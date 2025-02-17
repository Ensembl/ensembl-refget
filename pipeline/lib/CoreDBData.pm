#!/usr/bin/env perl
use warnings;
use strict;

package CoreDBData;
use Exporter 'import';
use DBI;
use DBD::mysql;

use Path::Tiny qw(path);
use lib path($0)->absolute->parent(2)->child('lib')->stringify;
use Options qw(command_line_arguments config_option);

use feature 'say';

our @EXPORT_OK = qw(fetch_cs_mappings fetch_species_id);

# Fetches species ID (dbID) for a given species
# Dies if not found or if multiple matches found
# Due to changes in the metadata DB, the
# species.prodictiopn_name is currently not available
sub fetch_species_id {
    my ($dbh, $species) = @_;
    my ($found_species_id);

    my $sql = "select a.species_id, a.meta_value as species from meta a
    where a.meta_key = 'species.production_name'";

    my $sth = $dbh->prepare($sql);
    $sth->execute;

    while (my $ref = $sth->fetchrow_arrayref()) {
        my ($species_id, $db_species, $db_gca) = @$ref;

        if ($db_species eq $species) {
            die "Multiple matches found for species $species in database " . $dbh->{Name} if defined $found_species_id;
            $found_species_id = $species_id;
        }
    }
    unless (defined $found_species_id) {
        die "No match found for species $species in database " . $dbh->{Name};
    }

    return $found_species_id;
}


