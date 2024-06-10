from __future__ import annotations
from fastapi import FastAPI, Header, HTTPException, Response, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse
from indexed_zstd import IndexedZstdFile
from models import Metadata, Metadata1, RefgetServiceInfo, Refget, ServiceType, Organization
from pydantic import conint
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse, PlainTextResponse, FileResponse
from typing import Optional
import asyncio
import dbm.gnu
import os

# Refget server implemetation
# This conforms to Refget API Specification v2.0.0

################################################################################
# Globals
################################################################################
INDEXDBPATH = "./data/index.gdbm"
SEQPATH = "./"
CACHE = {}
DB = dbm.gnu.open(INDEXDBPATH, "r")
CHUNKSIZE = 128 * 1024
SERVICEVERSION = "1.0.0"

################################################################################
# FastAPI app config
################################################################################
app = FastAPI(
    description='System for retrieving sequence and metadata concerning a reference sequence object by hash identifiers',
    version=SERVICEVERSION,
    title='Refget API server',
    contact={
        'name': 'EMBL-EBI GAA Infrastructure team',
        'email': 'ensembl-infrastructure@ebi.ac.uk',
        'url': 'https://refget-infra.internal.ebi.ac.uk',
    }
)


################################################################################
# Middleware
################################################################################
app.add_middleware(GZipMiddleware, minimum_size=2 * CHUNKSIZE, compresslevel=1)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    # allow_credentials=False is the default if origin is *, but better be explicit
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


################################################################################
# Helper methods / functions
################################################################################
async def read_zstd(filename, start, length):

    if filename in CACHE:
        file = CACHE[filename]
    else:
        try:
            file = IndexedZstdFile(filename)
        except:
            raise HTTPException(status_code=500, detail=f"Error opening {filename}")
        CACHE[filename] = file

    chunkstart = 0
    while chunkstart < length:
        try:
            file.seek(start + chunkstart)
            readlen = CHUNKSIZE
            if length - chunkstart < CHUNKSIZE:
                readlen = length - chunkstart
            data = file.read(readlen)

            chunkstart += readlen
        except:
            raise HTTPException(status_code=500, detail="Error reading sequence data")

        yield data


################################################################################
# App logic
################################################################################
@app.api_route(
    "/",
    methods=['GET', 'HEAD'],
    include_in_schema=False
)
async def root():
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
                    <a href="sequence/093f6ac5627a36f562fe2458b95975d0a60d8cbc4ef736c3">093f6ac, 160KB</a>
                </li>
                <li>
                    <a href="sequence/1e7e23d36c98cd650b817a53b3cb788d570201a354204aef">1e7e23d, 12 MB</a>
                </li>
                <li>
                    <a href="sequence/ff0779f0c5c47a47479c165d4e79f19b5bfc66cda43ac03a">ff0779f, 23 MB</a>
                </li>
                <li>
                    <a href="sequence/f9f6507d003783b80908384e5502058368b75049498c3f7f">f9f6507, 45 MB</a>
                </li>
                <li>
                    <a href="sequence/000018905fb82da47d20001dad1934f5b4ae7fa9331e5d11">0000189, 469 B</a>
                </li>
                <li>
                    <a href="sequence/000b7e851733e8b1237d461a6cfe016aed77267a9870f5af">000b7e8, 625B</a>
                </li>
                <li>
                    <a href="sequence/093f6ac5627a36f562fe2458b95975d0a60d8cbc4ef736c3/metadata">sequence/{id}/metadata</a>
                </li>
            </ul>
        </body>
    </html>
    """)

# The most important thing
@app.api_route(
    '/favicon.ico',
    methods=['GET', 'HEAD'],
    include_in_schema=False
)
async def favicon():
    return FileResponse('favicon.ico')


# service-info
@app.api_route(
    '/sequence/service-info',
    methods=['GET', 'HEAD'],
    response_model=RefgetServiceInfo,
    tags=['Other']
)
async def service_info() -> RefgetServiceInfo:
    """
    Retrieve a summary of features this API deployment supports
    """
    return RefgetServiceInfo(
        refget = Refget(
            circular_supported = False,
            algorithms = ["md5", "ga4gh", "trunc512"]
        ),
        id="refget.infra.ebi.ac.uk",
        name="Refget server",
        type=ServiceType(
            group="org.ga4gh",
            artifact="refget",
            version="2.0.0"
        ),
        organization=Organization(
            name="EMBL-EBI",
            url="https://ebi.ac.uk"
        ),
        version=SERVICEVERSION
    )

# sequence retrieval
@app.api_route(
    '/sequence/{qid}',
    methods=['GET', 'HEAD'],
    response_model=str,
    tags=['Sequence']
)
async def sequence(
    request: Request,
    qid: str,
    start: Optional[conint(ge=0)] = None,
    end: Optional[conint(ge=0)] = None,
    range: Optional[str] = Header(None, alias='Range'),
) -> StreamingResponse | PlainTextResponse:
    """
    Fetch and return sequence data for an identifier
    """

    # TODO: handle range

    # 400: bad request
    # 406 Not Acceptable
    # 416 Range Not Satisfiable
    # 501: not implemented

    # Treat nonsensical requests first
    if end == 0:
        return PlainTextResponse('', media_type='text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii')
    if start:
        if end and start > end:
            raise HTTPException(status_code=501, detail="Circular regions not currently supported")
        if start == end:
            return PlainTextResponse('', media_type='text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii')

    # Fetch data
    path, seqstart, seqlength = get_record(qid)

    # Treat range constraints
    if start:
        if start > seqlength:
            # Should be 422, but spec forces 400
            raise HTTPException(status_code=400, detail="Requested start is beyond end of sequence")
        if end and start > end:
            raise HTTPException(status_code=501, detail="Circular regions not currently supported")

        seqstart += start
        seqlength -= start

    if end:
        if start is None:
            start = 0
        if end < start:
            raise HTTPException(status_code=422, detail="End must be greater than start")
        end = end - start
        if end < seqlength:
            seqlength = end
    if range:
        raise HTTPException(status_code=422, detail=f"Got range: {range}")

    file = os.path.join(SEQPATH, path, 'seqs/seq.txt.zst')

    if request.method == 'HEAD':
        return Response(content=None, headers={'content-length': str(seqlength)} , media_type='text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii')

    return StreamingResponse(read_zstd(file, seqstart, seqlength), media_type='text/vnd.ga4gh.refget.v2.0.0+plain; charset=us-ascii')


def get_record(qid: str) -> tuple(str, int, int):
    record = DB.get(qid.encode())
    if record is None:
        raise HTTPException(status_code=404, detail="Sequence ID not found")
    record = record.decode('utf-8')
    [ path, seqstart, seqlength ] = record.split('\t')
    seqstart = int(seqstart)
    seqlength = int(seqlength)

    return (path, seqstart, seqlength)


# sequence metadata
@app.api_route(
    '/sequence/{qid}/metadata',
    methods=['GET', 'HEAD'],
    response_model=Metadata,
    tags=['Metadata']
)
async def metadata(qid: str) -> Metadata:
    """
    Get reference metadata from a hash
    """
    path, seqstart, seqlength = get_record(qid)

    return Metadata(metadata = Metadata1(
        id=qid,
        md5="Not available",
        trunc512=qid,
        ga4gh="TODO",
        length=seqlength,
        aliases=[]
    ))

