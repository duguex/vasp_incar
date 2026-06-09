# INCAR-_-

## 项目概述

这是一个专门处理 VASP (Vienna Ab initio Simulation Package) 输入文件 INCAR 的工具集。项目的主要目的是提供一套完整的工具来管理、验证、比较和生成 VASP 的 INCAR 文件，以帮助材料科学计算研究人员更高效地进行计算参数设置和管理。

## 核心组件

### Python 脚本

- **`incar.py`**：验证 INCAR 文件与参考数据库的一致性，检查当前 INCAR 参数与材料系统预期值之间的不一致性。需要 POSCAR 文件来识别材料系统。

- **`incar_ref.py`**：基于配置的 JSON 数据库生成参考 INCAR 文件。允许按参数值查询并生成匹配配置中最常用的参数值的 INCAR 文件。

- **`extract_incar.py`**：从目录树中提取 INCAR 文件并保存到 JSON 文件中。支持多进程并行处理并包含去重步骤。

- **`compare_incar.py`**：比较两个 INCAR 文件并报告共同参数、每个文件独有的参数以及值不同的参数。

- **`tag_incar.py`**：提供交互式界面，使用预定义标签修改 INCAR 文件。标签对应于常见的 VASP 设置（如 SOC、HSE0、PBE0、自旋极化），便于轻松修改 INCAR 参数。

### 数据文件

- **`incar_data.json`**：一个大型 JSON 文件，包含从各种 VASP 计算中提取的 INCAR 配置，用作 `incar.py` 和 `incar_ref.py` 的参考数据库。

### Shell 脚本

- **`sample_incar.sh`**：一个 Bash 脚本，从指定目录中随机采样 INCAR 文件并将它们复制到具有编号文件名的新目录中。

### 示例 INCAR 文件

- **`incar_samples/`**：一个包含示例 INCAR 文件的目录，可用于测试或参考。

## 使用方法

### 先决条件

- Python 3.x
- `pymatgen` 库
- `tqdm` 库（用于 `extract_incar.py` 中的进度条）

### 常见工作流程

1. **提取 INCAR 配置**：
   - 使用 `extract_incar.py` 扫描包含 VASP 计算的目录树并将所有 INCAR 文件提取到单个 JSON 文件中。
   - 示例：`python extract_incar.py /path/to/vasp/calculations -o my_incar_data.json`

2. **生成参考 INCAR 文件**：
   - 使用 `incar_ref.py` 根据 JSON 数据库中的特定参数值生成 INCAR 文件。
   - 示例：`python incar_ref.py ALGO=All AEXX=0.25 -o INCAR_hse0`

3. **验证 INCAR 文件**：
   - 使用 `incar.py` 将现有 INCAR 文件与参考数据库（`incar_data.json`）进行检查。
   - 需要在当前目录中有一个 `POSCAR` 文件来识别材料系统。

4. **比较 INCAR 文件**：
   - 使用 `compare_incar.py` 直接比较两个 INCAR 文件。
   - 示例：`python compare_incar.py`（比较当前目录中的 INCAR_6 和 INCAR_8）

5. **交互式 INCAR 修改**：
   - 使用 `tag_incar.py` 使用预定义标签交互式修改 INCAR 文件。
   - 示例：`python tag_incar.py soc spin=2`（启用自旋-轨道耦合并将自旋设置为 2）

## 开发约定

- Python 脚本使用 argparse 进行命令行参数解析。
- 脚本设计为在读取文件时优雅地处理错误。
- `tag_incar.py` 中的标记系统提供了一种方便的方法来修改常见 INCAR 参数，而无需直接编辑文件。
- JSON 数据库（`incar_data.json`）是基于参考操作的关键组件。