# Find shortest coordinate system mappings from toplevel coordinate systems to
# sequence level coordinate systems
sub fetch_cs_mappings {
    my ($dbh, $species_id) = @_;

    # mapping info
    my %map;
    # coordinate system info by cs name
    my %cs;
    # reverse mapping cs id to name
    my %cs_rev;

    # store which cs are toplevel
    my %toplevel_cs;

    # coordinate system ids that are default and have toplevel seq_regions. This
    # is where the algorithm starts
    my %starts;
    # coordinate system ids at sequence level. This is where the algorithm stops
    my %stops;

    my ($sql, $rows);
    # select and store toplevel coord system ids
    $sql = "
        select sr1.coord_system_id from seq_region sr1
        inner join seq_region_attrib sra1 on sr1.seq_region_id = sra1.seq_region_id
        inner join attrib_type aty1 on sra1.attrib_type_id = aty1.attrib_type_id and aty1.code = 'toplevel'
        inner join coord_system c1 on sr1.coord_system_id = c1.coord_system_id
        where c1.species_id = ?
        group by sr1.coord_system_id;
    ";

    $rows = $dbh->selectall_arrayref($sql, {Slice => {}}, $species_id);
    for my $row (@$rows) {
        $toplevel_cs{$row->{'coord_system_id'}} = 1;
    }

    # select and store coord_system info
    $sql = "
        select coord_system_id, name, version, attrib
        from coord_system
        where species_id = ?
        order by coord_system_id
    ";
    $rows = $dbh->selectall_arrayref($sql, {Slice => {}}, $species_id);

    for my $row (@$rows) {
        my %attrs = map {$_ => 1} split (",",  $row->{'attrib'} // '');
        my $is_default = $attrs{'default_version'} // 0;
        my $is_sq_lv = $attrs{'sequence_level'} // 0;
        my $id = $row->{'coord_system_id'};
        my $name = $row->{'name'};
        my $version = $row->{'version'};
        my $cs_name_ver = $name . ($version ? ":$version" : '');
        $version //= 'NULL';

        $cs{$cs_name_ver} = {'id' => $id, 'is_default' => $is_default, 'is_sq_lv' => $is_sq_lv};
        $cs_rev{$id} = $cs_name_ver;
        if ($toplevel_cs{$id} and $is_default) {
            $starts{$id} = 1;
        }
        if ($is_sq_lv) {
            $stops{$id} = 1;
        }
    }
    die "No toplevel coordinate systems found" unless keys %starts;
    die "No sequence_level coordinate systems found" unless keys %stops;

    $sql = "
        select meta_value
        from meta
        where meta_key = 'assembly.mapping'
            and species_id = ?
    ";
    $rows = $dbh->selectall_arrayref($sql, { Slice => {} }, $species_id);

    # The values for assembly.mapping look like this:
    # scaffold:GRCm39#contig
    # scaffold:GRCm39#scaffold:GRCm38#supercontig:NCBIM37
    # There must be two and there may be three coord_systems
    for my $row (@$rows) {
        my $val = $row->{'meta_value'};
        my @elements = split(/[|#]/, $val);
        my $from = $elements[0];
        my $fromid = $cs{$from}->{'id'};
        my $to = $elements[1];
        my $toid = $cs{$to}->{'id'};
        push @{$map{$fromid}}, $toid;

        if ($elements[2]) {
            my $from = $elements[1];
            my $fromid = $cs{$from}->{'id'};
            my $to = $elements[2];
            my $toid = $cs{$to}->{'id'};
            push @{$map{$fromid}}, $toid;
        }
    }
    my $paths;

    # No mappings - species only has a primary_assembly. Mappings - build path/s
    if (! @$rows) {
        $paths = [map {[$_]} keys %starts];
    } else {
        $paths = find_mapping_toplevel_to_seq([sort keys %starts], \%stops, \%map, \%cs_rev);
    }
    die "No valid coordinate system mapping paths found" unless @$paths;

    return $paths;
}


# Find mappings from toplevel seq regions to seq-level seq regions
sub find_mapping_toplevel_to_seq {
    # $starts: ref to array of coordinate system ids that are
    # default and that have corresponding toplevel seq_regions
    # $stops: {id => 1}; ref to hash of coordinate system ids
    # $map: {id => [id, ...]}; ref to hash with key: coord_sys_id and value: ref
    # to array of all other coord_sys_ids where there exists a mapping
    my ($starts, $stops, $map) = @_;

    # Finished paths will go here. E.g.:
    # ([1,2,3],[2,3])
    my @out;

    # Unfinished paths go here. E.g.:
    # ([1,2],[2])
    my @work = map {[$_]} @$starts;

    my %uniq_path;

    # For arbitrary length paths, this would be a while(1). But we are only
    # looking for a max length of three because the databases and API currently
    # only support mappings up to this depth
    for (1 .. 3) {
        my @newwork;

        # Fetch and remove every unfinished item from the work array
        while (my $arr = shift @work) {
            # get the inner array
            my @inner = @$arr;

            # get the last element
            my $start = $inner[-1];

            # Check if we are at sequence level. If so, the path is finished and
            # goes to @out
            if (exists $stops->{$start}) {
                my $path_key = join("|", @inner);
                unless (exists $uniq_path{$path_key}) {
                    $uniq_path{$path_key} = 1;
                    push @out, [@inner];
                }
                next;
            }

            my @targets;
            # Find if there are targets to map to
            if (exists $map->{$start}) {
                @targets = @{$map->{$start}};
            }
            # for each target, copy the complete current path and append the new
            # coord_sys
            foreach my $tgt (@targets) {
                push @newwork, [@inner, $tgt];
            }

            # There are no more targets and we are not at sequence level, since we
            # checked that before. Discard this path.
            if (! @targets) {
                next;
            }
        }
        # If we found new work, run the loop again, else break
        last unless @newwork;
        @work = @newwork;
    }

    # pick out the shortest path - there might be multiple ways from one coord_sys to another
    my %shortest;
    foreach my $arr (@out) {
        my @path = @$arr;
        my $start = $path[0];
        if (! exists $shortest{$start} or (exists $shortest{$start} and @{$shortest{$start}} > @path)) {
            $shortest{$start} = \@path;
        }
    }

    return [values %shortest];
}

1;
