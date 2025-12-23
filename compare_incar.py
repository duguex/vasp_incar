#!/home/duguex/.conda/envs/pydefect/bin/python

import os
from pymatgen.io.vasp import Incar

def compare_incar_files(file1, file2):
    """Compare two INCAR files and return differences and similarities."""
    # Read both INCAR files
    incar1 = Incar.from_file(file1)
    incar2 = Incar.from_file(file2)
    
    # Convert to dictionaries for easier comparison
    dict1 = dict(incar1)
    dict2 = dict(incar2)
    
    # Get all keys from both dictionaries
    all_keys = set(dict1.keys()) | set(dict2.keys())
    
    # Initialize result containers
    common = {}
    only_in_file1 = {}
    only_in_file2 = {}
    different_values = {}
    
    # Compare keys
    for key in all_keys:
        if key in dict1 and key in dict2:
            if dict1[key] == dict2[key]:
                common[key] = dict1[key]
            else:
                different_values[key] = (dict1[key], dict2[key])
        elif key in dict1:
            only_in_file1[key] = dict1[key]
        else:
            only_in_file2[key] = dict2[key]
    
    return {
        'common': common,
        'only_in_file1': only_in_file1,
        'only_in_file2': only_in_file2,
        'different_values': different_values
    }

def print_comparison_report(result):
    """Print a formatted comparison report with color coding."""
    print("INCAR Comparison Report")
    print("======================")
    
    print("\n\033[32mCommon parameters:\033[0m")  # Green
    for key, value in result['common'].items():
        print(f"  \033[32m{key} = {value}\033[0m")
    
    print("\n\033[33mParameters only in INCAR_6:\033[0m")  # Yellow
    for key, value in result['only_in_file1'].items():
        print(f"  \033[33m{key} = {value}\033[0m")
    
    print("\n\033[34mParameters only in INCAR_8:\033[0m")  # Blue
    for key, value in result['only_in_file2'].items():
        print(f"  \033[34m{key} = {value}\033[0m")
    
    print("\n\033[31mParameters with different values:\033[0m")  # Red
    for key, (val1, val2) in result['different_values'].items():
        print(f"  \033[31m{key}: INCAR_6 = {val1}, INCAR_8 = {val2}\033[0m")

if __name__ == "__main__":
    # Compare INCAR_6 and INCAR_8
    result = compare_incar_files('INCAR_6', 'INCAR_8')
    print_comparison_report(result)