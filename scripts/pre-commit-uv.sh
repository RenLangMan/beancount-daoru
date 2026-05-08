#!/bin/bash

###
# @Author: error: git config user.name & please set dead value or install git
# @Date: 2026-04-15 22:05:34
# @LastEditors: error: git config user.name & please set dead value or install git
# @LastEditTime: 2026-04-15 22:19:21
# @FilePath: \\beancount-daoru\\scripts\\pre-commit-uv.sh
# @Description:
# Copyright (c) 2026 by ${git_name_email}, All Rights Reserved.
# ==============================================
###

# scripts/pre-commit-uv.sh - 为 pre-commit 查找 uv 命令

set -e

# 检测操作系统
case "$OSTYPE" in
  msys* | cygwin* | win32* | mingw*)
    IS_WINDOWS=true
    VENV_BIN="Scripts"
    ;;
  *)
    IS_WINDOWS=false
    VENV_BIN="bin"
    ;;
esac

# 获取项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "${PROJECT_ROOT}" || exit 1

# 加载环境配置
if [ -f "${PROJECT_ROOT}/.env" ]; then
  source "${PROJECT_ROOT}/.env"
fi

# 查找 uv 命令（与 dev.sh 逻辑一致）
find_uv_cmd() {
  # 使用 VENV_BIN 而不是硬编码路径
  if [ -f ".venv/$VENV_BIN/uv" ] || [ -f ".venv/$VENV_BIN/uv.exe" ]; then
    echo ".venv/$VENV_BIN/uv"
  elif command -v uv &> /dev/null; then
    echo "uv"
  elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv" ]; then
    echo "$UV_PATH/uv"
  elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv.exe" ]; then
    echo "$UV_PATH/uv.exe"
  else
    echo ""
  fi
}

UV_CMD=$(find_uv_cmd)

if [ -z "$UV_CMD" ]; then
  echo "ERROR: uv command not found" >&2
  exit 1
fi

# 可选：如果需要 Windows 特定处理
if [ "$IS_WINDOWS" = true ]; then
  # Windows 特定逻辑，例如转换路径格式
  # 当前脚本已经能正确处理，这里留作扩展
  :
fi

# 执行 uv 命令（传递所有参数）
exec "$UV_CMD" "$@"
