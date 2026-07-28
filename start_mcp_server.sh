#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d "mcp_env" ]]; then
    echo "错误：虚拟环境不存在，请先运行 python3 -m venv mcp_env" >&2
    exit 1
fi

if [[ ! -f ".env" ]]; then
    echo "错误：.env 不存在，请先复制 .env.example 并填写认证信息" >&2
    exit 1
fi

source mcp_env/bin/activate
python server/mcp_server.py "${1:-streamable-http}"
