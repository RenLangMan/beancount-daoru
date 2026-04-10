#!/bin/bash
# scripts/dev.sh - 开发环境管理脚本（跨平台）

set -e

# 颜色定义
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_success() { echo -e "${GREEN}✅${NC} $1"; }

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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 加载环境配置
if [ -f "${PROJECT_ROOT}/.env" ]; then
    source "${PROJECT_ROOT}/.env"
fi

# 进入项目目录
cd "${PROJECT_ROOT}" || { print_error "无法进入项目目录"; exit 1; }

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    print_error "虚拟环境不存在，请先运行: ./scripts/setup.sh"
    exit 1
fi

# 激活虚拟环境
if [ "$IS_WINDOWS" = true ]; then
    source .venv/Scripts/activate
else
    source .venv/bin/activate
fi

# 查找 uv 命令
UV_CMD=""
if [ -f ".venv/$VENV_BIN/uv" ] || [ -f ".venv/$VENV_BIN/uv.exe" ]; then
    UV_CMD=".venv/$VENV_BIN/uv"
elif command -v uv &> /dev/null; then
    UV_CMD="uv"
elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv" ]; then
    UV_CMD="$UV_PATH/uv"
elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv.exe" ]; then
    UV_CMD="$UV_PATH/uv.exe"
else
    print_error "未找到 uv 命令"
    exit 1
fi

# 显示当前环境信息
show_status() {
    echo
    echo "================== 当前环境状态 =================="
    echo -e "${BLUE}项目目录:${NC} $PROJECT_ROOT"
    echo -e "${BLUE}操作系统:${NC} $([ "$IS_WINDOWS" = true ] && echo "Windows" || echo "Linux")"
    echo -e "${BLUE}Python:${NC} $(python --version 2>&1)"
    echo -e "${BLUE}Python 路径:${NC} $(which python)"
    echo -e "${BLUE}UV:${NC} $("$UV_CMD" --version 2>&1)"
    echo -e "${BLUE}UV 路径:${NC} $UV_CMD"
    echo "=================================================="
}

# 同步依赖
sync_deps() {
    local upgrade=$1
    echo "同步依赖..."
    if [ "$upgrade" = "upgrade" ]; then
        print_info "更新所有依赖到最新版本..."
        "$UV_CMD" sync --upgrade --all-extras --link-mode=copy
    else
        "$UV_CMD" sync --all-extras --link-mode=copy
    fi
    print_success "依赖同步完成"
}

# 运行测试
run_tests() {
    echo "运行测试..."
    if python -m pytest --version &> /dev/null; then
        python -m pytest "$@"
    else
        print_error "pytest 未安装，请运行: $UV_CMD add pytest"
    fi
}

# 构建项目
build_project() {
    echo "构建项目..."
    "$UV_CMD" build
    print_success "构建完成"
}

# 清理缓存
clean_cache() {
    echo "清理缓存..."
    "$UV_CMD" cache clean
    # 清理 Python 缓存文件
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    print_success "缓存已清理"
}

# 显示快捷命令
show_aliases() {
    echo
    echo "================== 快捷命令 =================="
    echo "  $UV_CMD sync --all-extras --dev   同步依赖"
    echo "  $UV_CMD add <package>             添加依赖"
    echo "  $UV_CMD remove <package>          移除依赖"
    echo "  python -m pytest                  运行测试"
    echo "  $UV_CMD build                     构建项目"
    echo "=============================================="
}

# 显示帮助
show_help() {
    echo
    echo "================== 使用说明 =================="
    echo "直接运行菜单: ./scripts/dev.sh"
    echo "或使用命令行参数:"
    echo "  ./scripts/dev.sh status   - 查看环境状态"
    echo "  ./scripts/dev.sh sync      - 同步依赖"
    echo "  ./scripts/dev.sh upgrade   - 更新所有依赖"
    echo "  ./scripts/dev.sh test      - 运行测试"
    echo "  ./scripts/dev.sh build     - 构建项目"
    echo "  ./scripts/dev.sh clean     - 清理缓存"
    echo "  ./scripts/dev.sh aliases   - 显示快捷命令"
    echo "=============================================="
}

# 命令行参数处理
case "$1" in
    status|st)      show_status ;;
    sync|s)         sync_deps ;;
    upgrade|up)     sync_deps "upgrade" ;;
    test|t)         shift; run_tests "$@" ;;
    build|b)        build_project ;;
    clean|c)        clean_cache ;;
    aliases|alias|a) show_aliases ;;
    help|-h|--help|h) show_help ;;
    "") ;;
    *) print_error "未知命令: $1"; show_help; exit 1 ;;
esac

# 如果有命令行参数，直接退出
if [ -n "$1" ]; then
    exit 0
fi

# 显示菜单
show_menu() {
    echo
    echo "================== Beancount Daoru 开发工具 =================="
    echo -e "  ${GREEN}1${NC}. 同步依赖 (uv sync)"
    echo -e "  ${GREEN}2${NC}. 更新所有依赖 (uv sync --upgrade)"
    echo -e "  ${GREEN}3${NC}. 运行测试 (pytest)"
    echo -e "  ${GREEN}4${NC}. 构建项目 (uv build)"
    echo -e "  ${GREEN}5${NC}. 查看已安装包 (uv pip list)"
    echo -e "  ${GREEN}6${NC}. 清理缓存"
    echo -e "  ${GREEN}7${NC}. 查看环境状态"
    echo -e "  ${GREEN}8${NC}. 显示快捷命令"
    echo -e "  ${GREEN}9${NC}. 退出"
    echo "=============================================================="
    echo -n "请选择 [1-9]: "
}

# 主循环
while true; do
    show_menu
    read -r choice
    echo
    case $choice in
        1) sync_deps ;;
        2) sync_deps "upgrade" ;;
        3) run_tests ;;
        4) build_project ;;
        5) echo "已安装的包:"; "$UV_CMD" pip list ;;
        6) clean_cache ;;
        7) show_status ;;
        8) show_aliases ;;
        9) echo "退出"; exit 0 ;;
        *) print_error "无效选择" ;;
    esac
    echo
    read -p "按 Enter 键继续..."
done