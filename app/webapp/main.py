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
import base64
import os
import re
import resource
import tkrzw
from typing import Optional

from cachetools import LFUCache
from fastapi import FastAPI, Header, HTTPException, Response, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from indexed_zstd import IndexedZstdFile
from pydantic import conint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse, PlainTextResponse, FileResponse

from models import (
    Alias,
    Metadata,
    Metadata1,
    RefgetServiceInfo,
    Refget,
    ServiceType,
    Organization,
)

class FHCache(LFUCache):
    def popitem(self):
        filename, file = super().popitem()
        file.close()
        return filename, file


# Refget server implemetation
# This conforms to Refget API Specification v2.0.0

################################################################################
# Globals
################################################################################
INDEXDBPATH = os.getenv("INDEXDBPATH","/www/unit/data/indexdb.tkh")
SEQPATH = os.getenv("SEQPATH","/www/unit/data/")

# Number of filehandles that this app may keep open to read the compressed data
# files. There will be some more open file handles for STDIN, STDOUT, STDERR and
# the indexdb. There might be more associated with Python, nginx or loggers.
softlimit, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
MAX_OPEN_FILEHANDLES = softlimit - 24

# This cache stores opened file handles with the associated IndexedZstdFile
# object. It will store up to MAX_OPEN_FILEHANDLES and automatically evict the
# least frequently used ones when that limit is reached.
CACHE = FHCache(maxsize=MAX_OPEN_FILEHANDLES)

DB = tkrzw.DBM()
DB.Open(INDEXDBPATH, False, no_create=True, no_wait=True, truncate=False,
        dbm="HashDBM").OrDie()

# Maximum number of (uncompressed) bytes to read per loop iteration. Also
# controls the minimum response size to start compressing the response.
CHUNKSIZE = 128 * 1024

# Version of this app. This is not the protocol version
SERVICEVERSION = "1.0.0"

