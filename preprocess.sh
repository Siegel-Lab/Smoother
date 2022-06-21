#!/bin/bash
#SBATCH --mem 100G -J preprocess_heatmap --time=240:00:00 -o slurm_preprocess_heatmap-%j.out --mail-user=markus.rainer.schmidt@gmail.com --mail-type END


module load ngs/samtools/1.9

source activate $(pwd)/conda_env/smoother

./bin/conf_version.sh
cat VERSION


BEDS="/work/project/ladsie_012/ABS.2.2/2021-10-26_NS502-NS521_ABS_CR_RADICL_inputMicroC/bed_files"
BED_SUF="RNA.sorted.bed_K1K2.bed_K4.bed_R_D.bed_R_D_K1K2.bed_R_D_PRE1.bed"

BAMS="/work/project/ladsie_012/ABS.2.2/20210608_Inputs"
BAM_SUF="R1.sorted.bam"

INDEX_PREFIX="../smoother_out/test"
#INDEX_PREFIX="../smoother_out/annas"

rm -r ${INDEX_PREFIX}.smoother_index

echo "generating index ${INDEX_PREFIX}"

#DBG_C=""
#DBG_C="--without_dep_dim"
DBG_C="--uncached --test"
#DBG_C="--uncached"
#DBG_C="--test"

python3 preprocess.py ${DBG_C} init "${INDEX_PREFIX}" Lister427.sizes -a HGAP3_Tb427v10_merged_2021_06_21.gff3 -d 1000

# ANNA #

#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS503_P10_Total_2.${BED_SUF}" "P10_Total_Rep2" -g a

#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS504_P10_Total_3.${BED_SUF}" "P10_Total_Rep3" -g a
#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS505_N50_Total_1.${BED_SUF}" "N50_Total_Rep1" -g a
#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS506_N50_Total_2.${BED_SUF}" "N50_Total_Rep2" -g a
#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS507_N50_Total_3.${BED_SUF}" "N50_Total_Rep3" -g a

#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS508_P10_NPM_1.${BED_SUF}" "P10_NPM_Rep1" -g b

#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS509_P10_NPM_2.${BED_SUF}" "P10_NPM_Rep2" -g b
#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS510_P10_NPM_3.${BED_SUF}" "P10_NPM_Rep3" -g b
#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS511_N50_NPM_1.${BED_SUF}" "N50_NPM_Rep1" -g b
#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS512_N50_NPM_2.${BED_SUF}" "N50_NPM_Rep2" -g b
#python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${BEDS}/NS513_N50_NPM_3.${BED_SUF}" "N50_NPM_Rep3" -g b

#python3 preprocess.py ${DBG_C} norm "${INDEX_PREFIX}" "${BAMS}/WT1_gDNA_inputATAC.${BAM_SUF}" "gDNA_inputATAC" -g col
#python3 preprocess.py ${DBG_C} norm "${INDEX_PREFIX}" "${BAMS}/WT1_RNAseq_NS320.${BAM_SUF}" "RNAseq_NS320" -g row


# BROKEN
#python3 preprocess.py ${DBG_C} norm "${INDEX_PREFIX}" \
#                           "${BAMS}/small_rna/ID-000723-NS1_noadapter_longer17.fq.sorted.bam" "small_RNA" -g row

# test with this:
#python3 preprocess.py ${DBG_C} grid-seq-norm -v -b 1000 -R 60 -D 200000 ${INDEX_PREFIX} caGene

# once -R and -D are correct use this:
# This requires the files that are used to create the datasets to still be in the correct place
#python3 preprocess.py ${DBG_C} grid-seq-norm -van -b 1000 -R 60 -D 200000 ${INDEX_PREFIX} caGene


# CLAUDIA #
CR_BEDS="/work/project/ladsie_010/CR3_Smoother/"

python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${CR_BEDS}/pre1_P10-1_3.x" "P10_Lib1-3" -g a
python3 preprocess.py ${DBG_C} repl "${INDEX_PREFIX}" "${CR_BEDS}/pre1_P10-4_6.x" "P10_Lib4-6" -g a