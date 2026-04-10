#!/bin/bash
# scripts/activate.sh - 快速激活项目环境（跨平台:Windows Git Bash / Linux）

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 检测操作系统
case "$OSTYPE" in
    msys*|cygwin*|win32*|mingw*)
        IS_WINDOWS=true
        VENV_BIN="Scripts"
        ;;
    *)
        IS_WINDOWS=false
        VENV_BIN="bin"
        ;;
esac

# 加载 .env 配置（如果存在）
if [ -f "${PROJECT_ROOT}/.env" ]; then
    source "${PROJECT_ROOT}/.env"
fi

# 进入项目目录
cd "${PROJECT_ROOT}" || exit 1

# 检查必要的文件
if [ ! -d ".venv" ]; then
    echo "❌ 虚拟环境不存在，请先运行 ./scripts/setup.sh"
    exit 1
fi

# 激活虚拟环境
if [ "$IS_WINDOWS" = true ]; then
    source ".venv/Scripts/activate"
else
    source ".venv/bin/activate"
fi

# 设置 UV 配置（如果 .env 中有定义）
[ -n "$UV_LINK_MODE" ] && export UV_LINK_MODE="$UV_LINK_MODE"
[ -n "$UV_INDEX_URL" ] && export UV_INDEX_URL="$UV_INDEX_URL"
[ -n "$UV_CONCURRENT_DOWNLOADS" ] && export UV_CONCURRENT_DOWNLOADS="$UV_CONCURRENT_DOWNLOADS"
[ -n "$UV_CACHE_DIR" ] && export UV_CACHE_DIR="$UV_CACHE_DIR"

echo "✅ 虚拟环境已激活"
echo "🐍 Python: $(python --version 2>&1)"
echo "📁 Python 路径: $(which python)"
if command -v uv &> /dev/null; then
    echo "🔧 UV 版本: $(uv --version 2>&1)"
fi

# 显示快捷命令
echo
echo "📌 快捷命令:"
echo "  uv sync --all-extras --dev  # 同步依赖"
echo "  uv add <package>            # 添加依赖"
echo "  deactivate                  # 退出虚拟环境"