################################################################################
# FastAPI app config
################################################################################
app = FastAPI(
    description=(
        "System for retrieving sequence and metadata concerning a reference sequence"
        " object by hash identifiers"
    ),
    version=SERVICEVERSION,
    title="Refget API server",
    contact={
        "name": "EMBL-EBI GAA Infrastructure team",
        "email": "ensembl-infrastructure@ebi.ac.uk",
        "url": "https://refget-infra.internal.ebi.ac.uk",
    },
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
async def read_zstd(file, start, length):
    """
    Read from zst compressed file in chunks, yield uncompressed data.
    """

    chunkstart = 0
    while chunkstart < length:
        try:
            file.seek(start + chunkstart)
            readlen = CHUNKSIZE
            if length - chunkstart < CHUNKSIZE:
                readlen = length - chunkstart
            data = file.read(readlen)

            chunkstart += readlen
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Error reading sequence data") from exc

        yield data


def get_record(qid: str) -> tuple(str, int, int, str, str):
    """
    Do a lookup for a SHA (TRUNC512) query id in the index database.
    Returns a tuple containing the data for the entry.
    """

    record = DB.Get(qid.encode())
    if record is None:
        raise HTTPException(status_code=404, detail="Sequence ID not found")
    record = record.decode("utf-8")
    [path, seqstart, seqlength, name, md5] = record.split("\t")
    seqstart = int(seqstart)
    seqlength = int(seqlength)

    return (path, seqstart, seqlength, name, md5)


def parse_range(range_raw_line: str) -> Tuple[int, int | None]:
    """
    Parse the Range header, return (start, end).
    Does not support multiple ranges (e.g. "Range: bytes=0-50, 100-150").
    A range like "100-" is valid and will return (100, None).
    """

    try:
        unit, ranges_str = range_raw_line.split("=", maxsplit=1)
    except ValueError:
        raise HTTPException(
            status_code=400, detail="Invalid 'Range' header"
        )
    if unit != "bytes":
        raise HTTPException(
            status_code=400,
            detail="Invalid unit for 'Range' header. Only 'bytes' ranges are supported."
        )

    matches = re.match(r"(\d+)-(\d+)?", ranges_str)

    if matches is None:
        raise HTTPException(
            status_code=400, detail="Invalid 'Range' header."
        )

    return (matches[1], matches[2])


_is_hex = re.compile('^[0-9a-fA-F]+$').search
def id_to_sha(qid: str):
    """
    Return a sha (TRUNC512) type query. If given an MD5 query id, will do a
    lookup for the SHA id.
    """

    if len(qid) == 48 and _is_hex(qid):
        return qid.lower()
    if len(qid) == 32 and _is_hex(qid):
        qid = qid.lower()
        return DB.Get(qid).decode("utf-8")

    namespace = "ga4gh"
    if ":" in qid:
        namespace, query = qid.split(":", maxsplit=1)
        qid = query

    namespace = namespace.lower()

    if namespace == "trunc512" and len(qid) == 48 and _is_hex(qid):
        return qid
    if namespace == "md5" and len(qid) == 32 and _is_hex(qid):
        return DB.Get(qid).decode("utf-8")
    if namespace == "ga4gh":
        return ga4gh_to_sha(qid)

    return None



def ga4gh_to_sha(qid: str):
    """
    Turns ga4gh type digest into truncated sha 512 (TRUNC512) type. Assumes no
    namespace.
    """
    base64_data = qid.replace("SQ.","")
    sha_bin = base64.urlsafe_b64decode(base64_data)
    return sha_bin.hex()

def sha_to_ga4gh(sha_txt):
    """
    Turns truncated sha 512 (TRUNC512) type digest into ga4gh type. Does not add
    a namespace.
    """
    sha_bin = bytes.fromhex(sha_txt)
    sha_b64 = base64.urlsafe_b64encode(sha_bin)
    sha_b64 = sha_b64.decode("utf-8")
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
            <title>Refget API demo</title>
        </head>
        <body>
            <h1>Refget API demo</h1>
            <ul>
                <li>
                    <a href="sequence/service-info">sequence/service-info</a>
                </li>
                <li>
                    <a href="sequence/3129e478766bbbd904ed9825e4b82b5fbc98b20ba16d1e28">PEP ENSP00000426975.1 3129e47 1178 b</a>
                </li>
                <li>
                    <a href="sequence/ee3d05dff4ed34cad1d1b5a359d11c91edfeac44952c8d48">CDS ENST00000511072.5 ee3d05d 3537 b</a>
                </li>
                <li>
                    <a href="sequence/1085aeabd7922049ea428eea3ea65f6566111da51c30482c">CDNA ENST00000624431.2 1085aea 570 b</a>
                </li>
                <li>
                    <a href="sequence/2f52fa14ef0448864904d4ce4cf2bb1a766f25889ec0a2b4">2f52fa1, 13794 b</a>
                </li>
                <li>
                    <a href="sequence/3b20ace25e343148aafb31b0f0b67058e838197019da55ae">3b20ace, 23533 b</a>
                </li>
                <li>
                    <a href="sequence/2f52fa14ef0448864904d4ce4cf2bb1a766f25889ec0a2b4/metadata">sequence/2f52fa1.../metadata</a>
                </li>
            </ul>
        </body>
    </html>
    """)


# The most important thing
@app.api_route("/favicon.ico", methods=["GET", "HEAD"], include_in_schema=False)
async def favicon():
    """
    Return a FileResponse for the favicon.
    """

    return FileResponse("favicon.ico")


# service-info
@app.api_route(
    "/sequence/service-info",
    methods=["GET", "HEAD"],
    response_model=RefgetServiceInfo,
    tags=["Other"],
)
async def service_info() -> RefgetServiceInfo:
    """
    Retrieve a RefgetServiceInfo describing the features this API deployment supports.
    """
    return RefgetServiceInfo(
        refget=Refget(circular_supported=False, algorithms=["md5", "ga4gh", "trunc512"]),
        id="refget.infra.ebi.ac.uk",
        name="Refget server",
        type=ServiceType(group="org.ga4gh", artifact="refget", version="2.0.0"),
        organization=Organization(name="EMBL-EBI", url="https://ebi.ac.uk"),
        version=SERVICEVERSION,
    )


# sequence retrieval
@app.api_route(
    "/sequence/{qid}", methods=["GET", "HEAD", "OPTIONS"],
    response_model=str,
    tags=["Sequence"]
)
async def sequence(
    request: Request,
    qid: str,
    start: Optional[conint(ge=0)] = None,
    end: Optional[conint(ge=0)] = None,
    range_header: Optional[str] = Header(None, alias="Range"),
) -> StreamingResponse | PlainTextResponse:
    """
    Fetch and return sequence data for an identifier.
    """

    # 400: bad request
    # 406 Not Acceptable
    # 416 Range Not Satisfiable
    # 501: not implemented

    if range_header:
        if (start or end):
            raise HTTPException(
                status_code=400,
                detail="Range request and start/end parameters are mutually exclusive"
            )
        start, end = parse_range(range_header)

        # In the following code, we don't want to care where this comes from.
        # But for the range header, the end is inclusive, for refget, the end
        # parameter is exclusive. Make this match the parameter semantic.
        if end:
            end = int(end) + 1

    if start is None:
        start = 0
    else:
        start = int(start)

    # Treat nonsensical requests first
    if end:
        if start > end:
            raise HTTPException(
                status_code=501, detail="Circular regions not currently supported"
            )
        if start == end:
            return PlainTextResponse(
                "", media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii"
            )


    sha_id = id_to_sha(qid)
    if sha_id is None:
        raise HTTPException(status_code=404, detail="Sequence ID not found")

    # Fetch data
    path, seqstart, seqlength, _, _ = get_record(sha_id)

    # Treat range constraints
    if start >= seqlength:
        # Should be 422, but spec forces 400
        raise HTTPException(
            status_code=400, detail="Requested start is beyond end of sequence"
        )

    if end is None:
        end = seqlength

    if start > end:
        raise HTTPException(
            status_code=501, detail="Circular regions not currently supported"
        )

    seqstart += start
    seqlength -= start

    end = end - start
    seqlength = min(seqlength, end)
    if seqlength == 0:
        return PlainTextResponse(
            "", media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii"
        )


    if request.method == "HEAD":
        return Response(
            content=None,
            headers={"content-length": str(seqlength)},
            media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii",
        )
    if request.method == "OPTIONS":
        return Response(
            content=None,
            headers={"allow": "OPTIONS, GET, HEAD"},
        )

    filename = os.path.join(SEQPATH, path)

    if filename in CACHE:
        filehandle = CACHE[filename]
    else:
        try:
            filehandle = IndexedZstdFile(filename)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error opening {filename}") from exc
        CACHE[filename] = filehandle


    return StreamingResponse(
        read_zstd(filehandle, seqstart, seqlength),
        media_type="text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii",
    )



# sequence metadata
@app.api_route(
    "/sequence/{qid}/metadata",
    methods=["GET", "HEAD"],
    response_model=Metadata,
    tags=["Metadata"],
)
async def metadata(qid: str) -> Metadata:
    """
    Return aliases, length and available hash types for a query hash.
    """

    sha_id = id_to_sha(qid)
    if sha_id is None:
        raise HTTPException(status_code=404, detail="Sequence ID not found")

    _, _, seqlength, name, md5_id = get_record(sha_id)

    ga4gh_id = sha_to_ga4gh(sha_id)

    return Metadata(
        metadata=Metadata1(
            id=qid,
            md5=md5_id,
            trunc512=sha_id,
            ga4gh=ga4gh_id,
            length=seqlength,
            aliases=[
                Alias(naming_authority='ensembl', alias=name)
            ],
        )
    )
