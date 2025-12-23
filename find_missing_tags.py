#!/usr/bin/env python

import os
import json
import argparse
from pymatgen.io.vasp import Incar


def extract_all_tags_from_json(json_file):
    """从JSON文件中提取所有已统计的标签"""
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    all_tags = set()
    for entry in data:
        incar_dict = entry.get('incar', {})
        all_tags.update(incar_dict.keys())
    
    return all_tags


def find_all_incar_files(root_dir):
    """查找所有INCAR文件"""
    incar_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.startswith("INCAR"):
                incar_files.append(os.path.join(dirpath, filename))
    return incar_files


def extract_tags_from_incar_file(incar_file):
    """从单个INCAR文件中提取标签"""
    try:
        incar = Incar.from_file(incar_file)
        return set(incar.keys())
    except Exception as e:
        print(f"Error reading INCAR file {incar_file}: {e}")
        return set()


def main():
    parser = argparse.ArgumentParser(description="Find tags that are not currently tracked in the database")
    parser.add_argument("root_dir", help="Root directory to search for INCAR files")
    parser.add_argument("--json_file", default="incar_data.json",
                       help="JSON file containing existing INCAR data (default: incar_data.json)")

    args = parser.parse_args()

    # 检查JSON文件是否存在
    if not os.path.exists(args.json_file):
        print(f"Error: JSON file '{args.json_file}' does not exist")
        return 1

    print(f"Extracting tags from JSON file: {args.json_file}")
    existing_tags = extract_all_tags_from_json(args.json_file)
    print(f"Found {len(existing_tags)} tags in the existing database")

    print(f"Searching for INCAR files in: {args.root_dir}")
    incar_files = find_all_incar_files(args.root_dir)
    print(f"Found {len(incar_files)} INCAR files")

    # 从所有INCAR文件中提取标签
    all_found_tags = set()

    # 使用tqdm显示进度条
    from tqdm import tqdm
    for incar_file in tqdm(incar_files, desc="Processing INCAR files", unit="file"):
        file_tags = extract_tags_from_incar_file(incar_file)
        all_found_tags.update(file_tags)

    # 找出未统计的标签
    missing_tags = all_found_tags - existing_tags

    print("\n" + "="*50)
    print("SUMMARY:")
    print(f"Total tags found in all INCAR files: {len(all_found_tags)}")
    print(f"Tags already in database: {len(existing_tags)}")
    print(f"Tags not currently tracked: {len(missing_tags)}")
    print("="*50)

    if missing_tags:
        print("\nTags not currently tracked in the database:")
        for tag in sorted(missing_tags):
            print(f"  - {tag}")
    else:
        print("\nNo missing tags found - all tags are already tracked!")

    return 0


if __name__ == "__main__":
    exit(main())