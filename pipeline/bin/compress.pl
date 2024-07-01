#!/usr/bin/env perl
use warnings;
use strict;

use feature 'say';

use Getopt::Long;

# The program that does the seekable ZStandard compression.
my $COMPRESSOR = 't2sz';

my ($infile, $outfile);

GetOptions(
    "infile=s" => \$infile,
    "outfile=s" => \$outfile,
) or die("Error in command line arguments\n");

say "[compress] Applying seekable zstandard compression to sequence data.";
my @cmd = ($COMPRESSOR, qw(-l 1 -T 1 -s 512K), '-o', $outfile, $infile);

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
