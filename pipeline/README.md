# Data files for the new web site

This repo contains a nextflow pipeline to prepare sequence data to serve 
by an API implementing the refget protocol in the context of the new Ensembl infrastructure.

## Structure of the project
- Scripts are contained in the [bin](bin) folder
- Perl libraries are in the [lib](lib) folder
- The [indexer](indexer) folder contains a program to create an index of sequences
- The [nextflow](nextflow) folder contains the Nextflow pipeline and related configuration
- Required dependencies are specified in `cpanfile` and `requirements.txt` for Perl and Python respectively

## Running the pipeline

#### Codon software environment

Set up the environment like this:

    source /hps/software/users/ensembl/ensw/swenv/initenv default


### Binaries

> [!NOTE]
> When using the new software environment on Codon, the dependencies are there,
> this step can be skipped.

The following packages (Debian/Ubuntu) are required for building/installing the 
other Python dependencies

   sudo apt-get install pkg-config python3-dev default-libmysqlclient-dev \
        build-essential python3-tkrzw tkrzw-utils

For convenience, there is a script `setup-env.sh` that sets up the
environment variables. You still have to install Python dependencies. If you choose
different locations for the dependencies, please adapt this to your needs.

### Perl

Perl has no dependencies.

### Python
There is a `requirements.txt` for the Python dependencies. Python >= 3.10 is required.
Recommended set up:

#### Set up dependencies

    mkdir venv
    python3 -m venv venv
    . venv/bin/activate
    pip install -r requirements.txt

## Running the scripts

### Generating sequence data for one or more genomes

Running the nextflow pipeline will generate data for one or more genomes.
Currently, the path to the `genomes.py` script from the Ensembl production
metadata API must be provided (please see below).

A config file for the DB connections must be provided. It must be JSON and
should look like this:

    {
    "meta" : "mysql://anonuser@metadata-host.ebi.ac.uk:1111/ensembl_genome_metadata"
    }

Run the pipeline like this:

    cd nextflow

    nextflow refget.nf -c config/refget.config -profile slurm \
    --factory_path $META_REPO_PATH/ensembl/production/metadata/api/factories/genomes.py \
    --output_path $OUTPUT_PATH \
    --script_path $GIT_REPO_PATH/ensembl-refget/bin \
    --dbconnection_file $CONFIG_PATH/db-connection-secrets.json \
    --metadatadb_key meta \
    --fasta_path $FASTA_PATH \
    --factory_selector 'Processing'

It accepts one or more genome uuids:

    --genome_uuid a73357ab-93e7-11ec-a39d-005056b38ce3

or

    --genome_uuid a73357ab-93e7-11ec-a39d-005056b38ce3,96156567-3c9f-4305-a3be-eacdb5dc4353,4aaf041d-5ab0-41e8-acd6-0abcc2a51029

Currently, the pipeline expects these environment variables to be set:

    $NOBACKUP_DIR : Work directory for the pipeline

### Information about individual scripts in 'pipeline'

- *bin/dump_from_fasta.pl* - Copies data out of Fasta files
- *bin/compress.pl* - Compresses files with a seekable ZSTD compression
- *indexer/create_indexdb.py* - Creates the index key-value database


# SOP

## Log in

    ssh to codon/slurm

## Activate new codon software environment

    source /hps/software/users/ensembl/ensw/swenv/initenv default

## Clone required repo: [ensembl-refget](https://github.com/Ensembl/ensembl-refget/)

    export BASE_DIR=~/refget-test
    mkdir -p $BASE_DIR
    cd $BASE_DIR
    git clone --depth 1 https://github.com/Ensembl/ensembl-refget/

## Install and activate py deps and set env variables used by nf pipeline

    cd $BASE_DIR/ensembl-refget/pipeline
    python3 -m venv venv
    . venv/bin/activate
    pip install -r requirements.txt

    export NOBACKUP_DIR=/hps/nobackup/flicek/ensembl/production/ensembl_dumps/web/ensembl-refget/
    export WORK_DIR=$BASE_DIR/work
    export OUTPUT_PATH=$BASE_DIR/output
    export FASTA_PATH=/hps/nobackup/flicek/ensembl/production/ensembl_dumps/blast/

## Create Output Directory and nf workflow dir

    cd $BASE_DIR/ensembl-refget/pipeline/nextflow
    mkdir -p $WORK_DIR
    
    export FACTORY_SCRIPT=$BASE_DIR/ensembl-refget/pipeline/venv/lib/python3.10/site-packages/ensembl/production/metadata/api/factories/genomes.py


## Run for all species
    nextflow refget.nf -c config/refget.config -profile slurm \
    --factory_path $FACTORY_SCRIPT \
    --output_path $OUTPUT_PATH \
    --script_path $BASE_DIR/ensembl-refget/pipeline/bin \
    --dbconnection_file $BASE_DIR/db-connection-secrets.json \
    --metadatadb_key meta \
    --fasta_path $FASTA_PATH \
    --factory_selector 'Processing'


## Run for specific genome UUIDs
    nextflow refget.nf -c config/refget.config -profile slurm \
    --factory_path $FACTORY_SCRIPT \
    --output_path $OUTPUT_PATH \
    --script_path $BASE_DIR/ensembl-refget/pipeline/bin \
    --dbconnection_file $BASE_DIR/db-connection-secrets.json \
    --metadatadb_key meta \
    --fasta_path $FASTA_PATH \
    --factory_selector 'Processing' \
    --genome_uuid a73357ab-93e7-11ec-a39d-005056b38ce3,96156567-3c9f-4305-a3be-eacdb5dc4353,4aaf041d-5ab0-41e8-acd6-0abcc2a51029

> [!IMPORTANT]
> In case of re-run, make sure to `rm -rf` as appropriate from the `OUTPUT_PATH` to 
> minimise some pain that will inevitably follow.

## Run the indexer
In order to the API to work and serve the sequence data, an index must be created by
the provided program.
The command lines below provide examples assuming you are as impatient as the authors of this 
document and want to maximise the I/O performance by using `/dev/shm`. Feel free to use another
device of your liking though.

### To create the index
The command below will create the index file `indexdb.tkh`, using genome-looking directories
within `path-to-data`.

   python create_indexdb.py -dbfile /dev/shm/indexdb.tkh --datadir /path-to-data

### To update an existing index
The procedure and command is exactly as per creating the index (see above).
If `/dev/shm/indexdb.tkh` exists, `create_indexdb.py` will update it with contents found
in the given `path-to-data`.

> [!IMPORTANT]
> Do not forget to copy or move the new index into its most appropriate location.

