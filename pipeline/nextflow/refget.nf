#!/usr/bin/env nextflow
import groovy.json.JsonSlurper

nextflow.enable.dsl=2

def helpAndDie() {
    // display the help message and terminate

    log.info'''
    Usage:
    nextflow run datafile.nf <ARGUMENTS>

    Required:
    --output_path <PATH>
        Datafile output directory

    --fasta_path <PATH>
        Path to FASTA format data for CDS, CDNA and PEP. This is usually
        produced by the production dump pipeline. 
        Example: <path>/ensembl/production/ensembl_dumps/blast

    --script_path <PATH>
        Path to the bin folder of the ensembl-e2020-datafiles pipeline
        Example: <path>/ensembl-e2020-datafiles/bin/

    --factory_path <PATH>
        Path to the metadata API species factory script

    --factory_selector <STRING>
        Specify what to select in the metadata DB. Example 'Processing
        Submitted'. Remember to quote string in the shell.

    --dbconnection_file <PATH>
        Path to JSON file with DB config. Example:
        {
            "prod-1-meta" : "mysql://ensro@mysql-ens-production-1.ebi.ac.uk:4721/ensembl_genome_metadata",
            "sta-6" : "mysql://ensro@mysql-ens-sta-6.ebi.ac.uk:4695/"
        }

    --metadatadb_key <Key>
        Key to the metadata DB config in the DB connection file (e.g. prod-1-meta)

    --speciesdb_key <Key>
        Key to the species DB config in the DB connection file (e.g. sta-6)

    Optional:
    --genome_uuid <UUID>
        Optional comma-separated list of genome_uuids. The pipeline will generate data for these species.
        Without the option, the default is to run for all species

    --release_id <ID>
        Optional release_id. The pipeline will generate data for the species belonging to this release_id.
        Without the option, the default is to run disregarding the release

    --help
        This text

    --debug
        Enable nextflow debug output
    '''.stripIndent()
    System.exit(1)
}

def paramsOrDie() {
    /*
      Function: paramsOrDie
      Description: Checks the params defined by the user.
      Input: inputData - None (default nextflow params Type: None)
      Output: result - Throws the exception . (Type: RuntimeException])
    */

    allowedParams = [
        'output_path',
        'fasta_path',
        'script_path',
        'factory_path',
        'factory_selector',
        'dbconnection_file',
        'metadatadb_key',
        'speciesdb_key',
        'genome_uuid',
        'release_id',
        'help',
        'debug'
    ]
    unknownParams = params.keySet() - allowedParams

    def printErr = System.err.&println

    if (unknownParams) {
        printErr("Unknown parameters: ${unknownParams.join(', ')}")
        System.exit(1)
    }

    for (i in allowedParams) {
        if (! params.containsKey(i)) {
            params[i] = ""
        }
    }

    for (i in [
        params.dbconnection_file, params.output_path, params.fasta_path, params.script_path, params.factory_path,
        params.factory_selector, params.metadatadb_key, params.speciesdb_key
    ]) {
        if (! i?.trim()) {
            printErr("Missing required parameter")
            helpAndDie()
        }
    }
}

def convertToList( userParam ){
    /*
      Function: convertToList
      Description: Convert user defined comma separated params into a list.
      Input: inputData - Comma separated string. (Type: String, Ex: "homo_sapiens,mus_musculus")
      Output: result - Split the string with delimiter. (Type: List[String])
    */

    if ( userParam && userParam != true && userParam != false){
        return userParam.split(',').collect { value -> "\"$value\""}
    }

    return []	

}

paramsOrDie()
println """\
         D A T A F I L E - N F   P I P E L I N E
         ===================================
         output_path: ${params.output_path}
         fasta_path: ${params.fasta_path}
         script_path: ${params.script_path}
         factory_path: ${params.factory_path}
         dbconnection_file: ${params.dbconnection_file}
         metadatadb_key: ${params.metadatadb_key}
         speciesdb_key: ${params.speciesdb_key}
         genome_uuid: ${params.genome_uuid}
         release_id: ${params.release_id}
         debug: ${params.debug}
         """
         .stripIndent()


workflow {
    params.help && helpAndDie()

    def jsonSlurper = new JsonSlurper()
    def myConfig = jsonSlurper.parseText(new File(params.dbconnection_file).text)
    metadataDBConnStr = myConfig[params.metadatadb_key]
    speciesDBConnStr = myConfig[params.speciesdb_key]

    GenomeInfoProcess(metadataDBConnStr)
    | splitText
    | combine(Channel.of(speciesDBConnStr))
    | ( DumpSequence & DumpCDNA & DumpCDS & DumpPEP)
}

process GenomeInfoProcess {
    /*
      Description: Fetch the genome information from the ensembl production
      metadata-api and write as JSON.
    */

    if (params.debug) {
        debug params.debug
        errorStrategy 'terminate'
    }
    label 'mem1GB'
    tag 'genomeinfo'
    publishDir "${params.output_path}", mode: 'copy', overWrite: true

    input:
    val dbconn

    output:
    path 'genome_info.json'

    script:
    g_uuid = params.genome_uuid ? "--genome_uuid " + convertToList(params.genome_uuid).join(" ") : ""
    e_release_id = params.release_id ? "--release_id " + params.release_id : ""

    """
    python ${params.factory_path} \
        --metadata_db_uri ${dbconn} \
        --output genome_info.json \
        --batch_size 0 \
        --dataset_status ${params.factory_selector} \
        --dataset_type genebuild \
        ${g_uuid} \
        ${e_release_id}
    """
}

