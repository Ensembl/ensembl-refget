package Options;

################################################################
#
# A singleton for capturing command-line options
#
################################################################

use strict;
use warnings;

use Exporter qw(import);
our @EXPORT = qw(skipdone_option output_option config_option dbconn_option command_line_arguments);

use Getopt::Long;

my $output;
my $conf;
my $dbconn;
my $skipdone;

GetOptions (
    'output=s' => \$output,
    'config=s' => \$conf,
    'dbconn=s' => \$dbconn,
    'skipdone' => \$skipdone
);

sub output_option {
    return $output;
}

sub config_option {
    return $conf;
}

sub dbconn_option {
    return $dbconn;
}

sub skipdone_option {
    return $skipdone;
}

sub command_line_arguments {
    # by now @ARGV contains only items not specified in GetOptions
    return @ARGV;
}

1;
