#!/usr/bin/env perl

# See the NOTICE file distributed with this work for additional information
# regarding copyright ownership.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

use warnings;
use strict;

use feature 'say';
binmode STDOUT, ':utf8';

use DBI;
use Digest::MD5;
use Digest::SHA;
use File::Basename;
use File::Path qw(make_path);
use Getopt::Long;
use MIME::Base64 qw(decode_base64);

# Dump sequence data from FASTA and merge in circularity from the metadata DB.
#
# Output format intentionally mirrors seq.hashes/chrom.hashes:
# name \t md5 \t sha512t24 hex trunc \t \t length \t is_circular
#
# This script is only for assembly sequence data. It preserves FASTA order,
# writes the concatenated sequence to seq.txt, and writes a seq.hashes file with
# the same checksum format as dump_from_fasta.pl plus the circularity flag. By
# default, checksums are read from the metadata DB. Use --validate_checksums to
# recalculate md5/SHA512 from FASTA and compare them with the metadata values.

my ($genome_uuid, $metadata_dbconn, $infile, $hashfile, $seqfile);
my $validate_checksums = 0;

GetOptions(
    "genome_uuid=s"        => \$genome_uuid,
    "metadata_dbconn=s"    => \$metadata_dbconn,
    "infile=s"             => \$infile,
    "hashfile=s"           => \$hashfile,
    "seqfile=s"            => \$seqfile,
    "validate_checksums!"  => \$validate_checksums,
) or die("Error in command line arguments\n");

for my $required (
    ["genome_uuid",     $genome_uuid],
    ["metadata_dbconn", $metadata_dbconn],
    ["infile",          $infile],
    ["hashfile",        $hashfile],
    ["seqfile",         $seqfile],
) {
    my ($name, $value) = @$required;
    die "Missing required argument --$name\n" if !defined($value) || $value eq "";
}

my ($dsn, $user, $password) = mysql_uri_to_dbi($metadata_dbconn);

my $dbh = DBI->connect(
    $dsn,
    $user,
    $password,
    {
        RaiseError => 1,
        PrintError => 0,
        AutoCommit => 1,
        mysql_enable_utf8mb4 => 1,
    }
) or die "Failed to connect to metadata DB\n";

my $rows_by_name = fetch_assembly_sequences($dbh, $genome_uuid);
$dbh->disconnect;

my $hash_path = dirname($hashfile);
make_path($hash_path);
open(my $outfh, ">", $hashfile) or die "Error opening hash file '$hashfile': $!";

my $seq_path = dirname($seqfile);
make_path($seq_path);
open(my $seqfh, ">", $seqfile) or die "Error opening sequence file '$seqfile': $!";

open(my $infh, "<", $infile) or die "Error opening input file '$infile': $!";
my $len = 0;
my $current;
my $seq = undef;
my $sequence_count = 0;

while (my $line = <$infh>) {
    chomp $line;
    if ($line =~ /^>/) {
        if ($current) {
            process_seq($current, $len, \$seq, $rows_by_name, $outfh, $seqfh, $validate_checksums);
            $sequence_count++;
        }
        $current = $line;
        $len = 0;
        $seq = undef;
        next;
    }
    $len += length($line);
    $seq .= $line;
}

die "No FASTA records found in '$infile'\n" if !$current;
process_seq($current, $len, \$seq, $rows_by_name, $outfh, $seqfh, $validate_checksums);
$sequence_count++;

close($infh) or die "Error closing input file '$infile': $!";
close($seqfh) or die "Error closing sequence file '$seqfile': $!";
close($outfh) or die "Error closing hash file '$hashfile': $!";

die "No sequences written for genome_uuid=$genome_uuid\n" if !$sequence_count;

sub fetch_assembly_sequences {
    my ($dbh, $uuid) = @_;

    my $sql = <<'SQL';
SELECT
    assembly_sequence.name,
    assembly_sequence.md5,
    assembly_sequence.sha512t24u,
    assembly_sequence.length,
    assembly_sequence.is_circular
FROM genome
JOIN assembly_sequence
  ON assembly_sequence.assembly_id = genome.assembly_id
WHERE genome.genome_uuid = ?
SQL

    my $sth = $dbh->prepare($sql);
    $sth->execute($uuid);

    my %rows_by_name;
    while (my $row = $sth->fetchrow_hashref) {
        my $name = $row->{name};
        die "assembly_sequence row with empty name for genome_uuid=$uuid\n"
            if !defined($name) || $name eq "";
        die "Duplicate assembly_sequence name '$name' for genome_uuid=$uuid\n"
            if exists $rows_by_name{$name};
        $rows_by_name{$name} = $row;
    }

    die "No assembly_sequence rows found for genome_uuid=$uuid\n" if !%rows_by_name;
    return \%rows_by_name;
}

