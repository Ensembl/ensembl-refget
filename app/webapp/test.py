import sys
import os

sys.path.append('/usr/lib/python3/dist-packages/')

os.environ["DEBUSSY"] = "1"
os.environ["INDEXDBPATH"] = "../testdata/indexdb.tkh"
os.environ["SEQPATH"] = "../testdata/"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

def test_read_main():
    response = client.get("/")
    assert response.status_code == 200

def test_read_seq():
    response = client.get("/sequence/2f52fa14ef0448864904d4ce4cf2bb1a766f25889ec0a2b4")
    assert response.status_code == 200
    assert len(response.text) == 13794

def test_read_meta():
    response = client.get("/sequence/2f52fa14ef0448864904d4ce4cf2bb1a766f25889ec0a2b4/metadata")
    assert response.status_code == 200
    print(response.text)

# TODO:
# * get metadata, compare length to response length, re-calc checksums and compare
# * get seq with start or end or both
# * get seq at beginning and at end of zst file
# * open more files than fit in cache
# * check range behaviour and data

def test_read_range():
    response = client.get("/sequence/2f52fa14ef0448864904d4ce4cf2bb1a766f25889ec0a2b4",
               headers={"Range": "bytes=0-99"})
    assert response.status_code == 200
    assert len(response.text) == 100
    response = client.get("/sequence/2f52fa14ef0448864904d4ce4cf2bb1a766f25889ec0a2b4",
               headers={"Range": "bytes=13794-"})
    assert response.status_code == 400
    response = client.get("/sequence/2f52fa14ef0448864904d4ce4cf2bb1a766f25889ec0a2b4",
               headers={"Range": "bytes=13694-"})
    assert response.status_code == 200
    assert len(response.text) == 100
    print(response.text)

