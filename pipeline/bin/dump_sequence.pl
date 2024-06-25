#!/usr/bin/env perl
use warnings;
use strict;

use feature 'say';
binmode STDOUT, ':utf8';

use DBI;
use DBD::mysql;
use Digest::MD5 'md5_hex';
use Digest::SHA 'sha512_hex';
use File::Path qw(make_path);
use File::Spec::Functions qw(rel2abs catfile);
use File::Basename qw(dirname);
use Bio::EnsEMBL::Utils::Sequence qw(reverse_comp);

use Path::Tiny qw/path/;
use lib path($0)->absolute->parent(2)->child('lib')->stringify;

use Options qw(dbconn_option config_option output_option skipdone_option command_line_arguments);
use CoreDBData qw(fetch_cs_mappings fetch_species_id);
use Genome;

my $dbconn = dbconn_option();
my $conf = config_option();
my $output = output_option();
my $skipdone = skipdone_option();

my $genome = Genome->new($dbconn, $conf, $output);

do_species($genome);

### End of main

# 1 Fetch data for report plus additional data
# - write report - this is sorted by karyotype
# - keep the report data in memory
# 2 fetch sequence for each region name in the report
# - optionally write out sequence files
# - calculate checksums
# - keep the calculated sums in memory
# - calculate %GC data
# - build the 'gc.bw' bigWig file with the GC data
# 3 write chrom files keeping the sort order from the report
sub do_species {
    my ($genome) = @_;

	my $path = $genome->common_files_path->stringify();
	my $chrom_file = catfile($path, 'chrom.hashes');
    my $genome_uuid = $genome->genome_uuid();

	if ($skipdone and -f $chrom_file and ! -z $chrom_file) {
        say "[dump_sequence] Data for genome_uuid $genome_uuid exists, skipping";
        return;
    }

    my $dbh = $genome->get_dbh();

    say "[dump_sequence] Fetch species ID for $genome_uuid";
    my $species = $genome->species();
    my $species_id = fetch_species_id($dbh, $species);
    say "[dump_sequence] Fetch region data";
    my ($report, $report_data_list) = fetch_report($dbh, $species_id);
    # write report to file
    # write_report_file($genome, $report);

    say "[dump_sequence] Fetch sequence data, calculate hashes";
    my $checksum_hash = fetch_and_write_checksum($dbh, $genome, $report_data_list, $species_id);
    say "[dump_sequence] Write chrom file";
    write_chrom_files($genome, $report_data_list, $checksum_hash);
    say "[dump_sequence] Done";

    $dbh->disconnect;
}

# Write report file. $report is a string with the full report data
sub write_report_file {
    my ($genome, $report) = @_;
    my $genome_uuid = $genome->genome_uuid();

    my $report_path = $genome->common_files_path->stringify();
    make_path($report_path);

    my $report_file = catfile($report_path, 'genome_report.txt');

    open (my $fh, '>',  $report_file) or die "Error opening '$report_file': $!";
    print $fh $report;
    close $fh or die "Error closing '$report_file': $!";
}

# Write 'chrom' files. Takes data in order from $report_data_list and the hash sums from $checksum_hash
sub write_chrom_files {
    my ($genome, $report_data_list, $checksum_hash) = @_;
    my $genome_uuid = $genome->genome_uuid();

    my $path = $genome->common_files_path->stringify();
    make_path($path);

    my $last_name;
    my @chrom_hashes;
    foreach my $item (@$report_data_list) {
        my ($seq_region_id, $is_direct, $seq_region_name, $seq_region_length, undef, undef) = @$item;
        my $hashref = $checksum_hash->{$seq_region_name};
        unless ($hashref) {
            die "No checksums found for seq_region $seq_region_name. The likely cause is bad data in the DB.";
            next;
        }
        my ($md5_sum, $sha_sum) = @{$checksum_hash->{$seq_region_name}};

        push (@chrom_hashes, join("\t", $seq_region_name, $md5_sum, $sha_sum, '', $seq_region_length, ''), "\n");
    }

    my $chrom_file = catfile($path, 'chrom.hashes');
    open(my $fh, '>', $chrom_file) or die "Error opening '$chrom_file': $!";
    foreach my $line (@chrom_hashes) {
        print $fh $line;
    }
    close $fh or die "Error closing '$chrom_file': $!";
}

