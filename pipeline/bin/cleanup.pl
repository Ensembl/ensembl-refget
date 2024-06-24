#!/usr/bin/env perl
use warnings;
use strict;

use feature 'say';

use Path::Tiny qw/path/;
use lib path($0)->absolute->parent(2)->child('lib')->stringify;
use File::Path qw(remove_tree);;
use Options qw(dbconn_option config_option output_option command_line_arguments);
use Genome;

my $genome = Genome->new(dbconn_option(), config_option(), output_option());
do_species($genome);
### End of main

# Process one species+accession. die()s on errors
sub do_species {
    my ($genome) = @_;

    my $species = $genome->{species};
    say "[cleanup] Cleaning up temporary files for species $species";

    my @remove = $genome->temporary_files_path()->stringify();
    push @remove, $genome->gc_path->child('gc.wig')->stringify();
    push @remove, $genome->contigs_path->child('contigs.bed')->stringify();
    push @remove, $genome->genes_transcripts_path->child('genes.bed')->stringify();
    push @remove, $genome->genes_transcripts_path->child('transcripts.bed')->stringify();
    push @remove, $genome->genes_transcripts_path->child('repeats.bed')->stringify();
    push @remove, $genome->genes_transcripts_path->child('simplefeatures.bed')->stringify();
    #    push @remove, $genome->chrom_sizes_path->stringify();
    #    push @remove, $genome->chrom_hashes_path->stringify();
    #    push @remove, $genome->jump_path->child('jump.txt')->stringify();
    remove_tree(@remove, {verbose => 0});
}

