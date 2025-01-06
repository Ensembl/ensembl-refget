#!/usr/bin/env python3

# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import os
import sys
import re
import tempfile
import shutil
import tkrzw
from pathlib import Path


def add_data(db, basedir, dirname):
    print(f"DB insert for {dirname}")

    for datatype in ['chrom', 'cdna', 'cds', 'pep']:

        hashfile = f"{datatype}.hashes"
        seqname = datatype
        if seqname == 'chrom':
            seqname = 'seq'

        seqfile = f"{dirname}/seqs/{seqname}.txt.zst"

        infile = os.path.join(basedir, dirname, hashfile)
        if not os.path.isfile(infile):
            print(f"Warning, missing file {infile}. Skipping.", file=sys.stderr)
            continue

        with open(infile, "rb") as file:
            startpos = 0
            for line in file:
                name, md5, sha, _, length, _ = line.split(b"\t")
                value = b"\t".join(
                    [
                        seqfile.encode('utf-8'),
                        str(startpos).encode('utf-8'),
                        length,
                        name,
                        md5
                    ]
                )
                db[md5] = sha
                db[sha] = value
                startpos += int(length.decode('utf-8'))


def main():
    parser = argparse.ArgumentParser(
        description=(
            'This will build the main lookup index for a refget server.'
            ' By default, this will ingest data for all species / genomes available from'
            ' <datadir>/genome_uuid_dir/{chrom,cdna,cds,pep}.hashes .'
        )
    )
    parser.add_argument("--datadir", help='Directory holding the data', required=True)

    # If you use /dev/shm on Slurm, the RAM to hold the DB will be accounted to
    # your process. You should allow for approx. 20GB per 100M entries.
    parser.add_argument("--dbfile",
        help=('Database file. Will be created if it does not exist.'
              ' It is recommended to create the DB in /dev/shm if available,'
              ' then copy it to permanent storage.'
              ),
        required=True
    )
    # This is using a file hash database. This specifies the number of buckets
    # that the hash will have. Ideally, this number should be larger than the
    # number of keys inserted. If there are more entries, keys will hash to the
    # same bucket and be stored in a linked list. Eventually, performance will
    # deteriorate, so this should be chosen to be large enough.
    # If a DB grows over time to exceed the initial value, it should be rebuilt.
    # It's possible to rebuild an existing database. This is not currently part
    # of this script.
    # The dbsize option is only applied when creating a database. When opening
    # an existing DB, it is ignored.
    parser.add_argument("--dbsize",
        help=(
            'Tunes the number of hash buckets for the DB. This should ideally be'
            ' about 20%% more than the number of entries you expect.'
            ' Default is 1 billion.'
        ),
        default=1_000_000_000,
        required=False,
        type=int
    )
    parser.add_argument("select_dirs",
        help=(
            'One or more directories to include, relative to datadir.'
            ' Optional. Omit to select all directories that look like a genome'
            ' uuid.'
        ),
        nargs='*'
    )
    args = parser.parse_args()


    dbsize = args.dbsize
    datadir = args.datadir
    dbfile = args.dbfile
    select_dirs = args.select_dirs

    print("Opening DB")
    db = tkrzw.DBM()
    # This is a Tkrzw file hash DB. Open as writeable.
    # The DB supports compression. This is not enabled because it saves a few
    # percent disk space but is almost half as fast
    db.Open(dbfile, True, no_wait=True, truncate=False,
            offset_width=5, align_pow=3,
            update_mode="UPDATE_IN_PLACE",
            dbm="HashDBM",
            num_buckets=dbsize).OrDie()

    print("DB open OK")

    i = 0
    if select_dirs:
        dirs_to_index = [Path(datadir, dir) for dir in select_dirs]
    else:
        dirs_to_index = os.scandir(datadir)

    for file in dirs_to_index:
        if not file.is_dir():
            continue
        dirname = file.name
        if not re.search(r'\w{8}-\w{4}-\w{4}-\w{4}-\w{12}', dirname):
            continue
        add_data(db, datadir, dirname)

    # Closes the database.
    db.Close().OrDie()


main()
