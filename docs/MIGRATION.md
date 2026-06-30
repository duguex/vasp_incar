# DFT Tools — 迁移指南

> 本文档适用于在新机器上部署 `dft-tools` 项目（合并后的 `vasp_query` + `omx_tools`）。
> 旧版 MCP server 已在 v0.2.0 移除，所有集成改为通过 Hermes Skill 注册。

## 文件清单

目标目录应包含：

```
dft-tools/
├── pyproject.toml              # 统一包配置 (name=dft-tools, v0.3.0)
├── dft_utils/                  # 共享工具
├── vasp_query/                 # VASP INCAR 查询 CLI
│   ├── query.py, _common.py, processor.py, fetcher.py
│   └── data/                   # 676 个 INCAR 标签 + 统计 + 向量
├── omx_tools/                  # OpenMX 工具链
│   ├── database.py, generator.py, vasp2omx.py, omp2vasp.py
│   ├── mapping/, parsers/, writers/, schemas/
│   └── tests/                  # 110+ 测试
├── openmx.db                   # v4.0 手册全文数据库 (3.4 MB)
├── openmx4.0_manual/           # HTML 手册 (263 页)
├── data/raw/                   # 原始 VASP wiki 数据 + INCAR 配置
├── skills/
│   ├── vasp-query/SKILL.md     # VASP agent 接口
│   └── omx-tools/SKILL.md      # OpenMX agent 接口
└── aliases.json                # 领域缩写映射
```

## 迁移步骤

### 1. 复制目录

```bash
rsync -av /源路径/dft-tools/ /目标路径/dft-tools/
```

### 2. 安装依赖

```bash
pip install -e ".[all]"          # 全装
# 或按需：
pip install -e ".[vasp]"         # VASP 查询 + 语义搜索
pip install -e ".[omx]"          # OpenMX 输入生成 + 格式转换
```

### 3. 注册 Hermes Skill

```bash
ln -s ~/vasp_wiki/skills/vasp-query/SKILL.md  ~/.hermes/skills/research/vasp-query/SKILL.md
ln -s ~/vasp_wiki/skills/omx-tools/SKILL.md   ~/.hermes/skills/research/omx-tools/SKILL.md
```

### 4. 验证

```bash
python3 -m vasp_query tag ENCUT          # VASP 标签查询
omx-db search "SCF convergence"          # OpenMX 手册搜索
omx-gen --list-templates                 # OpenMX 模板列表
```

### 5. 运行测试（可选）

```bash
python3 -m vasp_query.test_cli           # 22 个 VASP 测试
python3 -m pytest tests/ --ignore=tests/test_integration.py  # 109 个 OpenMX 测试
```

## 项目路径变更历史

| 版本 | 根目录 | 说明 |
|------|--------|------|
| v0.1.x | `~/vasp_incar/` | 仅 vasp-query，含 MCP server |
| v0.2.0 | `~/vasp_wiki/` | 移除 MCP，改为 Skill 集成 |
| v0.3.0 | `~/vasp_wiki/` | 合并 `omx-tools`，重命名为 `dft-tools` |

## 常见问题

### 数据库版本不匹配？

```bash
python3 -m vasp_query preprocess         # 重建 VASP 数据
# openmx.db 是预构建的，见 scripts/extract_keywords.py
```

### 安装后命令找不到？

确认 pip 安装的包在 PATH 中，或直接使用：
```bash
python3 -m vasp_query <command>
python3 -m omx_tools.database <command>
```
