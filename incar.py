#!/usr/bin/env python3

from pymatgen.io.vasp import Incar
from pymatgen.core import Structure
import json
from copy import deepcopy

if os.path.exists("/mnt/shared/rc-tmp"):
    rcTmpPath = "/mnt/shared/rc-tmp"
else:
    rcTmpPath = os.path.expanduser("~/rc-tmp")

converted_repo = json.load(open(f"{rcTmpPath}/vasp_input_repo.json"))
small_repo = {tuple(k.split("_")): v for k, v in converted_repo.items()}

poscar = Structure.from_file("POSCAR")
symbol_list = tuple([i.symbol for i in poscar.elements])

if symbol_list in small_repo:
    print("嘻嘻")
else:
    print("不嘻嘻")
    symbol_list = tuple(input(f"没有找到当前目录的体系{symbol_list}, 看看其他的？").strip().split())
    if symbol_list in small_repo:
        print("嘻嘻")
    else:
        print("不嘻嘻")
        exit()

incar = Incar.from_file("INCAR")
tmp_repo = deepcopy(small_repo[symbol_list])

print(60 * "#")
print(" ".join(symbol_list))
print(60 * "#")
for key, value in incar.items():
    values_repo = tmp_repo.pop(key, None)
    if values_repo is not None and value not in values_repo:
        print(f"{key:<20} = {value:<20} {str(values_repo):<20}")

if tmp_repo:
    print(60 * "#")
    print("As a reminder, the following INCAR tags are not in the repo:")
    for key, value in tmp_repo.items():
        print(f"{key:<20} = {str(value):<20}")