# Fetches data for the genome_report.txt
sub fetch_report {
    my ($dbh, $species_id) = @_;

    my $sql = "
        select sr.seq_region_id,
            sr.name,
            sr.length,
            cs.name,
            CASE WHEN (cs.attrib like '%sequence_level%') THEN 1 else 0 END as is_direct,
            CASE WHEN sra3.value IS NULL AND cs.name = 'chromosome' THEN 'assembled-molecule' ELSE 'unlocalized-scaffold' END as sequence_role
        from coord_system cs
        join seq_region sr on (cs.coord_system_id = sr.coord_system_id)
        join seq_region_attrib sra1 on (sr.seq_region_id = sra1.seq_region_id)
        join attrib_type at1 on (sra1.attrib_type_id = at1.attrib_type_id)
        left join seq_region_attrib sra2 on (sr.seq_region_id = sra2.seq_region_id and sra2.attrib_type_id = (select attrib_type_id from attrib_type where code = 'karyotype_rank'))
        left join seq_region_attrib sra3 on (sr.seq_region_id = sra3.seq_region_id and sra3.attrib_type_id = (select attrib_type_id from attrib_type where code = 'non_ref'))
        where at1.code = 'toplevel'
        and cs.species_id = ?
        group by sr.seq_region_id
        order by IFNULL(CONVERT(sra2.value, UNSIGNED), 5e6) asc, sr.name
    ";

    my $report = "# Sequence-Name	Sequence-Role	Assigned-Molecule	Assigned-Molecule-Location/Type	GenBank-Accn	Relationship	RefSeq-Accn	Assembly-Unit	Sequence-Length	UCSC-style-name\n";

    my $sth = $dbh->prepare($sql);
    $sth->bind_param(1, $species_id);
    $sth->execute;
    my $report_data_list = [];

    while (my $ref = $sth->fetchrow_arrayref()) {
        my ($seq_region_id, $seq_region_name,  $seq_region_length, $coord_sys_name, $is_direct, $sequence_role) = map { defined $_ ? $_ : '-' } @{$ref};
        if (@$report_data_list > 1 and $report_data_list->[-1]->[0] == $seq_region_id) {
            warn "Found duplication, seq_region_id $seq_region_id, seq_region_name $seq_region_name. Skipping.";
            next;
        }
        push(@$report_data_list, [$seq_region_id, $is_direct, $seq_region_name, $seq_region_length]);

        my @report_list = ($seq_region_name, $sequence_role, $seq_region_name, $coord_sys_name, '', '=', '', 'Primary Assembly', $seq_region_length, '');
        $report .= join("\t", @report_list) . "\n";
    }

    return ($report, $report_data_list);
}

