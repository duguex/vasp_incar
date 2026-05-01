# VASP MCP 系统服务备份

## 文件说明

- `vaspilot.service` — VASPilot MCP 服务器 (端口 8933)
- `vasp-query.service` — vasp-query MCP 服务器 (端口 8932)
- `README.md` — 此说明文件

## 迁移到新机器的步骤

### 1. 复制 service 文件

```bash
scp vasp-mcp-systemd-services/*.service user@new-machine:~/vasp-mcp-systemd-services/
```

### 2. 在新机器上安装

```bash
# 复制到 systemd 目录
cp vasp*.service ~/.config/systemd/user/

# 重载 systemd
systemctl --user daemon-reload

# 启动服务
systemctl --user start vaspilot
systemctl --user start vasp-query

# 设置为开机自启
systemctl --user enable vaspilot
systemctl --user enable vasp-query
```

### 3. 检查服务状态

```bash
systemctl --user status vaspilot vasp-query
ss -tlnp | grep -E "8932|8933"
```

## 注意事项

### 路径修改

不同机器的目录结构可能不同，需要修改 service 文件中的路径：

**vaspilot.service** 需要修改：
- `WorkingDirectory` — VASPilot 项目根目录
- `Environment=PMG_VASP_PSP_DIR` — POTCAR 目录路径
- `ExecStart` 中的 `config_path` — 配置文件路径

**vasp-query.service** 需要修改：
- `WorkingDirectory` — vasp_query 项目目录
- `Environment=PATH` — 正确的 conda 环境路径
- `ExecStart` 中的可执行文件和项目路径

### Python 环境

确保新机器上安装了相应的 Python 包：

**vaspilot**:
```bash
# 使用 vasp 项目的虚拟环境
cd /path/to/VASPilot
uv run pip install -e .
```

**vasp-query**:
```bash
# 确保 conda 环境中安装了 mcp 和 fastmcp
conda activate dgkan_rocm_3.11  # 或其他环境
pip install mcp fastmcp
```

### 防火墙

如果其他机器要通过网络访问，确保防火墙放行端口：
- 8932 (vasp-query)
- 8933 (VASPilot)

```bash
sudo ufw allow 8932/tcp
sudo ufw allow 8933/tcp
```

### Claude Code 配置

如果要在其他机器上使用 Claude Code 访问这些 MCP 服务，需要更新 `~/.claude.json` 中的 URL：

```json
"mcpServers": {
  "vasp-query": {
    "type": "http",
    "url": "http://<server-ip>:8932/mcp"
  },
  "VASPilot": {
    "type": "http",
    "url": "http://<server-ip>:8933/mcp"
  }
}
```
