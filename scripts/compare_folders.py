"""
Script for comparing the filenames that appear in one repository but not in the
other and vice versa
"""

import sys
import os
from pathlib import Path
from typing import List, Set

def filename_from_folder(folder: str) -> List[str]:
    return [Path(f).stem for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))]

def compare_folders(folder1: str, folder2: str) -> Set[str]:
    files1 = set(filename_from_folder(folder1))
    files2 = set(filename_from_folder(folder2))
    return files1.symmetric_difference(files2)

if __name__ == "__main__":
    files = compare_folders(sys.argv[1], sys.argv[2])
    print("Files not found")
    for file_ in files:
        print(file_)