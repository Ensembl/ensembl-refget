#!/usr/bin/env perl
use warnings;
use strict;

use feature 'say';
binmode STDOUT, ':utf8';

use Digest::MD5;
use Digest::SHA;
use Getopt::Long;
use File::Basename;
use File::Path qw(make_path);

# This script prepares data for the refget server (ensembl-refget).
# Reads in a multi-sequence fasta file (e.g. cdna.fa).
# Creates two files, one with only the sequence and one with tab separated data
# that resembles a 'chrom' file:
# (name \t md5 hash \t sha512t24 hash \t \t length \t).
my ($infile, $seqfile, $hashfile);

GetOptions(
    "infile=s" => \$infile,
    "seqfile=s" => \$seqfile,
    "hashfile=s" => \$hashfile
) or die("Error in command line arguments\n");


my $len = 0;
my $current;
my $seq = undef;

open (my $infh, '<', $infile) or die "Error opening input file '$infile': $!";
my $seq_path = dirname($seqfile);
# It's OK if zero dirs are created, so don't die
make_path($seq_path);
open (my $seqfh, '>', $seqfile) or die "Error opening sequence file '$seqfile': $!";
open (my $hashfh, '>', $hashfile) or die "Error opening hash file '$hashfile': $!";

while (<$infh>) {
    chomp;
    if (/^>/) {
        if ($current) {
            process_seq($current, $len, \$seq);
        }
        $current = $_;
        $len = 0;
        $seq = undef;
        next;
    }
    $len += length;
    $seq .= $_;
}
process_seq($current, $len, \$seq);

close($infh) or die "Error closing file '$infile': $!";
close($seqfh) or die "Error closing file '$seqfile': $!";
close($hashfh) or die "Error closing file '$hashfile': $!";
# End of main

sub calc_sums {
    my ($sequence_path, $seq_ref) = @_;

    my $sha = Digest::SHA->new(512);
    my $md5 = Digest::MD5->new;
    $md5->add($$seq_ref);
    $sha->add($$seq_ref);
    my $sha_trunc = substr($sha->hexdigest, 0, 48);
    my $md5_sum = $md5->hexdigest;

    return ($md5_sum, $sha_trunc);
}

sub process_seq {
    my ($desc, $len, $seq) = @_;
    $desc =~ /ENSEMBL:(\S+)/;
    my $name = $1 // 'No data';
    my ($md5_sum, $sha_trunc) = calc_sums(undef, $seq);

    say $hashfh "$name\t$md5_sum\t$sha_trunc\t\t$len\t" or die "Write failed: $!";
    print $seqfh $$seq or die "Write failed: $!";
}
