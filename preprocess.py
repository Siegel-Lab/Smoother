import os
from pickle import FALSE
import stat as stat_perm
import argparse
from bin.meta_data import *
from bin.chr_sizes import *
import random
import sys
from bin.heatmap_as_r_tree import *
import subprocess
import glob
import math
from bin.libSps import *
from bin.grid_seq_norm import *
from bin.parse_and_group_reads import *
from bin.dist_dep_decay_norm import *


# parses file & sets up axis and matrix to have the appropriate size

def touch(f_name):
    with open(f_name, 'a'):  # Create file if does not exist
        pass


def execute(cmd):
    popen = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, universal_newlines=True)
    for stdout_line in iter(popen.stdout.readline, ""):
        yield stdout_line
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)


def parse_norm_file(filename):
    for line in execute(['samtools', 'view', filename]):
        if len(line) == 0:
            continue
        split = line.split("\t")
        if len(split) < 5:
            print("weird line in bam file: '", line, "'")
            continue

        read_name, flag, chrom, start_pos, map_q, *other = split
        xa_tag = "?"
        for s in other:
            if s[:5] == "XA:Z:":
                xa_tag = s
        yield read_name, chrom, int(start_pos), int(map_q), xa_tag

def group_norm_file(in_filename, file_size):
    file_name = simplified_filepath(in_filename)
    last_read_name = None
    group = []
    def deal_with_group():
        nonlocal last_read_name
        nonlocal group
        chr_1 = group[0][0]
        do_cont = True
        for chr_2, _, _ in group:
            if chr_2 != chr_1:
                do_cont = False # no reads that come from different chromosomes
        if do_cont:
            pos_s = min([g[1] for g in group])
            pos_e = max([g[1] for g in group])
            map_q = max([g[2] for g in group])
            if len(group) > 1:
                map_q += 1
            yield last_read_name, chr_1, pos_s, pos_e, map_q
        group = []
    
    for idx_2, (read_name, chrom, pos, map_q, xa_tag) in enumerate(parse_norm_file(in_filename)):
        if idx_2 % PRINT_MODULO == 0:
            print("loading file", file_name, ", line", idx_2+1, "of", file_size, "=", 
                   round( 100*(idx_2+1)/file_size, 2), "%", end="\033[K\r")
        if last_read_name != read_name and len(group) > 0:
            yield from deal_with_group()
        last_read_name = read_name
        group.append((chrom, int(pos), int(map_q)))
        for chr_1, pos_1 in read_xa_tag(xa_tag):
            group.append((chr_1, int(pos_1), 0))
    yield from deal_with_group()


def parse_annotations(annotation_file, axis_start_pos_offset, dividend):
    annos = []

    annotation_types = set()
    with open(annotation_file, "r") as in_file_1:
        for line in in_file_1:
            if line[0] == "#":
                continue
            # parse file colum
            chrom, db_name, annotation_type, from_pos, to_pos, _, strand, _, extras, *opt = line.split()
            
            if not chrom in axis_start_pos_offset:
                continue
            annotation_types.add(annotation_type)
            s = axis_start_pos_offset[chrom] + int(from_pos) // dividend
            e = axis_start_pos_offset[chrom] + int(to_pos) // dividend
            annos.append((annotation_type, s, max(s+1, e), extras.replace(";", "\n")))
    return annos


