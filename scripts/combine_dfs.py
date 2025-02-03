import os
import subprocess
import shutil
import filecmp
from pathlib import Path
import multiprocessing as mp
import sys
import pandas as pd
from count_num_ins import instrs_from_opcodes


def combine_dfs(csv_folder: Path, combined_csv: Path):
    dfs = []
    for csv_file in csv_folder.glob("*.csv"):
        df = pd.read_csv(csv_file, index_col=0)
        df.reset_index(drop=True, inplace=True)
        dfs.append(df)
    combined_df = pd.concat(dfs, ignore_index=True)
    combined_df.to_csv(combined_csv)


if __name__ == "__main__":
    combine_dfs(Path(sys.argv[1]), Path(sys.argv[2]))
