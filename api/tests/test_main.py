import os
import refget
import logging
import hashlib

os.environ["INDEXDBPATH"] = "./testdata/indexdb.tkh"
os.environ["SEQPATH"] = "./testdata/"

from fastapi.testclient import TestClient
from refget.main import app

client = TestClient(app)


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    response = client.get("/sequence/service-info")
    assert response.status_code == 200
    assert response.json() == {
        "contactUrl": None,
        "createdAt": None,
        "description": None,
        "documentationUrl": None,
        "environment": None,
        "id": "refget.infra.ebi.ac.uk",
        "name": "Refget server",
        "organization": {"name": "EMBL-EBI", "url": "https://ebi.ac.uk/"},
        "refget": {
            "algorithms": ["md5", "ga4gh", "trunc512"],
            "circular_supported": False,
            "identifier_types": None,
            "subsequence_limit": None,
        },
        "type": {"artifact": "refget", "group": "org.ga4gh", "version": "2.0.0"},
        "updatedAt": None,
        "version": refget.main.SERVICEVERSION,
    }


def checklog(caplog, level, match, loggername="root"):
    assert caplog.records is not None and len(caplog.records) > 0

    record = caplog.records.pop(0)
    while record.name is not loggername and len(caplog.records) > 0:
        record = caplog.records.pop(0)

    assert record.levelname == level
    assert match in record.message


# test seq is the (single) e.coli chromosome, length 4_641_652. Data:
# Chromosome  482a2b04485ec8c4b5f4eaba2c2002da    3638c7b68436818772d9156401904a51106257bc69fbc652        4641652
def test_read_seq(caplog):
    caplog.set_level(logging.INFO)

    response = client.get("/sequence/482a2b04485ec8c4b5f4eaba2c2002da")
    assert response.status_code == 200
    assert len(response.text) == 4641652

    # Random small peptide:
    # ACO59992        0b49cb6558b97aea58066cbb482c6790        024d0fa06f5ef897aad15f9bf6553aaf2664e178e1b5adc0                21

    # Get with SHA
    response = client.get("/sequence/024d0fa06f5ef897aad15f9bf6553aaf2664e178e1b5adc0")
    assert response.status_code == 200
    assert len(response.text) == 21

    # Get with wrong SHA
    response = client.get("/sequence/024d0fa06f5ef897aad15f9bf6553aaf2664e178e1b5adc1")
    assert response.status_code == 404
    checklog(caplog, "INFO", "ID not found")

    # Get with MD5
    response = client.get("/sequence/0b49cb6558b97aea58066cbb482c6790")
    assert response.status_code == 200
    assert len(response.text) == 21

    # Get with wrong MD5
    response = client.get("/sequence/0b49cb6558b97aea58066cbb482c6791")
    assert response.status_code == 404
    checklog(caplog, "INFO", "ID not found")

    # Get with wrong string
    response = client.get("/sequence/sugar")
    assert response.status_code == 404
    checklog(caplog, "INFO", "ID not found")

    # Get with wrong string of length 33, will result in b64 decode attempt
    response = client.get("/sequence/012345678901234567890123456789123")
    assert response.status_code == 404
    checklog(caplog, "INFO", "ID not found")

    response = client.get("/sequence/SQ.Ak0PoG9e-Jeq0V-b9lU6ryZk4Xjhta3A")
    assert response.status_code == 200
    assert len(response.text) == 21

    response = client.get("/sequence/Ak0PoG9e-Jeq0V-b9lU6ryZk4Xjhta3A")
    assert response.status_code == 200
    assert len(response.text) == 21


