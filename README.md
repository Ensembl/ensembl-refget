# A Refget server, implemented in Python

This is a REST API server, conforming to the
[Refget specification](https://samtools.github.io/hts-specs/refget.html)
It is implemented with Python and Fastapi.

Please also see the README file for the refget app [here](api/README.md).

## How to run with Docker

Two docker files are provided, one for nginx-unit and one for Uvicorn.
Choose one, build the Docker image, then run it:

    docker build --tag=refget-app .
    docker run -it --mount type=bind,src=/anypath/,dst=/www/unit/data -p 8000:8000 refget-app:latest

If data is mounted to a different path in the container, the env variables
INDEXDBPATH and SEQPATH must be set accordingly.

## Data

This app expects data with this layout:

    anypath/
    anypath/indexdb.tkh
    anypath/<genome_uuid>/
    anypath/<genome_uuid>/seqs/
    anypath/<genome_uuid>/seqs/seq.txt.zst
    anypath/<genome_uuid>/seqs/cdna.txt.zst
    anypath/<genome_uuid>/seqs/cds.txt.zst
    anypath/<genome_uuid>/seqs/pep.txt.zst
