#!/usr/bin/env python3
import argparse
import os
import sys
import re
import tempfile
import shutil
import tkrzw


def add_data(db, basedir, dirname):
    print(f"DB insert for {dirname}")

    infile = os.path.join(basedir, dirname, 'chrom.hashes')
    if not os.path.isfile(infile):
        print(f"Warning, missing file {infile}. Skipping.", file=sys.stderr)
        return

    with open(infile, "rb") as file:
        startpos = 0
        for line in file:
            name, md5, sha, _, length, _ = line.split(b"\t")
#            print(row)
            value = b"\t".join([dirname.encode('utf-8'), str(startpos).encode('utf-8'), length, name])
#           print(f"MD5 {md5}; SHA512T {sha}; DATA {value}")
            db[md5] = sha
            db[sha] = value
            startpos += int(length.decode('utf-8'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("datadir", help='Directory holding the data')
    parser.add_argument("dbfile",
        help='Database file. Will be created if it does not exist'
    )
    args = parser.parse_args()


    datadir = args.datadir
    dbfile = args.dbfile

    print("Opening DB")
    db = tkrzw.DBM()
    # This is a Tkrzw file hash DB. Open as writeable.
    # The DB supports compression. This is not enabled because it saves a few
    # percent disk space but is almost half as fast
    db.Open(dbfile, True, no_wait=True, truncate=False,
            offset_width=5, align_pow=3,
            update_mode="UPDATE_IN_PLACE",
            dbm="HashDBM",
            num_buckets=1_000_000_000)

    print("DB open OK")

    i = 0
    for file in os.scandir(datadir):
        if not file.is_dir():
            continue
        dirname = file.name
        if not re.search(r'\w{8}-\w{4}-\w{4}-\w{4}-\w{12}', dirname):
            continue
        add_data(db, datadir, dirname)

    # Closes the database.
    db.Close()


main()
