#!/usr/bin/env perl
use warnings;
use strict;

use feature 'say';
binmode STDOUT, ':utf8';

use File::Spec::Functions qw(catfile);

use Path::Tiny qw/path/;
use lib path($0)->absolute->parent(2)->child('lib')->stringify;

use Options qw(config_option output_option skipdone_option);
use Genome;

my $conf = config_option();
my $output = output_option();
my $skipdone = skipdone_option();

my $genome = Genome->new('mysql://dummy', $conf, $output);

# The program that does the seekable ZStandard compression.
my $COMPRESSOR = 't2sz';

do_species($genome);
### End of main

sub do_species {
    my ($genome) = @_;

	my $path = $genome->common_files_path->stringify();
	my $chrom_file = catfile($path, 'seqs/seq.txt.zst');

    my $genome_uuid = $genome->genome_uuid();
	if ($skipdone and -f $chrom_file and ! -z $chrom_file) {
        say "[compress] Data for genome_uuid $genome_uuid exists, skipping";
        return;
    }
    my $sequence_path = $genome->seqs_path->stringify();
    my $sequence_file = catfile($sequence_path, 'seq.txt');
    say "[compress] Applying seekable zstandard compression to sequence data.";
    my @cmd = ($COMPRESSOR, qw(-l 1 -T 1 -s 512K), '-o', "$sequence_file.zst", $sequence_file);
    if (system(@cmd)) {
        say STDERR "Failed to run command: @cmd";
        if ($? == -1) {
            die "Failed to exec command: $!";
        } elsif ($? & 127) {
            die sprintf "Child died with signal %d, %s coredump",
                ($? & 127),  ($? & 128) ? 'with' : 'without';
        } else {
            die sprintf "Child exited with value %d", $? >> 8;
        }
    }
}
