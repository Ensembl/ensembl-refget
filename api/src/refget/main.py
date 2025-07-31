"""
See the NOTICE file distributed with this work for additional information
regarding copyright ownership.


Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations
from contextlib import asynccontextmanager
from pathlib import Path as OsPath
from typing import Optional, Tuple, List
from typing_extensions import Annotated
import base64
import binascii
import logging
import os
import re
import resource

from cachetools import LFUCache
from fastapi import FastAPI, Header, HTTPException, Request, Path
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from indexed_zstd import IndexedZstdFile
from pydantic import Field, HttpUrl
from starlette.config import Config
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse, PlainTextResponse, FileResponse
import tkrzw
import uvicorn

from refget.models import (
    Metadata,
    Metadata1,
    Organization,
    Refget,
    RefgetServiceInfo,
    ServiceType,
)


class FHCache(LFUCache):
    def popitem(self):
        filename, file = super().popitem()
        file.close()
        return filename, file


# Refget server implementation
# This conforms to Refget API Specification v2.0.0

################################################################################
# Globals and config
################################################################################
# If a file named .env is present, take env variables from it
CONFFILE = ".env"
if OsPath(CONFFILE).is_file():
    config = Config(CONFFILE)
else:
    config = Config(None)

INDEXDBPATH = config("INDEXDBPATH", default="/www/unit/data/indexdb.tkh")
if not OsPath(INDEXDBPATH).is_file():
    raise SystemExit(
        f"Error: Index DB file not found: {INDEXDBPATH}. Please set the env variable INDEXDBPATH to the right path."
    )

SEQPATH = config("SEQPATH", default="/www/unit/data/")
if not OsPath(SEQPATH).is_dir():
    raise SystemExit(
        f"Error: Data file directory not found: {SEQPATH}. Please set the env variable SEQPATH to the right path."
    )

# Number of filehandles that this app may keep open to read the compressed data
# files. There will be some more open file handles for STDIN, STDOUT, STDERR and
# the indexdb. There might be more associated with Python, nginx or loggers.
softlimit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
MAX_OPEN_FILEHANDLES = softlimit - 24

# This cache stores opened file handles with the associated IndexedZstdFile
# object. It will store up to MAX_OPEN_FILEHANDLES and automatically evict the
# least frequently used ones when that limit is reached.
CACHE = FHCache(maxsize=MAX_OPEN_FILEHANDLES)

# Index database
DB = tkrzw.DBM()
DB.Open(
    INDEXDBPATH, False, no_create=True, no_wait=True, truncate=False, dbm="HashDBM"
).OrDie()

# Maximum number of (uncompressed) bytes to read per loop iteration. Also
# controls the minimum response size to start compressing the response.
CHUNKSIZE = 128 * 1024

# Version of this app. This is not the protocol version
SERVICEVERSION = "1.0.1"

MOUNTPATH = config("MOUNTPATH", default="/")
DEBUG: bool = config("DEBUG", cast=bool, default=False)

LOG = logging.getLogger()

LOGLEVELSTR = config("LOGLEVEL", default="INFO")
if DEBUG:
    LOGLEVEL = logging.DEBUG
elif LOGLEVELSTR:
    LOGLEVEL = logging.getLevelName(LOGLEVELSTR)
else:
    LOGLEVEL = logging.INFO


################################################################################
# FastAPI app config
################################################################################


# Configure loggers on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    global LOG
    LOG = logging.getLogger("uvicorn")
    LOG.setLevel(logging.INFO)
    LOG.info("Setting log level to: %s", logging.getLevelName(LOGLEVEL))

    for logger in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
        logging.getLogger(logger).setLevel(LOGLEVEL)

    LOG.info("Logging configured. Refget version %s starting.", SERVICEVERSION)

    yield


app = FastAPI(
    description=(
        "System for retrieving sequence and metadata concerning a reference sequence"
        " object by hash identifiers"
    ),
    version=SERVICEVERSION,
    title="Refget API server",
    contact={
        "name": "EMBL-EBI Genomics Technology Infrastructure",
        "email": "helpdesk@ensembl.org",
        "url": "https://beta.ensembl.org/api/refget",
    },
    redoc_url=None,
    lifespan=lifespan,
    openapi_url=str(OsPath(MOUNTPATH, "openapi.json")),
)


################################################################################
# Middleware
################################################################################
app.add_middleware(GZipMiddleware, minimum_size=2 * CHUNKSIZE, compresslevel=1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_credentials=False is the default if origin is *, but better be explicit
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


################################################################################
# Helper methods / functions
################################################################################
async def read_zstd(file: IndexedZstdFile, requests: List[Tuple[int, int]]):
    """
    Read from zst compressed file in chunks, yield uncompressed data.

    Parameters
    ----------
    file : IndexedZstdFile
        zst compressed file to read

    requests : List[Tuple[int,int]]
        Each tuple represents where to start to read the compressed zst from and
        length of the read. Both expressed in uncompressed positions

    Returns
    -------
    Yields chunks as they are read
    """
    for request in requests:
        start, length = request
        LOG.debug("read_zstd: file=%s start=%s length=%s", file.name, start, length)

        chunkstart = 0
        while chunkstart < length:
            try:
                file.seek(start + chunkstart)
                readlen = CHUNKSIZE
                if length - chunkstart < CHUNKSIZE:
                    readlen = length - chunkstart
                data = file.read(readlen)
                if len(data) != readlen:
                    LOG.error(
                        (
                            "Short read for: file=%s start=%s length=%s. "
                            "Client may have received partial data"
                        ),
                        file.name,
                        start,
                        length,
                    )
                    # This is a streaming request. A 200 OK header has already been
                    # sent, so there is no way of sending a 500 now. This is the best we
                    # can do.
                    yield "\n\nIO error. Sequence truncated.\n"
                    break

                chunkstart += readlen
            except Exception as exc:
                LOG.error(
                    (
                        "Error reading sequence data: file=%s start=%s length=%s. "
                        "Client may have received partial data"
                    ),
                    file.name,
                    start,
                    length,
                    exc_info=exc,
                )
                # Same as above, this is the best we can do.
                # can do.
                yield "\n\nIO error. Sequence truncated.\n"
                break

            yield data


def get_record(qid: str) -> Tuple[str, int, int, str, str]:
    """
    Do a lookup for a SHA (TRUNC512) query id in the index database.
    Returns a tuple containing the data for the entry.
    """

    record_b = DB.Get(qid.encode())

    if record_b is None:
        LOG.info("ID not found: %s", qid)
        raise HTTPException(status_code=404, detail="Sequence ID not found")
    record = record_b.decode("utf-8")
    [path, seqstart, seqlength, name, md5] = record.split("\t")

    if md5 is None:
        LOG.error("Invalid record in index DB. qid=%s record=%s", qid, record)
        raise HTTPException(status_code=500, detail="Internal DB error")

    seqstart_i = int(seqstart)
    seqlength_i = int(seqlength)

    return (path, seqstart_i, seqlength_i, name, md5)


def parse_range(range_raw_line: str) -> Tuple[int, int | None]:
    """
    Parse the Range header, return (start, end).
    Does not support multiple ranges (e.g. "Range: bytes=0-50, 100-150").
    A range like "100-" is valid and will return (100, None).
    """

    try:
        unit, ranges_str = range_raw_line.split("=", maxsplit=1)
    except ValueError:
        LOG.info("Client sent invalid range header: %s", range_raw_line)
        raise HTTPException(status_code=400, detail="Invalid 'Range' header")
    if unit != "bytes":
        LOG.info("Client sent invalid range header: %s", range_raw_line)
        raise HTTPException(
            status_code=400,
            detail="Invalid unit for 'Range' header. Only 'bytes' ranges are supported.",
        )

    matches = re.match(r"^(\d+)-(\d+)?$", ranges_str)

    if matches is None:
        LOG.info("Client sent invalid range header: %s", range_raw_line)
        raise HTTPException(status_code=400, detail="Invalid 'Range' header.")

    start = int(matches[1])
    end = None
    if matches[2] is not None:
        end = int(matches[2])

    return (start, end)


_is_hex = re.compile("^[0-9a-fA-F]+$").search


def id_to_sha(qid: str):
    """
    Return a sha (TRUNC512) type query. If given an MD5 query id, will do a
    lookup for the SHA id.
    """

    if len(qid) == 48 and _is_hex(qid):
        return qid.lower()
    if len(qid) == 32 and _is_hex(qid):
        qid = qid.lower()
        record = DB.Get(qid.encode())
        if record is None:
            return None
        return record.decode("utf-8")

    namespace = "ga4gh"
    if ":" in qid:
        namespace, query = qid.split(":", maxsplit=1)
        qid = query

    namespace = namespace.lower()

    if namespace == "trunc512" and len(qid) == 48 and _is_hex(qid):
        return qid
    if namespace == "md5" and len(qid) == 32 and _is_hex(qid):
        record = DB.Get(qid.encode())
        if record is None:
            return None
        return record.decode("utf-8")
    if namespace == "ga4gh" and (len(qid) == 32 or len(qid) == 35):
        return ga4gh_to_sha(qid)

    return None


def ga4gh_to_sha(qid: str):
    """
    Turns ga4gh type digest into truncated sha 512 (TRUNC512) type. Assumes no
    namespace.
    """
    base64_data = qid.replace("SQ.", "")
    try:
        sha_bin = base64.urlsafe_b64decode(base64_data)
    except (binascii.Error, ValueError):
        LOG.info("Client query with invalid b64 in ga4gh ID: %s", qid)
        return None
    return sha_bin.hex()


def sha_to_ga4gh(sha_txt: str):
    """
    Turns truncated sha 512 (TRUNC512) type digest into ga4gh type. Does not add
    a namespace.
    """
    sha_bin = bytes.fromhex(sha_txt)
    sha_b64_b = base64.urlsafe_b64encode(sha_bin)
    sha_b64 = sha_b64_b.decode("utf-8")
    return f"SQ.{sha_b64}"


################################################################################
# App logic
################################################################################
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def root():
    """
    Return HTML for the index page.
    """

    return HTMLResponse("""
    <html>
        <head>
            <title>Refget Server</title>
        </head>
        <body>
            <h1>Refget Server</h1>

            This server offers reference sequence data according to the <b>Refget</b> protocol.

            <ul>
                <li>
                    <a href="docs">API documentation</a>
                </li>
            </ul>
        </body>
    </html>
    """)


# Serve the favicon
@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon():
    """
    Return a FileResponse for the favicon.
    """

    path = OsPath(OsPath(__file__).parent, "favicon.ico")
    return FileResponse(path)


# service-info
@app.get(
    "/sequence/service-info",
    response_model=RefgetServiceInfo,
    tags=["Service info"],
)
@app.head(
    "/sequence/service-info",
    response_model=RefgetServiceInfo,
    tags=["Service info"],
)
async def service_info() -> RefgetServiceInfo:
    """
    Retrieve a RefgetServiceInfo describing the features this API deployment supports.
    """
    return RefgetServiceInfo(
        refget=Refget(
            circular_supported=True, algorithms=["md5", "ga4gh", "trunc512"]
        ),
        id="refget.infra.ebi.ac.uk",
        name="Refget server",
        type=ServiceType(group="org.ga4gh", artifact="refget", version="2.0.0"),
        organization=Organization(
            name="EMBL-EBI", url=HttpUrl(url="https://ebi.ac.uk")
        ),
        version=SERVICEVERSION,
    )


# sequence retrieval
@app.get(
    "/sequence/{qid}",
    response_model=str,
    tags=["Sequence retrieval"],
)
@app.head(
    "/sequence/{qid}",
    response_model=str,
    tags=["Sequence retrieval"],
)
@app.options(
    "/sequence/{qid}",
    response_model=str,
    tags=["Sequence retrieval"],
)
async def sequence(
    request: Request,
    qid: str = Path(
        ...,
        description="Query identifier. MD5, truncated SHA512 and ga4gh identifiers are accepted",
        openapi_examples={
            "MD5": {
                "summary": "MD5",
                "description": "An MD5 query ID.",
                "value": "091c2d0c6fb2a0b381797e22f2b05b47",
            },
            "SHA512": {
                "summary": "SHA512",
                "description": "A truncated SHA512 query ID.",
                "value": "9ebae97fdd0133e9eb93e7036901fc08d0e6ca763931a0d6",
            },
            "GA4GH": {
                "summary": "GA4GH",
                "description": "An GA4GH / refget query ID.",
                "value": "SQ.nrrpf90BM-nrk-cDaQH8CNDmynY5MaDW",
            },
        },
    ),
    start: Optional[Annotated[int, Field(ge=0)]] = None,
    end: Optional[Annotated[int, Field(ge=0)]] = None,
    range_header: Optional[str] = Header(None, alias="Range"),
) -> StreamingResponse | PlainTextResponse:
    """
    Fetch and return sequence data for an identifier.
    """

    LOG.debug(
        "Query: qid=%s, start=%s, end=%s, range_header=%s",
        qid,
        start,
        end,
        range_header,
    )
    # 400: bad request
    # 406 Not Acceptable
    # 416 Range Not Satisfiable
    # 501: not implemented

    if range_header:
        if start or end:
            LOG.info("Invalid client query with range and start/end")
            raise HTTPException(
                status_code=400,
                detail="Range request and start/end parameters are mutually exclusive",
            )
        start, end = parse_range(range_header)

        # In the following code, we don't want to care where this comes from.
        # But for the range header, the end is inclusive, for refget, the end
        # parameter is exclusive. Make this match the parameter semantic.
        if end is not None:
            end = end + 1

        # Cannot support circular requests with range. But can only test this if start & end are defined
        if start and end and start > end:
            LOG.info("Invalid client query with start > end")
            raise HTTPException(
                status_code=416,
                detail="Range request has start > end. Circular requests not supported as a range header",
            )

    if start is None:
        start = 0
    else:
        start = int(start)

    # Treat nonsensical requests first
    if end and start == end:
        return PlainTextResponse(
            "", media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii"
        )

    sha_id = id_to_sha(qid)
    if sha_id is None:
        LOG.info("ID not found: %s", qid)
        raise HTTPException(status_code=404, detail="Sequence ID not found")

    # Fetch data
    path, seqstart, seqlength, _, _ = get_record(sha_id)

    # Treat range constraints
    if start >= seqlength:
        LOG.info("Invalid client query with start > end of sequence")
        # Should be 422, but spec forces 400
        raise HTTPException(
            status_code=400, detail="Requested start is beyond end of sequence"
        )

    if end is None:
        end = seqlength

    # Refget encodes circular locations as start > end i.e. range goes through the
    # ori. Since sequences are held linear we split region into two requests
    #
    # 1). start to sequence length
    # 2). 0 to end
    if start > end:
        LOG.debug(
            f"Circular location detected: {start}-{end}. Splitting into two requests"
        )
        regions = [((seqstart + start), (seqlength - start))]
        # End of 0 is a no-op
        if end != 0:
            regions.append((seqstart, end))
    else:
        seqstart += start
        seqlength -= start

        end = end - start
        seqlength = min(seqlength, end)
        regions = [(seqstart, seqlength)]

    total_seqlength = sum(region[1] for region in regions)
    if total_seqlength == 0:
        return PlainTextResponse(
            "", media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii"
        )

    if request.method == "HEAD":
        return PlainTextResponse(
            content=None,
            headers={"content-length": str(total_seqlength)},
            media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii",
        )
    if request.method == "OPTIONS":
        return PlainTextResponse(
            content=None,
            headers={"allow": "OPTIONS, GET, HEAD"},
        )

    filename = os.path.join(SEQPATH, path)

    if filename in CACHE:
        filehandle = CACHE[filename]
    else:
        if not OsPath(filename).is_file():
            LOG.error("File not found: %s", filename)
            raise HTTPException(
                status_code=500, detail="Internal error. Data not found"
            )

        try:
            filehandle = IndexedZstdFile(filename)
        except Exception as exc:
            LOG.error(
                "Error creating IndexedZstdFile for file: %s", filename, exc_info=exc
            )
            raise HTTPException(status_code=500, detail="Internal error. Bad data")
        CACHE[filename] = filehandle

    return StreamingResponse(
        read_zstd(filehandle, regions),
        media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii",
    )


# sequence metadata
@app.get(
    "/sequence/{qid}/metadata",
    response_model=Metadata,
    tags=["Sequence metadata"],
)
@app.head(
    "/sequence/{qid}/metadata",
    response_model=Metadata,
    tags=["Sequence metadata"],
)
async def metadata(qid: str) -> Metadata:
    """
    Return aliases, length and available hash types for a query hash.
    """

    sha_id = id_to_sha(qid)
    if sha_id is None:
        LOG.info("ID not found: %s", qid)
        raise HTTPException(status_code=404, detail="Sequence ID not found")

    _, _, seqlength, _, md5_id = get_record(sha_id)

    ga4gh_id = sha_to_ga4gh(sha_id)

    return Metadata(
        metadata=Metadata1(
            id=qid,
            md5=md5_id,
            trunc512=sha_id,
            ga4gh=ga4gh_id,
            length=seqlength,
            aliases=[],
        )
    )


if __name__ == "__main__":
    uvicorn.run(app, log_config="logconfig.yaml")