def parse_wig_file(filename, chr_start_idx, dividend):
    with open(filename, "r") as in_file_1:
        curr_chr = None
        xs = [0]
        ys = [0]
        track = None
        y = "track"
        x = "variableStep chrom="
        for line in in_file_1.readlines():
            if line[:len(y)] == y:
                if not track is None:
                    xs.append(chr_start_idx['end'])
                    ys.append(0)
                    yield xs, ys, track
                    xs = [0]
                    ys = [0]
                track = line[line.index("name=\"")+len("name=\""):-2]
            elif line[:len(x)] == x:
                curr_chr = line[len(x):line.index(" span=")]
                if not curr_chr in chr_start_idx:
                    print("WIG file contains unknown contig", curr_chr)
                else:
                    xs.append(chr_start_idx[curr_chr])
                    ys.append(0)
            elif curr_chr in chr_start_idx:
                a, b = line[:-1].split(" ")
                xs.append(chr_start_idx[curr_chr] + int(a) // dividend)
                ys.append(float(b))
        xs.append(chr_start_idx['end'])
        ys.append(0)
        yield xs, ys, track


def make_meta(out_prefix, chr_len_file_name, annotation_filename, dividend, test=False):
    os.makedirs(out_prefix + ".smoother_index")
    #os.chmod(out_prefix + ".smoother_index", # would make it look more like a file but do i really want that?
    #         stat_perm.S_IWUSR | stat_perm.S_IXUSR | stat_perm.S_IXGRP | stat_perm.S_IXOTH )
    meta = MetaData(dividend)
    meta.set_chr_sizes(ChrSizes(chr_len_file_name, dividend, filter=lambda x: ("Chr1_" in x) or not test))

    if not annotation_filename is None:
        meta.add_annotations(parse_annotations(annotation_filename, meta.chr_sizes.chr_start_pos, dividend))

    meta.save(out_prefix + ".smoother_index/meta")
    touch(out_prefix + ".smoother_index/norm.coords")
    touch(out_prefix + ".smoother_index/norm.datsets")
    touch(out_prefix + ".smoother_index/norm.overlays")
    touch(out_prefix + ".smoother_index/norm.prefix_sums")
    for map_q in [True, False]:
        for multi_map in [True, False]:
            idx_suff = (".3" if map_q else ".2") + (".2" if multi_map else ".0")
            touch(out_prefix + ".smoother_index/repl" + idx_suff + ".coords")
            touch(out_prefix + ".smoother_index/repl" + idx_suff + ".datsets")
            touch(out_prefix + ".smoother_index/repl" + idx_suff + ".overlays")
            touch(out_prefix + ".smoother_index/repl" + idx_suff + ".prefix_sums")


def add_replicate(out_prefix, path, name, group_a, test=False, cached=False, no_groups=False, without_dep_dim=True,
                  keep_points=False, only_points=False, no_map_q=False, no_multi_map=False):
    meta = MetaData.load(out_prefix + ".smoother_index/meta")
    if not meta.dataset_name_unique(name):
        raise RuntimeError("The dataset name you provide must be unique but is not. Use the <list> command to see all datasets.")
    if not (no_map_q and no_multi_map):
        print("pre-scanning file for index parameters...")
        has_map_q, multi_map = has_map_q_and_multi_map(path, test, meta.chr_sizes.chr_sizes)
    if no_map_q:
        has_map_q = False
    if no_multi_map:
        multi_map = False
    print("generating index", "with" if has_map_q else "without", "mapping quality and", 
          "with" if multi_map else "without", "multi mapping.")
    idx_suff = (".3" if has_map_q else ".2") + (".2" if multi_map else ".0")
    index = make_sps_index(out_prefix + ".smoother_index/repl" + idx_suff, 3 if has_map_q else 2, False, True, 
                            2 if multi_map else 0, "Cached" if cached else "Disk", True )
    last_cnt = len(index)
    for read_name, chr_1, pos_1_s, pos_1_e, chr_2, pos_2_s, pos_2_e, map_q in group_heatmap(path, get_filesize(path),
                                                                                            meta.chr_sizes.chr_sizes,
                                                                                            no_groups, test):
        act_pos_1_s = meta.chr_sizes.coordinate(pos_2_s // meta.dividend, chr_2)
        act_pos_1_e = meta.chr_sizes.coordinate(pos_2_e // meta.dividend, chr_2)
        act_pos_2_s = meta.chr_sizes.coordinate(pos_1_s // meta.dividend, chr_1)
        act_pos_2_e = meta.chr_sizes.coordinate(pos_1_e // meta.dividend, chr_1)
        if has_map_q and multi_map:
            index.add_point([act_pos_1_s, act_pos_2_s, 255-map_q], [act_pos_1_e, act_pos_2_e, 255-map_q], read_name)
        elif has_map_q and not multi_map:
            index.add_point([act_pos_1_s, act_pos_2_s, 255-map_q], read_name)
        elif not has_map_q and multi_map:
            index.add_point([act_pos_1_s, act_pos_2_s], [act_pos_1_e, act_pos_2_e], read_name)
        elif not has_map_q and not multi_map:
            index.add_point([act_pos_1_s, act_pos_2_s], read_name)
        else:
            raise RuntimeError("this statement should never be reached")
    if not only_points:
        print()
        print("generating index")
        idx = index.generate(last_cnt, len(index))
        print("done generating index")
        #print("max value is:", index.get_max_prefix_sum())
        meta.add_dataset(name, path, group_a, idx, has_map_q, multi_map)
        meta.save(out_prefix + ".smoother_index/meta")
        if not keep_points:
            del index
            os.remove(out_prefix + ".smoother_index/repl" + idx_suff + ".points")
            os.remove(out_prefix + ".smoother_index/repl" + idx_suff + ".desc")
    else:
        print("Points are added to the indices:", last_cnt, "to", len(index))

def add_normalization(out_prefix, path, name, for_row, test=False, cached=False, keep_points=False):
    meta = MetaData.load(out_prefix + ".smoother_index/meta")
    if not meta.normalization_name_unique(name):
        raise RuntimeError("The normalization name you provide must be unique but is not. Use the <list> command to see all normalization.")
    index = make_sps_index(out_prefix + ".smoother_index/norm", 2, False, True, 1, 
                            "Cached" if cached else "Disk", True )
    last_cnt = len(index)
    if path[-4:] == ".wig":
        raise RuntimeError("disabled for now")
        for xs, ys, n in parse_wig_file(path, meta.chr_sizes.chr_start_pos, meta.dividend):
            meta.add_wig_normalization(name + ": " + n, path, for_row, xs, ys)
    else:
        cnt = 0
        file_size = int(subprocess.run(['samtools', 'view', '-c', path], stdout=subprocess.PIPE).stdout.decode('utf-8'))
        for read_name, chrom, pos_s, pos_e, map_q in group_norm_file(path, file_size):
            if not chrom in meta.chr_sizes.chr_sizes:
                continue
            act_pos_s = meta.chr_sizes.coordinate(int(pos_s) // meta.dividend, chrom)
            act_pos_e = meta.chr_sizes.coordinate(int(pos_e) // meta.dividend, chrom)
            index.add_point([act_pos_s, 255-map_q], [act_pos_e, 255-map_q], read_name)
            cnt += 1
            if cnt > TEST_FAC and test:
                break
        print()
        print("generating index")
        idx = index.generate(last_cnt, len(index))
        meta.add_normalization(name, path, for_row, idx, True, True)
    meta.save(out_prefix + ".smoother_index/meta")
    if not keep_points:
        del index
        os.remove(out_prefix + ".smoother_index/norm.points")
        os.remove(out_prefix + ".smoother_index/norm.desc")


def init(args):
    print("LibSps Version:", VERSION)
    make_meta(args.index_prefix, args.chr_len, args.annotations, args.dividend, args.test)

def repl(args):
    print("LibSps Version:", VERSION)
    add_replicate(args.index_prefix, args.path, args.name, args.group, args.test, not args.uncached, args.no_groups,
                  args.without_dep_dim, args.keep_points, args.only_points, args.no_map_q, args.no_multi_map)

def norm(args):
    print("LibSps Version:", VERSION)
    add_normalization(args.index_prefix, args.path, args.name, args.group, args.test, not args.uncached, args.keep_points)

def grid_seq_norm(args):
    print("LibSps Version:", VERSION)
    if not args.visualize and not args.add_annotation and not args.add_normalization_track:
        print("grid-seq-norm requires one of -a -v or -n.")
    else:
        meta = MetaData.load(args.index_prefix + ".smoother_index/meta")
        bin_size = max(args.bin_size // meta.dividend, 1)
        index = Tree_4(args.index_prefix)
        datasets = args.datasets
        if datasets is None or len(datasets) == 0:
            datasets = list(range(len(meta.datasets)))
        ranked_regions = make_grid_seq_ranked_regions(index, datasets, args.mapping_q, meta.chr_sizes,
                                                    meta.annotations, args.annotation, bin_size)
        if args.visualize:
            make_grid_seq_plots(ranked_regions, args.filter_rna, args.filter_dna)
        filtered_rr = filter_r_r(ranked_regions, args.filter_rna, args.filter_dna)[:100]
        if args.add_annotation:
            do_add_annotation(filtered_rr, meta, args.name)
        if args.add_normalization_track:
            index_arr = make_sps_index(args.index_prefix + ".smoother_index/norm", 2, False, 1, 
                                    "Cached" if not args.uncached else "Disk", True )
            add_as_normalization(filtered_rr, datasets, meta, index_arr, args.name, 
                                "GRID-seq normalization created with " + str(sys.argv))

        meta.save(args.index_prefix + ".smoother_index/meta")

def ddd_sample(args):
    print("LibSps Version:", VERSION)
    sample_dist_dep_dec(args.in_path, args.out_path)

def list_content(args):
    print("LibSps Version:", VERSION)
    print(MetaData.load(args.index_prefix + ".smoother_index/meta"))

def ddd_load(args):
    print("LibSps Version:", VERSION)
    meta = MetaData.load(args.index_prefix + ".smoother_index/meta")
    load_dist_dep_decay(meta, args.in_path, args.chr_list)
    meta.save(args.index_prefix + ".smoother_index/meta")

def get_argparse():
    parser = argparse.ArgumentParser(description='Create indices for the smoother Hi-C data viewer.')

    ## deebugging arguments
    parser.add_argument('--test', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('--uncached', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('--no_groups', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('-v', "--verbosity", help="@todo make this do sth", default=1)
    parser.add_argument('--without_dep_dim', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('--keep_points', help=argparse.SUPPRESS, action='store_true')
    parser.add_argument('--only_points', help=argparse.SUPPRESS, action='store_true')

    sub_parsers = parser.add_subparsers(help='Sub-command that shall be executed.', dest="cmd")
    sub_parsers.required=True

    init_parser = sub_parsers.add_parser("init", help="Create a new index.")
    init_parser.add_argument('index_prefix', 
        help="Path where the index shall be saved. Note: a folder with multiple files will be created.")
    init_parser.add_argument('chr_len', 
        help="Path to a file that contains the length (in nucleotides) of all chromosomes. The file shall contain 2 tab seperated columns columns: The chromosome names and their size in nucleotides. The order of chromosomes in this files will be used as the display order in the viewer.")
    init_parser.add_argument('-d', '--dividend', type=int, default=1,
        help="Divide all coordinates by this number. Larger numbers will reduce the index size and preprocessing time. However, bins with a size below this given number cannot be displayed.")
    init_parser.add_argument('-a', '--annotations', metavar="PATH", default=None,
        help="Path to a file that contains annotations for the genome. File should be in the gff3 fromat.")
    init_parser.set_defaults(func=init)

    repl_parser = sub_parsers.add_parser("repl", help="Add a replicate to a given index.")
    repl_parser.add_argument('index_prefix', 
        help="Prefix that was used to create the index (see the init subcommand).")
    repl_parser.add_argument('path', 
        help="Path to the file that contains the aligned reads.")
    repl_parser.add_argument('name', 
        help="Name for the new replicate.")
    repl_parser.add_argument('-g', '--group', default="neither", choices=["a", "b", "both", "neither"], 
        help="Which analysis group to place the new replicate in when opening the interface. (default: %(default)s)")
    repl_parser.add_argument('-q', '--no_map_q', action='store_true', 
        help="Do not store mapping quality information. This will make the index faster and smaller. (default: off)")
    repl_parser.add_argument('-m', '--no_multi_map', action='store_true', 
        help="Do not multi mapping information (reads that map to multiple loci). This will make the index faster and smaller. (default: off)")
    repl_parser.set_defaults(func=repl)

    norm_parser = sub_parsers.add_parser("norm", help="Add a normalization track to an index, using external sequencing data.")
    norm_parser.add_argument('index_prefix', 
        help="Prefix that was used to create the index (see the init subcommand).")
    norm_parser.add_argument('path', 
        help="Path to the file that contains the aligned reads.")
    norm_parser.add_argument('name', 
        help="Name for the new normalization track.")
    norm_parser.add_argument('-g', '--group', default="neither", 
                             choices=["row", "col", "both", "neither"], 
        help="Where to to place the new normalization track when opening the interface. (default: %(default)s)")
    norm_parser.set_defaults(func=norm)

    grid_seq_norm_parser = sub_parsers.add_parser("grid-seq-norm", help="Add a normalization track to an index, using the datasets already in the index. This follows the approach used in the GRID-seq paper. This function does nothing if neither -v -a or -n is given. We suggest using -v first to visualize what is then added to the index.")
    grid_seq_norm_parser.add_argument('index_prefix', 
        help="Prefix that was used to create the index (see the init subcommand).")
    grid_seq_norm_parser.add_argument('name', 
        help="Name for the new normalization track.")
    grid_seq_norm_parser.add_argument('-d', '--datasets', metavar="VAL", nargs='*', type=int,
        help="Datasets to include in the normalization, given by their Id's use the <list> command to find the ids. (default: all datasets)")
    grid_seq_norm_parser.add_argument('-m', '--mapping_q', metavar="VAL", type=int, default=0, 
        help="Consider only reads with this mapping quality or higher. (default: %(default)s)")
    grid_seq_norm_parser.add_argument('-b', '--bin_size', metavar="VAL", type=int, default=1000, 
        help="Use this bin size. (default: %(default)s)")
    grid_seq_norm_parser.add_argument('-R', '--filter_rna', metavar="VAL", type=float, default=100, 
        help="Only keep rows with an average RNA density of VAL reads per kb. (default: %(default)s)")
    grid_seq_norm_parser.add_argument('-D', '--filter_dna', metavar="VAL", type=float, default=10, 
        help="Only keep columns with a maximal DNA density of VAL reads per kb. (default: %(default)s)")
    grid_seq_norm_parser.add_argument('-A', '--annotation',
        help="name of the annotation to use as bins for the RNA or 'bins' to use --bin_size sized bins over the full genome.", metavar="VAL", default="gene")
    grid_seq_norm_parser.add_argument('-v', '--visualize', action='store_true', 
        help="Visualize the RNA and DNA densities as well as the picked filters.")
    grid_seq_norm_parser.add_argument('-a', '--add_annotation', action='store_true', 
        help="Turn the picked genes into an annotation track.")
    grid_seq_norm_parser.add_argument('-n', '--add_normalization_track', action='store_true', 
        help="Add the picked genes as an normalization track.")
    grid_seq_norm_parser.set_defaults(func=grid_seq_norm)
    
    ddd_sample_parser = sub_parsers.add_parser("ddd-sample", 
        help="Sample distance dependant decay from a replicate input file.") #@todo dataset-id
    ddd_sample_parser.add_argument('in_path', 
        help="Path to the file that contains the aligned reads.")
    ddd_sample_parser.add_argument('out_path',
        help="Where to store the distance dependant decay file output.")
    ddd_sample_parser.set_defaults(func=ddd_sample)

    ddd_load_parser = sub_parsers.add_parser("ddd-load", 
        help="Load a distance dependant decay file into the index.")
    ddd_load_parser.add_argument('index_prefix', 
        help="Prefix that was used to create the index (see the init subcommand).")
    ddd_load_parser.add_argument('in_path', 
        help="Path to the file that contains distance dependant decay.")
    ddd_load_parser.add_argument('chr_list', nargs='+', 
        help="List of chromosomes which to normalize with this distance dependant decay.")
    ddd_load_parser.set_defaults(func=ddd_load)

    list_parser = sub_parsers.add_parser("list", help="List the content (datasets and normalizations) of an index.")
    list_parser.add_argument('index_prefix', 
        help="Prefix that was used to create the index (see the init subcommand).")
    list_parser.set_defaults(func=list_content)

    return parser

if __name__ == "__main__":
    parser = get_argparse()

    args = parser.parse_args()

    args.func(args)

