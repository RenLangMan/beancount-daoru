#!/bin/bash
# scripts/setup.sh - 项目环境设置脚本（跨平台）
# shellcheck source=/dev/null
# shellcheck source=/dev/null
# shellcheck source=/dev/null

set -e

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 检测操作系统
case "$OSTYPE" in
  msys* | cygwin* | win32* | mingw*)
    IS_WINDOWS=true
    VENV_BIN="Scripts"
    ;;
  *)
    IS_WINDOWS=false
    # VENV_BIN is used on Windows only, defined here for consistency
    # shellcheck disable=SC2034
    VENV_BIN="bin"
    ;;
esac

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 加载 .env 配置
if [ -f "${PROJECT_ROOT}/.env" ]; then
  source "${PROJECT_ROOT}/.env"
fi

# 查找 uv 命令（优先 PATH，其次 .env 中自定义路径）
UV_CMD=""
if command -v uv &>/dev/null; then
  UV_CMD="uv"
elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv" ]; then
  UV_CMD="$UV_PATH/uv"
elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv.exe" ]; then
  UV_CMD="$UV_PATH/uv.exe"
else
  print_error "未找到 uv 命令，请先安装 uv"
  exit 1
fi

# 查找 python 命令
PYTHON_CMD=""
if [ -n "$PYTHON_PATH" ] && [ -f "$PYTHON_PATH/python" ]; then
  PYTHON_CMD="$PYTHON_PATH/python"
elif [ -n "$PYTHON_PATH" ] && [ -f "$PYTHON_PATH/python.exe" ]; then
  PYTHON_CMD="$PYTHON_PATH/python.exe"
elif command -v python &>/dev/null; then
  PYTHON_CMD="python"
elif command -v python3 &>/dev/null; then
  PYTHON_CMD="python3"
else
  print_error "未找到 python 命令"
  exit 1
fi

print_info "UV 命令: $UV_CMD"
print_info "Python 命令: $PYTHON_CMD"

export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
[ -n "$UV_INDEX_URL" ] && export UV_INDEX_URL="$UV_INDEX_URL"
[ -n "$UV_CONCURRENT_DOWNLOADS" ] && export UV_CONCURRENT_DOWNLOADS="$UV_CONCURRENT_DOWNLOADS"

# 进入项目目录
cd "${PROJECT_ROOT}" || exit 1

# 询问是否重建虚拟环境
read -p "是否重建虚拟环境？(y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
  print_info "删除旧的虚拟环境..."
  rm -rf .venv
  print_info "创建新的虚拟环境..."
  "$UV_CMD" venv --python "$PYTHON_CMD"
fi

# 激活虚拟环境
if [ "$IS_WINDOWS" = true ]; then
  source .venv/Scripts/activate
else
  source .venv/bin/activate
fi

print_info "使用 $(python --version 2>&1)"
print_info "安装项目依赖（包括开发依赖）..."
"$UV_CMD" sync --all-extras --dev --link-mode=copy

print_info "设置完成！虚拟环境已激活: $(which python)"
echo
print_info "运行 'deactivate' 退出虚拟环境"
