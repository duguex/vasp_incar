# vasp-query MCP systemd user service

把 `vasp_query/mcp_server.py` 部署成 HTTP 端点(端口 8932),供远程 Claude Code 通过 HTTP transport 访问。

> 本仓库根目录的 `.mcp.json` 用的是 stdio transport(本地调用);
> 本目录用 HTTP transport(跨机器调用)。两者互不冲突,可同时使用。

## 快速安装

```bash
cd vasp-mcp-systemd-services
./setup.sh
```

`setup.sh` 会:
1. 把 `vasp-query.service` 复制到 `~/.config/systemd/user/`
2. `daemon-reload` + `enable --now`
3. 显示服务状态和端口监听情况

## 手动步骤

### 1. 安装

```bash
# 关键:必须先 cd,否则下一步 cp 找不到文件
cd vasp-mcp-systemd-services

cp vasp-query.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user start vasp-query
systemctl --user enable vasp-query
```

### 2. 开启开机自启

`systemctl --user` 默认**不会在系统启动时运行**,只在用户登录后启动。
要真正开机自启需要:

```bash
sudo loginctl enable-linger $USER
```

### 3. 检查状态

```bash
systemctl --user status vasp-query
ss -tln | grep 8932
```

## 路径修改

把 `vasp-query.service` 复制到 `~/.config/systemd/user/` 之后,根据你的环境改:

- `WorkingDirectory` — vasp_incar 项目根目录(默认 `/home/duguex/vasp_incar`)
- `Environment=PATH` — 包含 `mcp` 和 `fastmcp` 的 conda 环境路径
- `ExecStart` 中的 `python3` 绝对路径 — 对应环境里的 python 解释器

## Python 环境

服务依赖的 Python 包:

```bash
conda activate <env_name>  # 例如 dgkan_rocm_3.11
pip install mcp fastmcp
```

## 防火墙

如果其他机器要通过网络访问,放行端口 8932:

```bash
sudo ufw allow 8932/tcp
```

## Claude Code 远程配置

在客户端机器的 `~/.claude.json` 中:

```json
"mcpServers": {
  "vasp-query": {
    "type": "http",
    "url": "http://<server-ip>:8932/mcp"
  }
}
```