# Fetches sequence data for the species.
# Calls calc_sums_write_file to calculate hashes and write out sequence data.
sub fetch_and_write_checksum {
    my ($dbh, $genome, $report_data_list, $species_id) = @_;
    my $genome_uuid = $genome->genome_uuid();

    my $sums_hash;

    my $sequence_path = $genome->seqs_path->stringify();
    make_path($sequence_path);

    # Query which coordinate systems are involved and then create SQL
    # constraints for these
    my $paths = fetch_cs_mappings($dbh, $species_id);

    my ($join_constraint_1, $join_constraint_2, $join_constraint_3, $where_constraint);
    {
        # All starting coord_sys_ids go into pathlen1, all paths of length 2 or 3
        # go into pathlen2 and only paths of length 3 go into pathlen3
        my (@pathlen1, @pathlen2, @pathlen3);

        my %colnames = (
            0 => 'sr1.coord_system_id = ',
            1 => 'sr2.coord_system_id = ',
            2 => 'sr3.coord_system_id = '
        );

        foreach my $pathref (@$paths) {
            my @path = @{$pathref};
            my $pathlen = @path;
            if ($pathlen > 3) {
                die "Mapping path too long. SQL statement currently does not support this";
            }

            push @pathlen1, $path[0];
            if ($pathlen >= 2) {
                push @pathlen2, $pathref;
            }
            if ($pathlen == 3) {
                push @pathlen3, $pathref;
            }
        }
        $join_constraint_1 = "and sr1.coord_system_id in (" . join(", ", @pathlen1) . ")";

        # We have arrays like [2,3] in @pathlen2 - the coord_sys_id for
        # seq_region sr1 and sr2. But we may not want to join the assembly
        # table, so we may not actually have values for sr2. Therefore, we only
        # pick the first element out of the array and add a constraint for it
        # (the 0..0 part). The full constraint goes into the where clause
        my $tmp_constraint_2;
        my @tmp_conditions_2;
        for my $item (@pathlen2) {
            my @tmp2;
            my @row = @$item;
            for my $i (0 .. 0) {
                push @tmp2, $colnames{$i} . $row[$i];
            }
            my $str2 = "(" . join(" and ", @tmp2) . ")";
            push @tmp_conditions_2, $str2;
        }
        $tmp_constraint_2 =  "(" . join(" or ", @tmp_conditions_2) . ")";
        $join_constraint_2 = @tmp_conditions_2 ? "and IF($tmp_constraint_2, TRUE, FALSE)" : 'and FALSE';

        # Similar to the above, we have arrays like [2,3,4] in @pathlen3 - the coord_sys_id for
        # seq_region sr1, sr2 and sr3. We may not want to join the assembly
        # table a2, so we may not actually have values for sr3. Therefore, we only
        # pick the first two elements out of the array and add a constraint for it
        # (the 0..1 part)
        my $tmp_constraint_3;
        my @tmp_conditions_3;
        for my $item (@pathlen3) {
            my @tmp3;
            my @row = @$item;
            for my $i (0 .. 1) {
                push @tmp3, $colnames{$i} . $row[$i];
            }
            my $str3 = "(" . join(" and ", @tmp3) . ")";
            push @tmp_conditions_3, $str3;
        }
        $tmp_constraint_3 =  "(" . join(" or ", @tmp_conditions_3) . ")";
        $join_constraint_3 = @tmp_conditions_3 ? "and IF($tmp_constraint_3, TRUE, FALSE)" : 'and FALSE';

        # Construct where constraint
        my @join;
        foreach my $pathref (@$paths) {
            my @path = @$pathref;
            my @conditions;
            for my $i (0 .. $#path) {
                push @conditions, $colnames{$i} . $path[$i]
            }
            push @join, '(' . join(" and ", @conditions) . ')';
        }
        if (@join) {
            $where_constraint = 'and (' . join(" or ", @join). ')';
        }
    }

    # This selects all sequence for all chromosomes/chrom-like things and all
    # scaffolds / supercontigs / scaffold-like things. We join the assembly
    # table two times. The assembly table may have no entries for the first or
    # the second join. This is handled later in the code, as well as properly
    # joining the sequence.
    my $sql = "
        select
            sr1.name as 'chrom or primary-assembly name',
            d1.sequence as seq1,
            a1.asm_start as start2,
            a1.asm_end as end2,
            a1.cmp_start as cstart2,
            a1.ori as strand2,
            d2.sequence as seq2,
            a2.asm_start as start3,
            a2.asm_end as end3,
            a2.cmp_start as cstart3,
            a2.ori as strand3,
            d3.sequence as seq3
        from seq_region sr1
        inner join coord_system c1 on sr1.coord_system_id = c1.coord_system_id $join_constraint_1
        inner join seq_region_attrib sra1 on sr1.seq_region_id = sra1.seq_region_id
        inner join attrib_type aty1 on sra1.attrib_type_id = aty1.attrib_type_id and aty1.code = 'toplevel'
        left join seq_region_attrib sra2 on (sr1.seq_region_id = sra2.seq_region_id and
            sra2.attrib_type_id = (select attrib_type_id from attrib_type where code = 'karyotype_rank'))
        left join dna d1 on d1.seq_region_id = sr1.seq_region_id
        left join assembly a1 on a1.asm_seq_region_id = sr1.seq_region_id $join_constraint_2
        left join seq_region sr2 on a1.cmp_seq_region_id = sr2.seq_region_id
        left join dna d2 on d2.seq_region_id = sr2.seq_region_id
        left join assembly a2 on a2.asm_seq_region_id = sr2.seq_region_id $join_constraint_3
        left join seq_region sr3 on a2.cmp_seq_region_id = sr3.seq_region_id
        left join dna d3 on d3.seq_region_id = sr3.seq_region_id
        where c1.species_id = ?
            $where_constraint
        order by IFNULL(CONVERT(sra2.value, UNSIGNED), 5e6) asc, sr1.name, a1.asm_start, sr2.name, a2.asm_start;
    ";

    #print STDERR "$sql\nWith bind val: $species_id";

    my @bind_values = ($species_id);

    my ($sequence, $dbsequence_length, $this_name, $db_start, $last_name, $last_start, $seq_start);

    my $rows = 0;
    $last_start = 0;
    $seq_start = 1;

    my $sth = $dbh->prepare($sql);
    $sth->execute(@bind_values);

    my $iter = 0;
    while (1) {
        my $ref = $sth->fetchrow_arrayref();

        my $new_sequence;

        if ($ref) {
            my ($name1, undef, $start2, $end2, $cstart2, $strand2, undef, $start3, $end3, $cstart3, $strand3, undef)
                = @$ref;
            my $seq1 = \$ref->[1];
            my $seq2 = \$ref->[6];
            my $seq3 = \$ref->[11];

            if ($$seq1) {
                $new_sequence = $seq1;
                $db_start = 1;
            } elsif ($$seq2) {
                $new_sequence = $seq2;
                $dbsequence_length = $end2 - $start2 + 1;
                $db_start = $start2;
                if ($strand2 == 1) {
                    $$seq2 = substr($$seq2, $cstart2 - 1, $dbsequence_length);
                } elsif ($strand2 == -1) {
                    $$seq2 = substr($$seq2, $cstart2 - 1, $dbsequence_length);
                    reverse_comp($seq2);
                } else {
                    die "Strand is not 1 or -1, instead we got '$strand2'";
                }
            } elsif ($$seq3) {
                $new_sequence = $seq3;
                $dbsequence_length = $end3 - $start3 + 1;
                $db_start = $start2 + $start3 - 1;
                if ($strand3 == 1) {
                    $$seq3 = substr($$seq3, $cstart3 - 1, $dbsequence_length);
                } elsif ($strand3 == -1) {
                    $$seq3 = substr($$seq3, $cstart3 - 1, $dbsequence_length);
                    reverse_comp($seq3);
                } else {
                    die "Strand is not 1 or -1, instead we got '$strand3'";
                }
            } else {
                die "No sequence found in DB";
            }

            # Sanity check
            die "Error while assembling sequence - start coord smaller than previous start coord."
                unless ($db_start > $last_start);
            $this_name = $name1;

            $rows++;
        }
        if (! defined $ref or ($this_name and $last_name and $this_name ne $last_name)) {
            # Hashsums are stored in a hash by seq_region_id. They'll be needed
            # later to write out the chrom files
            # $row is: [$seq_region_id, $is_direct, $seq_region_name, $seq_region_length, $insdc_synonym, $ucsc_synonym]
            my $report_name = $report_data_list->[$iter]->[2];
            die "Different ordering in report and DB result" unless $report_name eq $last_name;
            my $report_len = $report_data_list->[$iter]->[3];

            my $seq_len = length($sequence);
            my $gap = ($report_len - $seq_len);
            if ($gap) {
                if ($gap < 0) {
                    die "Error. Gap can not be negative. seq_region name $last_name, " .
                        "chrom len from report $report_len, seq len $seq_len";
                }
                $sequence .= 'N' x $gap;
            }

            my ($md5_sum, $sha_trunc) = calc_sums_write_file($sequence_path, \$sequence);
            $sums_hash->{$last_name} = [$md5_sum, $sha_trunc];

            $last_start = 0;
            $sequence = '';
            $seq_start = 1;
            $iter++;
        }

        last unless defined $ref;
        my $gap = ($db_start - $seq_start);
        if ($gap) {
            if ($gap < 0) {
                die "Error. Gap can not be negative. seq_region name $this_name, " .
                    "db_start $db_start, seq_start $seq_start" if $gap < 0;
            }
            $sequence .= 'N' x $gap;
            $seq_start += $gap;
        }

        $sequence .= $$new_sequence;
        $seq_start += length($$new_sequence);

        $last_name = $this_name;
    }

    unless ($rows) {
        die "No sequence data for genome ID $genome_uuid in DB " . $dbh->{Name};
    }

    $sth = undef;

    return $sums_hash;
}


# Calculate the hash sums for a sequence. Optionally write to disk, where the
# file name is the MD5 hash sum.
sub calc_sums_write_file {
    my ($sequence_path, $seq_ref) = @_;

    my $sha = Digest::SHA->new(512);
    my $md5 = Digest::MD5->new;
    $md5->add($$seq_ref);
    $sha->add($$seq_ref);
    my $sha_trunc = substr($sha->hexdigest, 0, 48);
    my $md5_sum = $md5->hexdigest;

    my $sequence_file = catfile($sequence_path, 'seq.txt');
    open (my $fh, '>>', $sequence_file) or die "Error opening '$sequence_file': $!";
    print $fh $$seq_ref;
    close ($fh) or die "Error closing file '$sequence_file': $!";

    return ($md5_sum, $sha_trunc);
}

