#!/usr/bin/env sh
cd src/refget
export INDEXDBPATH=../../testdata/indexdb.tkh SEQPATH=../../testdata/
exec uvicorn main:app --workers 2 --log-config logconfig.yaml
