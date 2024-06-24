# Data files for the new web site

This repo contains a nextflow pipeline to prepare genomic data for the Genome
Browser in the new Ensembl web site.

## Structure of the project
- Scripts are contained in the [bin](/bin) folder
- Perl modules are in the [lib](/lib) folder
- Python modules are in the [lib/python](/lib/python) folder
- Configs and sql schemas are in [common_files](/common_files)
- The Nextflow pipeline is in [nextflow](/nextflow)

## Requirements

#### Codon software environment

Set up the environment like this:

    source /hps/software/users/ensembl/ensw/swenv/initenv default

### Perl

When using the new software environment on Codon, the dependencies are there,
this step can be skipped.

If not, to install the Perl dependencies manually, there is a `cpanfile` for the
Perl requirements. Install with `cpanm --installdeps .` Recommended set up:

    cpanm -l ~/perl5 --installdeps .

### Python
There is a `requirements.txt` for the Python dependencies. Python >= 3.10 is required.
Recommended set up:

#### Set up dependencies

    mkdir venv
    python3 -m venv --system-site-packages venv
    . venv/bin/activate
    pip install -r requirements.txt

### Binaries

- The binary `bedSort` and `bedToBigBed` from the UCSC genome browser distribution (also known as
Kent tools). They are present when using the new software environment.
If not, these can be downloaded from UCSC.

- The binary `ncd-build` from Dan Sheppard's ncd tools. Found on Codon. Can also
be compiled from source on github: `https://github.com/ens-ds23/ncd-tools`

- For convenience, there is a script `setup-env.sh` that sets up the
environment. You still have to install Python dependencies. If you choose
different locations for the dependencies, please adapt this to your needs.

### Docker

There is a Dockerfile to generate a Docker container. This is currently
outdated.


## Running the scripts

### Generating all data for one or more genomes

Running the nextflow pipeline will generate data for one or more genomes.
Currently, the path to the `genomes.py` script from the Ensembl production
metadata API must be provided.

A config file for the DB connections must be provided. It must be JSON and
should look like this:

    {
    "meta" : "mysql://anonuser@metadata-host.ebi.ac.uk:1111/ensembl_genome_metadata",
    "species" : "mysql://anonuser@species-host.ebi.ac.uk:1111/"
    }

Run the pipeline like this:

    cd nextflow

    nextflow datafile.nf -c config/datafile.config -profile slurm \
    --factory_path $META_REPO_PATH/ensembl/production/metadata/api/factories/genomes.py \
    --output_path $OUTPUT_PATH/e2020-datafile-2024-03/ \
    --script_path $GIT_REPO_PATH/ensembl-e2020-datafiles/bin \
    --dbconnection_file $CONFIG_PATH/db-connection-secrets.json \
    --metadatadb_key meta --speciesdb_key species

It accepts one or more genome uuids:

    --genome_uuid a73357ab-93e7-11ec-a39d-005056b38ce3

or

    --genome_uuid a73357ab-93e7-11ec-a39d-005056b38ce3,96156567-3c9f-4305-a3be-eacdb5dc4353,4aaf041d-5ab0-41e8-acd6-0abcc2a51029

The option `--skipdone` will skip a step if the final output files for that step are present.

Currently, the pipeline expects these environment variables to be set:

    $NOBACKUP_DIR : Work directory for the pipeline
    $ENS_VERSION : Release version
    $BASE_CONFIG_DIR : Directory with the base nextflow config, e.g.
        '$GIT_REPO_PATH/ensembl-e2020-datafiles/nextflow/config'

### Information about individual scripts

- *report_and_chrom_new.pl* - Fetches data from the DB. Builds the
    genome_report.txt, the chrom.hashes and chrom.sizes files. Fetches sequence
    data, calculates hashes and GC data. Builds the the chrom.hashes(.ncd) and
    chrom.sizes(.ncd) files as well as the gc bigWig (gc.bw) file.

- *fetch_gene_bed_files.py* - Fetches genes and transcripts from the DB. Builds the transcripts.bed file

- *fetch_contigs.pl* - Fetches contigs from the DB. Builds the contigs.bed file
- *fetch_repeats.pl* - Fetches repeats from the DB. Builds the repeats.bed file
- *fetch_simplefeatures.pl* - Fetches simplefeatures from the DB. Builds the simplefeatures.bed file

- *index_bigbeds.pl* - Creates a BigBed (*.bb) file from a Bed file (*.bed)

- *focus_file.pl* - Builds the jump.ncd file


The files present in bin/tools and bin/check are currently outdated.

### Documentation
The documentation in docs/ is partly outdated. The documentation in docs/old is
outdated.


# SOP

Log in

    ssh to codon/slurm

Activate new codon software environment

    source /hps/software/users/ensembl/ensw/swenv/initenv default

Clone required repo: [ensembl-e2020-datafiles](https://github.com/Ensembl/ensembl-e2020-datafiles/)

    export BASE_DIR=/hps/software/users/ensembl/$TEAM/$USER
    cd $BASE_DIR
    git clone https://github.com/Ensembl/ensembl-e2020-datafiles/

 Install and activate py deps and set env variables used by nf pipeline

    cd $BASE_DIR/ensembl-e2020-datafiles
    python3 -m venv --system-site-packages venv
    . venv/bin/activate
    pip install -r requirements.txt

    export NOBACKUP_DIR=/home/app/ensembl_production_apps/ensembl-e2020-datafiles/nextflow/data
    export WORK_DIR=${NOBACKUP_DIR}/nextflow/datafile/work_dir
    export BASE_DIR=/hps/software/users/ensembl/repositories/${USER}
    export BASE_CONFIG_DIR=$BASE_DIR/ensembl-e2020-datafiles/nextflow/config
    export NCD_BUILD_PATH=${NOBACKUP_DIR}/nextflow/datafile/ncd-tools
    export OUTPUT_PATH=${NOBACKUP_DIR}/nextflow/datafile/release_${ENS_VERSION}

 Create Output Directory and nf workflow dir

    cd ${NOBACKUP_DIR}/nextflow/datafile
    mkdir -p $WORK_DIR


## Run all species, overwrite existing
    nextflow datafile.nf -c config/datafile.config -profile slurm \
    --factory_path $META_REPO_PATH/ensembl/production/metadata/api/factories/genomes.py \
    --output_path $OUTPUT_PATH/e2020-datafile-2024-03/ \
    --script_path $GIT_REPO_PATH/ensembl-e2020-datafiles/bin \
    --dbconnection_file $CONFIG_PATH/db-connection-secrets.json \
    --metadatadb_key meta --speciesdb_key species


## Run specific genome UUIDs, skip existing
    nextflow datafile.nf -c config/datafile.config -profile slurm \
    --factory_path $META_REPO_PATH/ensembl/production/metadata/api/factories/genomes.py \
    --output_path $OUTPUT_PATH/e2020-datafile-2024-03/ \
    --script_path $GIT_REPO_PATH/ensembl-e2020-datafiles/bin \
    --dbconnection_file $CONFIG_PATH/db-connection-secrets.json \
    --metadatadb_key meta --speciesdb_key species \
    --skipdone \
    --genome_uuid a73357ab-93e7-11ec-a39d-005056b38ce3,96156567-3c9f-4305-a3be-eacdb5dc4353,4aaf041d-5ab0-41e8-acd6-0abcc2a51029
