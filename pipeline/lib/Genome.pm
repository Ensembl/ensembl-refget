package Genome;

use strict;
use warnings;

use Path::Tiny qw(path);
use DBI;
use JSON;

my $dbconn;
my $conf;
my $output;

sub new {
    my $class = shift;
    $dbconn = shift or die "Need dbconn descriptor";
    my $confjson = shift or die "Need conf hash";
    $output = shift or die "Need output path";
    die "Need db connection string, e.g. 'mysql://user\@host:port/', got $dbconn" unless ($dbconn and $dbconn =~ m{mysql://.+});
    die 'Need conf json string, e.g. {"genome_uuid": ..., "species": ...}' unless $confjson;
    die "Need output path" unless $output and -d $output;

    $conf = decode_json($confjson);
    #    The JSON is expected to have this structure:
    #    {"genome_uuid": "ffe85b2a-7741-4fbc-9c99-e3a32005b8b3",
    #    "species": "agriopis_leucophaearia_gca949125355v1",
    #    "dataset_uuid": "7cba98c3-1796-4eb0-92f2-20df96c6d68b",
    #    "dataset_status": "Processed",
    #    "dataset_source": "agriopis_leucophaearia_gca949125355v1_core_110_1",
    #    "dataset_type": "assembly"}

    return bless {}, $class;
}

sub stringify {
    my ($self) = @_;
    return $self->genome_uuid();
}

sub get_dbh {
    my ($self) = @_;

    $dbconn =~ m{^mysql://([^:@]+)((?::[^@]+)?)@([^:]+):([^/]+)/$};

    my ($user, $pass, $host, $port) = ($1, $2, $3, $4);
    die "Error in DB connection string" unless ($user and $host and $port);
    my $dbname = $conf->{dataset_source};

    my $dbh = DBI->connect("dbi:mysql:host=$host;port=$port;database=$dbname",
        $user, $pass, {RaiseError => 1}) or die "DBI connect failed: $!";

    return $dbh;
}


sub genome_output_path {
    return path($output);
}
sub genome_uuid {
    return $conf->{genome_uuid};
}
sub species {
    return $conf->{species};
}

sub common_files_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid());
    return $self->_check_path($path);
}

sub temporary_files_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid())->child('tmp');
    return $self->_check_path($path);
}

sub genes_transcripts_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid());
    return $self->_check_path($path);
}

sub contigs_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid());
    return $self->_check_path($path);
}

sub seqs_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid())->child('seqs');
    return $self->_check_path($path);
}

sub gc_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid());
    return $self->_check_path($path);
}

sub jump_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid());
    return $self->_check_path($path);
}

sub variants_path {
    my ($self) = @_;
    my $path = $self->genome_output_path()->child($self->genome_uuid());
    return $self->_check_path($path);
}

sub get_seq_path {
    my ($self, $object) = @_;
    my $seq_id = $self->to_seq_id($object);
    my $path = $self->seqs_path()->child($seq_id);
    return $path;
}

sub genome_report_path {
    my ($self) = @_;
    return $self->common_files_path->child('genome_report.txt');
}

sub chrom_sizes_path {
    my ($self) = @_;
    return $self->common_files_path->child('chrom.sizes');
}

sub chrom_hashes_path {
    my ($self) = @_;
    return $self->common_files_path->child('chrom.hashes');
}

sub contigs_bb_path {
    my ($self) = @_;
    return $self->contigs_path->child('contigs.bb');
}

sub gc_bw_path {
    my ($self) = @_;
    return $self->gc_path->child('gc.bw');
}

sub canonical_transcripts_bb_path {
    my ($self) = @_;
    return $self->genes_transcripts_path->child('canonical.bb');
}

sub all_transcripts_bb_path {
    my ($self) = @_;
    return $self->genes_transcripts_path->child('all.bb');
}

sub genes_bb_path {
    my ($self) = @_;
    return $self->genes_transcripts_path->child('genes.bb');
}

sub _check_path {
    my ($self, $path) = @_;
    if (!$path->is_dir()) {
        $path->mkpath();
    }
    return $path;
}

1;
