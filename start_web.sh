#!/usr/bin/env bash
# 公众号封面工具 - 一键启动脚本（先进入虚拟环境，再启动 Web 前端）
set -euo pipefail

# 定位到脚本所在目录（项目根目录），无论从哪调用都能正确运行
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$BASE_DIR/.venv/bin/python"

cd "$BASE_DIR"

# 优先用 venv 里的 python（不依赖是否已激活）
PY=""
if [ -x "$VENV_PY" ]; then
    PY="$VENV_PY"
else
    # 回退：如果环境尚未激活但系统有 python，尝试用当前 python
    PY="$(command -v python || command -v python3 || true)"
fi

if [ -z "$PY" ]; then
    echo "❌ 未找到 python。请先激活虚拟环境：source $BASE_DIR/.venv/bin/activate" >&2
    exit 1
fi

echo "✅ 使用解释器: $PY"
exec "$PY" "$BASE_DIR/web_server.py"