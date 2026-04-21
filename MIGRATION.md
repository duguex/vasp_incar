# VASP INCAR Query Tool — 迁移指南

## 文件清单

目标目录需要包含：

```
vasp_incar/
├── CLAUDE.md                    # Agent 项目文档
├── vasp_query/
│   ├── __init__.py
│   ├── __main__.py
│   ├── mcp_server.py            # MCP server（6 个工具）
│   ├── processor.py             # 数据预处理
│   ├── query.py                 # CLI 查询工具
│   └── data/
│       ├── tag_index.json       # 630 个结构化 tag
│       ├── wiki_full.json       # 1036 页 wiki 内容
│       └── tag_stats.json       # 207 个 tag 统计
├── incar_data.json              # 10,176 个 INCAR 配置
└── vasp_wiki_all_data.json      # 1,186 个 wiki 页面
```

## 迁移步骤

### 1. 复制目录

```bash
rsync -av /源路径/vasp_incar/ /目标路径/vasp_incar/
```

### 2. 安装依赖

```bash
pip install mcp fastmcp
```

> 其他依赖都是 Python 标准库（json, pathlib, re, argparse, asyncio），无需安装。

### 3. 全局注册 MCP

```bash
claude mcp add vasp-query --scope user -- python3 /绝对/路径/vasp_incar/vasp_query/mcp_server.py
```

**注意**：命令必须带 `python3` 前缀，因为 `mcp_server.py` 没有 shebang 声明。

验证：`claude mcp list` 应显示 `vasp-query` Connected。

### 4. 重启 Claude Code

MCP server 配置在 Claude Code 启动时加载，需要重启。

### 5. 验证

```bash
python3 -m vasp_query tag LEFG
```

或通过 MCP 调用 `get_tag(name="LEFG")`。

## 常见问题

### 工具没加载？

- 确认注册命令带了 `python3` 前缀
- 确认 `python3` 在 PATH 中
- 确认依赖已安装：`pip install mcp fastmcp`
- 重启 Claude Code

### 移除已注册的 MCP

```bash
claude mcp remove vasp-query
```