def test_read_range(caplog):
    caplog.set_level(logging.INFO)

    # normal range get
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=0-39"},
    )
    # should be 206, but spec forces 200
    assert response.status_code == 200
    assert len(response.text) == 40
    assert response.text == "AGCTTTTCATTCTGACTGCAACGGGCAATATGTCTCTGTG"

    # range start after end of region
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=5000000-"},
    )
    # should be 416, but again, spec forces 400
    assert response.status_code == 400
    checklog(caplog, "INFO", "Invalid client query with start > end of sequence")

    # get with open end
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=4641600-"},
    )
    # should be 206
    assert response.status_code == 200
    assert len(response.text) == 52
    assert response.text == "TGATATTGAAAAAAATATCACCAAATAAAAAACGCCTTAGTAAGTATTTTTC"

    # get single char
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=0-0"},
    )
    assert response.status_code == 200
    assert len(response.text) == 1
    assert response.text == "A"

    # get two chars
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=0-1"},
    )
    # should be 206
    assert response.status_code == 200
    assert len(response.text) == 2
    assert response.text == "AG"

    # bad range spec
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "chars=5000000-"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Client sent invalid range header")

    # legal but not supported
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=-5"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Client sent invalid range header")

    # legal but not supported
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=5-10, 15-20, 25-"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Client sent invalid range header")
    # bad range spec
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "chars=5000000-"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Client sent invalid range header")

    # bad range spec
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=str"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Client sent invalid range header")
    # bad range spec
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=str-"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Client sent invalid range header")

    # bad range spec
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=99-str"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Client sent invalid range header")

    # range start after end of region
    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        headers={"Range": "bytes=5000000-"},
    )
    # should be 416, but again, spec forces 400
    assert response.status_code == 400
    checklog(caplog, "INFO", "Invalid client query with start > end of sequence")
    # remove https log message for next test
    checklog(caplog, "INFO", "400", "httpx")

    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        params={"start": 0, "end": 10},
        headers={"Range": "bytes=0-39"},
    )
    assert response.status_code == 400
    checklog(caplog, "INFO", "Invalid client query with range and start/end")

    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        params={"start": 0, "end": 10},
    )
    assert response.status_code == 200
    assert len(response.text) == 10
    assert response.text == "AGCTTTTCAT"

    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        params={"start": "1", "end": "10"},
    )
    assert response.status_code == 200
    assert len(response.text) == 9
    assert response.text == "GCTTTTCAT"

    response = client.get(
        "/sequence/482a2b04485ec8c4b5f4eaba2c2002da",
        params={"start": 400, "end": 10},
    )
    assert response.status_code == 501

    response = client.get(
        "/sequence/0b49cb6558b97aea58066cbb482c6790",
        params={"start": 400, "end": 410},
    )
    assert response.status_code == 400

    response = client.get(
        "/sequence/0b49cb6558b97aea58066cbb482c6790",
        params={"end": 10},
    )
    assert response.status_code == 200
    assert len(response.text) == 10
    assert response.text == "MKYINCVYNI"

    response = client.get(
        "/sequence/0b49cb6558b97aea58066cbb482c6790",
        params={"start": 10},
    )
    assert response.status_code == 200
    assert len(response.text) == 11
    assert response.text == "NYKLKPHSHYK"

    response = client.get(
        "/sequence/0b49cb6558b97aea58066cbb482c6790",
    )
    assert response.status_code == 200
    assert len(response.text) == 21
    assert (
        hashlib.md5(response.text.encode("utf-8")).hexdigest()
        == "0b49cb6558b97aea58066cbb482c6790"
    )


def test_read_meta():
    response = client.get("/sequence/482a2b04485ec8c4b5f4eaba2c2002da/metadata")
    assert response.status_code == 200
    assert response.json() == {
        "metadata": {
            "aliases": [],
            "ga4gh": "SQ.NjjHtoQ2gYdy2RVkAZBKURBiV7xp-8ZS",
            "id": "482a2b04485ec8c4b5f4eaba2c2002da",
            "length": 4641652,
            "md5": "482a2b04485ec8c4b5f4eaba2c2002da",
            "trunc512": "3638c7b68436818772d9156401904a51106257bc69fbc652",
        }
    }

    response = client.get(
        "/sequence/024d0fa06f5ef897aad15f9bf6553aaf2664e178e1b5adc0/metadata"
    )
    assert response.status_code == 200
    assert response.json() == {
        "metadata": {
            "aliases": [],
            "ga4gh": "SQ.Ak0PoG9e-Jeq0V-b9lU6ryZk4Xjhta3A",
            "id": "024d0fa06f5ef897aad15f9bf6553aaf2664e178e1b5adc0",
            "length": 21,
            "md5": "0b49cb6558b97aea58066cbb482c6790",
            "trunc512": "024d0fa06f5ef897aad15f9bf6553aaf2664e178e1b5adc0",
        }
    }

    # non-existant ID
    response = client.get(
        "/sequence/024d0fa06f5ef897aad15f9bf6553aaf2664e178e1b5adc1/metadata"
    )
    assert response.status_code == 404