process DumpSequence {
    /*
      Description: Builds the seq.txt and chrom.hashes files
    */
    if (params.debug) {
        debug params.debug
        errorStrategy 'terminate'
    }

    // Currently, the wheat cultivars need around 26 GB of RAM. Most species
    // need less than 3 GB.
    label 'mem32GB'
    tag 'dump_seq'

    input:
    val input

    when:
    destdir = params.output_path
    confStr = input[0].trim()
    jsonS = new JsonSlurper()
    confJson = jsonS.parseText(confStr)
    genome_uuid = confJson.genome_uuid
    File file = new File("${destdir}/${genome_uuid}/seqs/seq.txt.zst")
    ! file.exists()

    script:
    conf = input[0].trim()
    dbconn = input[1]
    File seqfile = new File("${destdir}/${genome_uuid}/seqs/seq.txt")
    File zstfile = new File("${destdir}/${genome_uuid}/seqs/seq.txt.zst")
    """
    echo [DumpSequence] Dump seq and calc checksum
    perl ${params.script_path}/dump_sequence.pl --conf '${conf}' --output ${params.output_path} --dbconn '${dbconn}'
    perl ${params.script_path}/compress.pl --infile ${seqfile} --outfile ${zstfile}
    rm -f ${seqfile}
    """
}


process DumpCDNA {
    /*
      Description: Create cdna.txt and cdna.hashes files from fasta input
    */
    if (params.debug) {
        debug params.debug
        errorStrategy 'terminate'
    }

    label 'mem1GB'
    tag 'dump_cdna'

    input:
    val input

    when:
    fastadir = params.fasta_path
    destdir = params.output_path
    confStr = input[0].trim()
    jsonS = new JsonSlurper()
    confJson = jsonS.parseText(confStr)
    genome_uuid = confJson.genome_uuid
    File dest = new File("${destdir}/${genome_uuid}/seqs/cdna.txt.zst")
    File source = new File("${fastadir}/${genome_uuid}/cdna.fa")
    source.exists() and ! dest.exists()

    script:
    File infile =  new File("${fastadir}/${genome_uuid}/cdna.fa")
    File hashfile= new File("${destdir}/${genome_uuid}/cdna.hashes")
    File seqfile = new File("${destdir}/${genome_uuid}/seqs/cdna.txt")
    File zstfile = new File("${destdir}/${genome_uuid}/seqs/cdna.txt.zst")
    """
    echo [DumpCDNA] Dump CDNA seq and calc checksum
    perl ${params.script_path}/dump_from_fasta.pl --infile ${infile} --hashfile ${hashfile} --seqfile ${seqfile}
    perl ${params.script_path}/compress.pl --infile ${seqfile} --outfile ${zstfile}
    rm -f ${seqfile}
    """
}
process DumpCDS {
    /*
      Description: Create cds.txt and cds.hashes files from fasta input
    */
    if (params.debug) {
        debug params.debug
        errorStrategy 'terminate'
    }

    label 'mem1GB'
    tag 'dump_cds'

    input:
    val input

    when:
    fastadir = params.fasta_path
    destdir = params.output_path
    confStr = input[0].trim()
    jsonS = new JsonSlurper()
    confJson = jsonS.parseText(confStr)
    genome_uuid = confJson.genome_uuid
    File dest = new File("${destdir}/${genome_uuid}/seqs/cds.txt.zst")
    File source = new File("${fastadir}/${genome_uuid}/cds.fa")
    source.exists() and ! dest.exists()

    script:
    File infile =  new File("${fastadir}/${genome_uuid}/cds.fa")
    File hashfile= new File("${destdir}/${genome_uuid}/cds.hashes")
    File seqfile = new File("${destdir}/${genome_uuid}/seqs/cds.txt")
    File zstfile = new File("${destdir}/${genome_uuid}/seqs/cds.txt.zst")
    """
    echo [DumpCDS] Dump CDS seq and calc checksum
    perl ${params.script_path}/dump_from_fasta.pl --infile ${infile} --hashfile ${hashfile} --seqfile ${seqfile}
    perl ${params.script_path}/compress.pl --infile ${seqfile} --outfile ${zstfile}
    rm -f ${seqfile}
    """
}
process DumpPEP {
    /*
      Description: Create pep.txt and pep.hashes files from fasta input
    */
    if (params.debug) {
        debug params.debug
        errorStrategy 'terminate'
    }

    label 'mem1GB'
    tag 'dump_pep'

    input:
    val input

    when:
    fastadir = params.fasta_path
    destdir = params.output_path
    confStr = input[0].trim()
    jsonS = new JsonSlurper()
    confJson = jsonS.parseText(confStr)
    genome_uuid = confJson.genome_uuid
    File dest = new File("${destdir}/${genome_uuid}/seqs/pep.txt.zst")
    File source = new File("${fastadir}/${genome_uuid}/pep.fa")
    source.exists() and ! dest.exists()

    script:
    File infile =  new File("${fastadir}/${genome_uuid}/pep.fa")
    File hashfile= new File("${destdir}/${genome_uuid}/pep.hashes")
    File seqfile = new File("${destdir}/${genome_uuid}/seqs/pep.txt")
    File zstfile = new File("${destdir}/${genome_uuid}/seqs/pep.txt.zst")
    """
    echo [DumpPEP] Dump PEP seq and calc checksum
    perl ${params.script_path}/dump_from_fasta.pl --infile ${infile} --hashfile ${hashfile} --seqfile ${seqfile}
    perl ${params.script_path}/compress.pl --infile ${seqfile} --outfile ${zstfile}
    rm -f ${seqfile}
    """
}

