#!/usr/bin/env bash
# This file sets up the environment for the pipeline. Must be sourced.

# We need Perl plus requirements, Python plus requirements
#
# We expect the Python requirements to be in the dir "venv" and Perl deps are in
# ~/perl5

[[ $0 != $BASH_SOURCE ]] || (echo "Must be sourced"; exit 1)

export PATH=/hps/software/users/ensembl/ensw/mysql-cmds/ensembl/bin:$PATH
source /hps/software/users/ensembl/ensw/swenv/env-config/prod-base/loader
source /hps/software/users/ensembl/ensw/swenv/env-config/prod-py-3-10/loader
source /hps/software/users/ensembl/ensw/swenv/env-config/prod-perl-5-26/loader
# Local Perl
export PERL5LIB=~/r/ensembl/modules:$PERL5LIB
eval $(perl -I ~/perl5/lib/perl5/ -Mlocal::lib)

export BASE_DIR=$(dirname $(readlink -f $BASH_SOURCE))
export VENV_DIR=$BASE_DIR/venv
export NF_DIR=$BASE_DIR/nextflow
export NF_CONFIG_DIR=$NF_DIR/config
export SCRIPT_DIR=$BASE_DIR/bin
export NOBACKUP_DIR=/hps/nobackup/flicek/ensembl/infrastructure/$USER/ensembl-refget

echo BASE_DIR=$BASE_DIR
echo VENV_DIR=$VENV_DIR
echo NF_DIR=$NF_DIR
echo NF_CONFIG_DIR=$NF_CONFIG_DIR
echo SCRIPT_DIR=$SCRIPT_DIR
echo NOBACKUP_DIR=$NOBACKUP_DIR

# py dependencies, especially for the metadata DB
. $VENV_DIR/bin/activate
