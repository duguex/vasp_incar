#!/usr/bin/env python3

import os
import json
import argparse
from tqdm import tqdm
from pymatgen.io.vasp import Incar
from multiprocessing import Pool


def extract_incar_from_dir(dirpath):
    """Extract INCAR data from a single directory."""
    try:
        # Read INCAR file using pymatgen
        incar = Incar.from_file(os.path.join(dirpath, "INCAR"))
        
        # Return directory path and INCAR data
        return {
            "directory": dirpath,
            "incar": dict(incar)
        }
    except Exception as e:
        print(f"Error reading INCAR in {dirpath}: {e}")
        return None


def extract_incar_data(root_dir, processes):
    """Extract INCAR data from all subdirectories using multiprocessing."""
    # Get all directories containing INCAR files
    directories_with_incar = []
    
    # Walk through all subdirectories
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Check if INCAR file exists in the current directory
        if "INCAR" in filenames:
            directories_with_incar.append(dirpath)
    
    # Use multiprocessing to process directories in parallel
    with Pool(processes=processes) as pool:
        # Use tqdm for progress bar
        results = list(tqdm(pool.imap(extract_incar_from_dir, directories_with_incar), 
                           total=len(directories_with_incar), 
                           desc="Processing INCAR files"))
    
    # Filter out None results (errors)
    incar_data = [result for result in results if result is not None]
    
    return incar_data

def remove_duplicates(incar_data):
    """Remove duplicate entries using loop comparison."""
    unique_data = []
    
    for i, current_item in enumerate(incar_data):
        is_duplicate = False
        
        # Compare with all previously added unique items
        for existing_item in unique_data:
            # Compare INCAR dictionaries directly
            if current_item["incar"] == existing_item["incar"]:
                is_duplicate = True
                break
        
        # If not a duplicate, add to unique list
        if not is_duplicate:
            unique_data.append(current_item)
    
    return unique_data

def save_to_json(data, output_file):
    """Save data to JSON file."""
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Extract INCAR data from VASP directories")
    parser.add_argument("root_dir", help="Root directory to search for INCAR files")
    parser.add_argument("-o", "--output", default="incar_data.json", 
                       help="Output JSON file (default: incar_data.json)")
    parser.add_argument("-p", "--processes", type=int, default=14,
                       help="Number of processes for parallel processing (default: 14)")
    parser.add_argument("--no-deduplicate", action="store_true",
                       help="Skip deduplication step")
    
    args = parser.parse_args()
    
    # Check if root directory exists
    if not os.path.exists(args.root_dir):
        print(f"Error: Root directory '{args.root_dir}' does not exist")
        return 1
    
    print(f"Searching for INCAR files in: {args.root_dir}")
    print(f"Using {args.processes} processes")
    print(f"Output file: {args.output}")
    
    # Extract INCAR data
    incar_data = extract_incar_data(args.root_dir, args.processes)
    
    # Remove duplicates unless specified otherwise
    if args.no_deduplicate:
        final_data = incar_data
        print("Skipping deduplication")
    else:
        print("Removing duplicates...")
        final_data = remove_duplicates(incar_data)
    
    # Save to JSON file
    save_to_json(final_data, args.output)
    
    print(f"Found {len(incar_data)} directories with INCAR files")
    if not args.no_deduplicate:
        print(f"After deduplication: {len(final_data)} unique INCAR configurations")
    print(f"Data saved to {args.output}")
    
    return 0

if __name__ == "__main__":
    exit(main())