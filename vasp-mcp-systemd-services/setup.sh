#!/bin/bash
# vasp-query systemd user service 一键安装脚本
# Idempotent: 可以重复运行。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="vasp-query.service"
TARGET="$HOME/.config/systemd/user/$SERVICE_NAME"

echo "==> Source: $SCRIPT_DIR/$SERVICE_NAME"
echo "==> Target: $TARGET"

mkdir -p "$(dirname "$TARGET")"
cp "$SCRIPT_DIR/$SERVICE_NAME" "$TARGET"
echo "✓ 已复制 $SERVICE_NAME"

echo
echo "==> 重新加载 systemd"
systemctl --user daemon-reload

echo
echo "==> 启动并启用 $SERVICE_NAME"
systemctl --user enable --now "$SERVICE_NAME"

echo
echo "==> 提示: 如果服务没有开机自启,运行:"
echo "    sudo loginctl enable-linger \$USER"

echo
echo "==> 当前状态"
systemctl --user status "$SERVICE_NAME" --no-pager || true

echo
echo "==> 端口监听 (8932)"
ss -tln 2>/dev/null | grep 8932 || echo "(尚未监听 8932)"