sub mysql_uri_to_dbi {
    my ($uri) = @_;

    my ($user_info, $host, $port, $database) =
        $uri =~ m{\Amysql://([^@]*)@([^/:?]+)(?::(\d+))?/([^?]+)(?:\?.*)?\z};

    die "Unsupported metadata DB URI. Expected mysql://user[:password]\@host[:port]/database\n"
        if !defined($user_info) || !defined($host) || !defined($database);

    my ($user, $password) = split /:/, $user_info, 2;
    $port ||= 3306;
    $password = "" if !defined $password;

    $user = uri_unescape($user);
    $password = uri_unescape($password);
    $host = uri_unescape($host);
    $database = uri_unescape($database);

    my $dsn = "DBI:mysql:database=$database;host=$host;port=$port";
    return ($dsn, $user, $password);
}

sub uri_unescape {
    my ($value) = @_;
    $value =~ s/%([0-9A-Fa-f]{2})/chr(hex($1))/eg;
    return $value;
}

sub calc_sums {
    my ($seq_ref) = @_;

    my $sha = Digest::SHA->new(512);
    my $md5 = Digest::MD5->new;
    $md5->add($$seq_ref);
    $sha->add($$seq_ref);
    my $sha_trunc = substr($sha->hexdigest, 0, 48);
    my $md5_sum = $md5->hexdigest;

    return ($md5_sum, $sha_trunc);
}

sub sha512t24u_to_hex {
    my ($value) = @_;

    die "Missing sha512t24u for genome_uuid=$genome_uuid\n"
        if !defined($value) || $value eq "";
    die "Malformed sha512t24u value '$value' for genome_uuid=$genome_uuid\n"
        if $value !~ /\A[A-Za-z0-9_-]+={0,2}\z/;

    my $encoded = $value;
    $encoded =~ tr/-_/+\//;
    $encoded .= "=" x ((4 - length($encoded) % 4) % 4);

    my $decoded = decode_base64($encoded);
    die "sha512t24u value '$value' decoded to " . length($decoded) . " bytes, expected 24\n"
        if length($decoded) != 24;

    return unpack("H*", $decoded);
}

sub process_seq {
    my ($desc, $len, $seq_ref, $rows_by_name, $hashfh, $seqfh, $validate_checksums) = @_;

    $desc =~ /ENSEMBL:(\S+)/;
    my $name = $1 // "No data";
    my $row = $rows_by_name->{$name};
    die "No assembly_sequence row found for genome_uuid=$genome_uuid name=$name\n" if !$row;

    for my $field (qw(md5 sha512t24u length)) {
        die "Missing $field for genome_uuid=$genome_uuid name=$name\n"
            if !defined($row->{$field}) || $row->{$field} eq "";
    }

    die "Length mismatch for genome_uuid=$genome_uuid name=$name: FASTA has $len, metadata DB has $row->{length}\n"
        if $len != $row->{length};

    my $md5_sum = $row->{md5};
    my $sha_trunc = sha512t24u_to_hex($row->{sha512t24u});

    if ($validate_checksums) {
        my ($calculated_md5, $calculated_sha) = calc_sums($seq_ref);
        die "MD5 mismatch for genome_uuid=$genome_uuid name=$name: FASTA has $calculated_md5, metadata DB has $md5_sum\n"
            if $calculated_md5 ne $md5_sum;
        die "SHA512t24 mismatch for genome_uuid=$genome_uuid name=$name: FASTA has $calculated_sha, metadata DB has $sha_trunc\n"
            if $calculated_sha ne $sha_trunc;
    }

    my $is_circular = $row->{is_circular} ? 1 : 0;
    say $hashfh join(
        "\t",
        $name,
        $md5_sum,
        $sha_trunc,
        "",
        $len,
        $is_circular,
    ) or die "Write failed: $!";
    print $seqfh $$seq_ref or die "Write failed: $!";
}
