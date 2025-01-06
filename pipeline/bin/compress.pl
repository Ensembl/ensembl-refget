#!/usr/bin/env perl

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
