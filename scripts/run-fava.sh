#!/bin/bash
# scripts/run-fava.sh - 启动 Fava Web 界面
# shellcheck source=/dev/null
# shellcheck source=/dev/null

set -e

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 账簿文件路径
BEANCOUNT_FILE="$PROJECT_ROOT/beancount-data/main.bean"

# 默认端口
PORT=${1:-5000}

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}启动 Fava 记账工具${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查账簿文件是否存在
if [ ! -f "$BEANCOUNT_FILE" ]; then
  echo -e "${YELLOW}错误: 找不到账簿文件 $BEANCOUNT_FILE${NC}"
  exit 1
fi

# 检查虚拟环境是否存在
if [ -d "$PROJECT_ROOT/.venv" ]; then
  echo -e "${GREEN}激活虚拟环境...${NC}"
  source "$PROJECT_ROOT/.venv/Scripts/activate"
elif [ -d "$PROJECT_ROOT/venv" ]; then
  echo -e "${GREEN}激活虚拟环境...${NC}"
  source "$PROJECT_ROOT/venv/Scripts/activate"
else
  echo -e "${YELLOW}警告: 未找到虚拟环境，使用系统 Python${NC}"
fi

# 检查 fava 是否安装
if ! command -v fava &> /dev/null; then
  echo -e "${YELLOW}错误: fava 未安装，请先运行: pip install fava${NC}"
  exit 1
fi

echo -e "${GREEN}账簿文件: $BEANCOUNT_FILE${NC}"
echo -e "${GREEN}访问地址: http://localhost:$PORT${NC}"
echo -e "${GREEN}按 Ctrl+C 停止服务${NC}"
echo -e "${GREEN}========================================${NC}"

# 启动 Fava
cd "$PROJECT_ROOT/beancount-data"
fava "$BEANCOUNT_FILE" --port "$PORT"
