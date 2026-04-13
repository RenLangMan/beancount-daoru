#!/bin/bash
# scripts/dev.sh - 完整的开发环境管理脚本（一站式开发流水线）
# shellcheck source=/dev/null
# shellcheck source=/dev/null
# shellcheck source=/dev/null

set -e

# ==================== 颜色定义 ====================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'

print_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
print_success() { echo -e "${GREEN}✅${NC} $1"; }
print_step() { echo -e "${CYAN}▶${NC} $1"; }
print_title() {
  echo -e "\n${MAGENTA}════════════════════════════════════════════════════════${NC}"
  echo -e "${MAGENTA}  $1${NC}"
  echo -e "${MAGENTA}════════════════════════════════════════════════════════${NC}\n"
}

# ==================== 检测操作系统 ====================
case "$OSTYPE" in
  msys* | cygwin* | win32* | mingw*)
    IS_WINDOWS=true
    VENV_BIN="Scripts"
    PYTHON_EXE="python.exe"
    ;;
  *)
    IS_WINDOWS=false
    VENV_BIN="bin"
    PYTHON_EXE="python"
    ;;
esac

# ==================== 路径设置 ====================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "${PROJECT_ROOT}" || {
  print_error "无法进入项目目录"
  exit 1
}

# ==================== 加载环境配置 ====================
if [ -f "${PROJECT_ROOT}/.env" ]; then
  source "${PROJECT_ROOT}/.env"
fi

# ==================== 查找命令 ====================
find_uv_cmd() {
  if [ -f ".venv/$VENV_BIN/uv" ] || [ -f ".venv/$VENV_BIN/uv.exe" ]; then
    echo ".venv/$VENV_BIN/uv"
  elif command -v uv &>/dev/null; then
    echo "uv"
  elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv" ]; then
    echo "$UV_PATH/uv"
  elif [ -n "$UV_PATH" ] && [ -f "$UV_PATH/uv.exe" ]; then
    echo "$UV_PATH/uv.exe"
  else
    echo ""
  fi
}

find_python_cmd() {
  if [ -n "$PYTHON_PATH" ] && [ -f "$PYTHON_PATH/$PYTHON_EXE" ]; then
    echo "$PYTHON_PATH/$PYTHON_EXE"
  elif command -v python &>/dev/null; then
    echo "python"
  elif command -v python3 &>/dev/null; then
    echo "python3"
  else
    echo ""
  fi
}

# ==================== 虚拟环境管理 ====================
check_venv() {
  if [ ! -d ".venv" ]; then
    return 1
  fi
  return 0
}

create_venv() {
  local python_cmd=$1
  local uv_cmd=$2

  print_step "创建虚拟环境..."
  if [ -n "$uv_cmd" ] && [ "$uv_cmd" != "uv" ]; then
    "$uv_cmd" venv --python "$python_cmd" --seed # 添加 --seed 安装 pip
  else
    if command -v uv &>/dev/null; then
      uv venv --python "$python_cmd" --seed # 添加 --seed 安装 pip
    else
      "$python_cmd" -m venv .venv
    fi
  fi
  print_success "虚拟环境创建完成"
}

activate_venv() {
  if [ "$IS_WINDOWS" = true ]; then
    source .venv/Scripts/activate 2>/dev/null || true
  else
    source .venv/bin/activate 2>/dev/null || true
  fi
}

recreate_venv() {
  print_warn "重建虚拟环境..."
  rm -rf .venv
  local python_cmd
  python_cmd=$(find_python_cmd)
  local uv_cmd
  uv_cmd=$(find_uv_cmd)
  create_venv "$python_cmd" "$uv_cmd"
}

# ==================== 依赖管理 ====================
sync_deps() {
  local upgrade=$1
  local uv_cmd
  uv_cmd=$(find_uv_cmd)

  if [ -z "$uv_cmd" ]; then
    print_error "未找到 uv 命令"
    return 1
  fi

  print_step "同步依赖..."
  export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
  [ -n "$UV_INDEX_URL" ] && export UV_INDEX_URL="$UV_INDEX_URL"
  [ -n "$UV_CONCURRENT_DOWNLOADS" ] && export UV_CONCURRENT_DOWNLOADS="$UV_CONCURRENT_DOWNLOADS"

  if [ "$upgrade" = "upgrade" ]; then
    print_info "更新所有依赖到最新版本..."
    "$uv_cmd" sync --upgrade --all-extras --link-mode=copy
  else
    "$uv_cmd" sync --all-extras --link-mode=copy
  fi
  print_success "依赖同步完成"
}

add_dep() {
  local package=$1
  local uv_cmd
  uv_cmd=$(find_uv_cmd)

  if [ -z "$package" ]; then
    print_error "请指定包名"
    return 1
  fi

  print_step "添加依赖: $package"
  "$uv_cmd" add "$package"
  print_success "依赖添加完成"
}

remove_dep() {
  local package=$1
  local uv_cmd
  uv_cmd=$(find_uv_cmd)

  if [ -z "$package" ]; then
    print_error "请指定包名"
    return 1
  fi

  print_step "移除依赖: $package"
  "$uv_cmd" remove "$package"
  print_success "依赖移除完成"
}

# ==================== 代码检查 ====================
run_ruff_check() {
  print_step "Ruff 代码检查..."
  uv run ruff check .
  print_success "Ruff 检查通过"
}

run_ruff_format() {
  print_step "Ruff 代码格式化检查..."
  uv run ruff format . --check
  print_success "代码格式正确"
}

run_shellcheck() {
  print_step "ShellCheck 脚本检查..."

  # 查找 shellcheck 命令
  SHELLCHECK_CMD=""
  if [ -f ".venv/Scripts/shellcheck.exe" ]; then
    SHELLCHECK_CMD=".venv/Scripts/shellcheck.exe"
  elif command -v shellcheck &>/dev/null; then
    SHELLCHECK_CMD="shellcheck"
  fi

  if [ -n "$SHELLCHECK_CMD" ]; then
    $SHELLCHECK_CMD scripts/*.sh || true
    print_success "ShellCheck 检查完成"
  else
    print_warn "shellcheck 未安装，跳过 Shell 脚本检查"
  fi
}

run_shfmt() {
  print_step "shfmt 格式化检查..."

  # 查找 shfmt 命令
  SHFMT_CMD=""
  if [ -f ".venv/Scripts/shfmt.exe" ]; then
    SHFMT_CMD=".venv/Scripts/shfmt.exe"
  elif command -v shfmt &>/dev/null; then
    SHFMT_CMD="shfmt"
  fi

  if [ -n "$SHFMT_CMD" ]; then
    $SHFMT_CMD -d scripts/*.sh
    print_success "Shell 脚本格式正确"
  else
    print_warn "shfmt 未安装，跳过格式化检查"
  fi
}

run_basedpyright() {
  print_step "Basedpyright 类型检查..."
  if uv run basedpyright --version &>/dev/null; then
    uv run basedpyright
    print_success "类型检查通过"
  else
    print_warn "basedpyright 未安装，跳过类型检查"
  fi
}

run_all_checks() {
  print_title "运行代码质量检查"
  run_ruff_check
  echo
  run_ruff_format
  echo
  run_shellcheck
  echo
  run_shfmt
  echo
  run_basedpyright
  print_success "所有检查通过！"
}

fix_code() {
  print_title "自动修复代码问题"
  print_step "格式化 Python 代码..."
  uv run ruff format .
  print_step "修复 Python 问题..."
  uv run ruff check . --fix
  print_step "格式化 Shell 脚本..."

  SHFMT_CMD=""
  if [ -f ".venv/Scripts/shfmt.exe" ]; then
    SHFMT_CMD=".venv/Scripts/shfmt.exe"
  elif command -v shfmt &>/dev/null; then
    SHFMT_CMD="shfmt"
  fi

  if [ -n "$SHFMT_CMD" ]; then
    $SHFMT_CMD -w scripts/*.sh
    print_success "Shell 脚本格式化完成"
  else
    print_warn "shfmt 未安装，跳过 Shell 脚本格式化"
  fi
  print_success "代码修复完成"
}

# ==================== 测试 ====================
run_tests() {
  local -a args
  args=("$@")
  print_title "运行测试"

  # 如果没有传递参数，默认使用 -v
  if [ ${#args[@]} -eq 0 ]; then
    args=("-v")
  fi

  if uv run pytest --version &>/dev/null; then
    uv run pytest "${args[@]}"
    print_success "测试完成"
  else
    print_error "pytest 未安装"
    return 1
  fi
}

run_tests_with_coverage() {
  print_title "运行测试（带覆盖率）"

  if uv run pytest --cov --version &>/dev/null; then
    uv run pytest --cov=src --cov-report=term --cov-report=html --cov-report=xml -v
    print_success "测试完成"
    echo
    print_info "覆盖率报告:"
    echo "  - HTML: htmlcov/index.html"
    echo "  - XML:  coverage.xml"
  else
    print_error "pytest-cov 未安装，请运行: ./scripts/dev.sh add pytest-cov"
    return 1
  fi
}

run_specific_test() {
  local test_path=$1
  if [ -z "$test_path" ]; then
    print_error "请指定测试文件或目录"
    return 1
  fi

  print_step "运行测试: $test_path"
  uv run pytest "$test_path" -v
}

# ==================== 构建与发布 ====================
build_project() {
  print_title "构建项目"
  local uv_cmd
  uv_cmd=$(find_uv_cmd)
  "$uv_cmd" build
  print_success "构建完成"
  echo
  print_info "构建产物位于 dist/ 目录"
}

check_publish() {
  print_title "检查发布配置"

  if uv run twine check dist/* &>/dev/null; then
    uv run twine check dist/*
    print_success "发布配置检查通过"
  else
    print_warn "twine 未安装，跳过检查"
    print_info "安装: ./scripts/dev.sh add twine"
  fi
}

publish_to_testpypi() {
  print_title "发布到 TestPyPI"

  if uv run twine upload --repository testpypi dist/* --skip-existing; then
    print_success "发布到 TestPyPI 完成"
  else
    print_error "发布失败"
    return 1
  fi
}

publish_to_pypi() {
  print_title "发布到 PyPI"

  print_warn "即将发布到正式 PyPI，请确认版本号正确"
  read -r -p "确认发布？(y/N): " -n 1
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    if uv run twine upload dist/*; then
      print_success "发布到 PyPI 完成"
    else
      print_error "发布失败"
      return 1
    fi
  else
    print_info "已取消发布"
  fi
}

# ==================== 清理 ====================
clean_cache() {
  print_title "清理缓存"

  print_step "清理 uv 缓存..."
  local uv_cmd
  uv_cmd=$(find_uv_cmd)
  "$uv_cmd" cache clean 2>/dev/null || true

  print_step "清理 Python 缓存文件..."
  find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
  find . -type f -name "*.pyc" -delete 2>/dev/null || true
  find . -type f -name ".coverage" -delete 2>/dev/null || true
  find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
  find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
  find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
  find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true

  print_success "缓存清理完成"
}

clean_all() {
  print_title "完全清理"
  print_warn "这将删除虚拟环境和所有缓存"
  read -r -p "确认清理？(y/N): " -n 1
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    clean_cache
    print_step "删除虚拟环境..."
    rm -rf .venv
    print_step "删除构建产物..."
    # shellcheck disable=SC2035
    rm -rf dist/ build/ *.egg-info/
    print_success "完全清理完成"
  else
    print_info "已取消清理"
  fi
}

# ==================== Pre-commit ====================
run_precommit_install() {
  print_title "安装 pre-commit hooks"
  bash "${SCRIPT_DIR}/setup_precommit.sh"
  print_success "pre-commit 安装完成"
}

run_precommit() {
  print_title "运行 pre-commit 检查"
  if command -v pre-commit &>/dev/null; then
    pre-commit run --all-files
    print_success "pre-commit 检查完成"
  else
    print_warn "pre-commit 未安装"
    print_info "运行: ./scripts/dev.sh precommit-install"
    return 1
  fi
}

# ==================== 环境信息 ====================
show_status() {
  print_title "当前环境状态"

  echo -e "${BLUE}项目信息:${NC}"
  echo "  目录: $PROJECT_ROOT"
  echo "  操作系统: $([ "$IS_WINDOWS" = true ] && echo "Windows" || echo "Linux")"
  echo

  echo -e "${BLUE}Python 环境:${NC}"
  if check_venv; then
    activate_venv
    echo "  虚拟环境: 已创建"
    echo "  Python 版本: $(python --version 2>&1)"
    echo "  Python 路径: $(which python)"
  else
    echo "  虚拟环境: 未创建"
  fi
  echo

  echo -e "${BLUE}工具链:${NC}"
  local uv_cmd
  uv_cmd=$(find_uv_cmd)
  if [ -n "$uv_cmd" ]; then
    echo "  UV: $($uv_cmd --version 2>&1)"
    echo "  UV 路径: $uv_cmd"
  else
    echo "  UV: 未安装"
  fi
  echo

  if check_venv; then
    echo -e "${BLUE}已安装的包:${NC}"
    uv pip list 2>/dev/null | head -20
    local pkg_count
    pkg_count=$(uv pip list 2>/dev/null | wc -l)
    if [ "$pkg_count" -gt 20 ]; then
      echo "  ... 共 $pkg_count 个包"
    fi
  fi
}

show_aliases() {
  print_title "快捷命令参考"
  echo -e "${CYAN}依赖管理:${NC}"
  echo "  ./scripts/dev.sh sync              # 同步依赖"
  echo "  ./scripts/dev.sh upgrade           # 更新所有依赖"
  echo "  ./scripts/dev.sh add <package>     # 添加依赖"
  echo "  ./scripts/dev.sh remove <package>  # 移除依赖"
  echo
  echo -e "${CYAN}代码质量:${NC}"
  echo "  ./scripts/dev.sh check             # 运行所有检查"
  echo "  ./scripts/dev.sh fix               # 自动修复问题"
  echo "  ./scripts/dev.sh lint              # 仅运行 Ruff 检查"
  echo "  ./scripts/dev.sh format            # 仅格式化代码"
  echo "  ./scripts/dev.sh type              # 仅类型检查"
  echo "  ./scripts/dev.sh shellcheck        # 仅 Shell 脚本检查"
  echo "  ./scripts/dev.sh shfmt             # 仅 Shell 格式化检查"
  echo
  echo -e "${CYAN}测试:${NC}"
  echo "  ./scripts/dev.sh test              # 运行测试"
  echo "  ./scripts/dev.sh test-cov          # 运行测试+覆盖率"
  echo "  ./scripts/dev.sh test-file <path>  # 运行指定测试"
  echo
  echo -e "${CYAN}构建与发布:${NC}"
  echo "  ./scripts/dev.sh build             # 构建项目"
  echo "  ./scripts/dev.sh publish-test      # 发布到 TestPyPI"
  echo "  ./scripts/dev.sh publish           # 发布到 PyPI"
  echo
  echo -e "${CYAN}环境管理:${NC}"
  echo "  ./scripts/dev.sh setup             # 完整环境设置"
  echo "  ./scripts/dev.sh reset             # 重建虚拟环境"
  echo "  ./scripts/dev.sh status            # 查看环境状态"
  echo "  ./scripts/dev.sh clean             # 清理缓存"
  echo "  ./scripts/dev.sh clean-all         # 完全清理"
  echo
  echo -e "${CYAN}开发流水线:${NC}"
  echo "  ./scripts/dev.sh pipeline          # 运行完整开发流水线"
  echo "  ./scripts/dev.sh ci                # CI 检查（无修复）"
  echo "  ./scripts/dev.sh precommit-install # 安装 pre-commit hooks"
  echo "  ./scripts/dev.sh precommit         # 运行 pre-commit 检查"
}

# ==================== 完整流水线 ====================
setup_full() {
  print_title "完整环境设置"

  # 1. 检查 uv
  local uv_cmd
  uv_cmd=$(find_uv_cmd)
  if [ -z "$uv_cmd" ]; then
    print_error "uv 未安装，请先安装: pip install uv"
    exit 1
  fi
  print_success "uv 已安装: $($uv_cmd --version)"

  # 2. 创建虚拟环境
  if check_venv; then
    read -r -p "虚拟环境已存在，是否重建？(y/N): " -n 1
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      recreate_venv
    fi
  else
    local python_cmd
    python_cmd=$(find_python_cmd)
    create_venv "$python_cmd" "$uv_cmd"
  fi

  # 3. 激活环境
  activate_venv

  # 4. 同步依赖
  sync_deps

  # 5. 显示状态
  show_status

  print_success "环境设置完成！"
}

run_ci_pipeline() {
  print_title "CI 检查流水线（无自动修复）"

  local has_error=0

  # 检查依赖
  print_step "检查依赖..."
  if ! check_venv; then
    print_error "虚拟环境不存在"
    has_error=1
  fi

  # Ruff 检查
  print_step "Ruff 检查..."
  if ! uv run ruff check .; then
    print_error "Ruff 检查失败"
    has_error=1
  fi

  # 格式检查
  print_step "格式检查..."
  if ! uv run ruff format . --check; then
    print_error "格式检查失败"
    has_error=1
  fi

  # 类型检查
  print_step "类型检查..."
  if uv run basedpyright --version &>/dev/null; then
    if ! uv run basedpyright; then
      print_error "类型检查失败"
      has_error=1
    fi
  fi

  # 测试
  print_step "运行测试..."
  if ! uv run pytest -v; then
    print_error "测试失败"
    has_error=1
  fi

  if [ $has_error -eq 0 ]; then
    print_success "CI 检查全部通过！"
  else
    print_error "CI 检查失败"
    exit 1
  fi
}

run_full_pipeline() {
  print_title "完整开发流水线"

  print_step "阶段 1/5: 环境检查"
  if ! check_venv; then
    print_warn "虚拟环境不存在，开始设置..."
    setup_full
  else
    activate_venv
    print_success "环境检查通过"
  fi
  echo

  print_step "阶段 2/5: 同步依赖"
  sync_deps
  echo

  print_step "阶段 3/5: 代码修复"
  fix_code
  echo

  print_step "阶段 4/5: 代码检查"
  run_all_checks
  echo

  print_step "阶段 5/5: 运行测试"
  run_tests_with_coverage
  echo

  print_title "流水线完成"
  print_success "所有阶段执行成功！"
  echo
  echo "下一步:"
  echo "  - 查看覆盖率报告: open htmlcov/index.html"
  echo "  - 构建项目: ./scripts/dev.sh build"
  echo "  - 发布项目: ./scripts/dev.sh publish-test"
}

# ==================== LLM (llama.cpp) 测试 ====================
find_llama_cmd() {
  local cmd=$1
  # 优先级：环境变量 > 项目 bin > 系统 PATH
  if [ -n "$LLAMA_SERVER" ] && [ -f "$LLAMA_SERVER" ]; then
    echo "$LLAMA_SERVER"
  elif [ -f "/usr/local/bin/$cmd" ]; then
    echo "/usr/local/bin/$cmd"
  elif command -v "$cmd" &>/dev/null; then
    echo "$cmd"
  else
    echo ""
  fi
}

run_llm_status() {
  print_title "LLM 服务状态"

  local llama_server
  llama_server=$(find_llama_cmd "llama-server")

  if [ -z "$llama_server" ]; then
    print_error "llama-server 未安装"
    print_info "请确保 llama.cpp 已编译并添加到 PATH"
    print_info "或设置 LLAMA_SERVER 环境变量指向可执行文件"
    return 1
  fi

  print_step "检查服务状态..."
  if pgrep -f "llama-server" >/dev/null 2>&1; then
    print_success "llama-server 运行中"
    local pid port
    pid=$(pgrep -f "llama-server" | head -1)
    port=$(netstat -tlnp 2>/dev/null | grep "$pid" | grep -oP ':\K\d+' | head -1 || echo "8080")
    echo "  PID:  $pid"
    echo "  端口: ${port:-8080}"
    echo "  URL:  http://localhost:${port:-8080}/v1/models"
  else
    print_warn "llama-server 未运行"
    print_info "使用 './scripts/dev.sh llm-start' 启动服务"
  fi
}

run_llm_start() {
  print_title "启动 LLM 服务"

  local llama_server
  llama_server=$(find_llama_cmd "llama-server")

  if [ -z "$llama_server" ]; then
    print_error "llama-server 未安装"
    return 1
  fi

  # 检查是否已运行
  if pgrep -f "llama-server" >/dev/null 2>&1; then
    print_warn "llama-server 已在运行"
    return 0
  fi

  local model="${LLAMA_MODEL:-/opt/models/tinyllama.gguf}"
  local host="${LLAMA_HOST:-0.0.0.0}"
  local port="${LLAMA_PORT:-8080}"
  local gpu_layers="${LLAMA_N_GPU_LAYERS:-99}"
  local ctx_size="${LLAMA_CONTEXT_SIZE:-2048}"

  print_step "启动 llama-server..."
  echo "  模型: $model"
  echo "  地址: $host:$port"
  echo "  GPU 层数: $gpu_layers"
  echo "  上下文: $ctx_size"

  if [ ! -f "$model" ]; then
    print_warn "模型文件不存在: $model"
    print_info "请下载模型或设置 LLAMA_MODEL 环境变量"
  fi

  # 后台启动
  "$llama_server" \
    -m "$model" \
    --host "$host" \
    --port "$port" \
    -ngl "$gpu_layers" \
    -c "$ctx_size" \
    &>"llama-server.log" &

  local pid=$!
  sleep 2

  if kill -0 "$pid" 2>/dev/null; then
    print_success "llama-server 已启动 (PID: $pid)"
    print_info "日志: llama-server.log"
    print_info "API: http://$host:$port"
  else
    print_error "启动失败，请检查 llama-server.log"
    return 1
  fi
}

run_llm_stop() {
  print_title "停止 LLM 服务"

  print_step "停止 llama-server..."
  if pkill -f "llama-server" 2>/dev/null; then
    sleep 1
    if pgrep -f "llama-server" >/dev/null 2>&1; then
      print_warn "服务可能仍在运行，尝试强制停止..."
      pkill -9 -f "llama-server" 2>/dev/null || true
    fi
    print_success "llama-server 已停止"
  else
    print_warn "llama-server 未运行"
  fi
}

run_llm_test() {
  print_title "测试 LLM API"

  local host="${LLAMA_HOST:-localhost}"
  local port="${LLAMA_PORT:-8080}"
  local base_url="http://$host:$port"

  # 检查服务是否运行
  print_step "检查服务状态..."
  if ! pgrep -f "llama-server" >/dev/null 2>&1; then
    print_warn "llama-server 未运行"
    read -r -p "是否启动服务？(y/N): " -n 1
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
      run_llm_start
    else
      return 1
    fi
  fi

  # 检查服务可用性
  print_step "测试 API 端点..."
  if curl -s --max-time 5 "$base_url/v1/models" >/dev/null 2>&1; then
    print_success "API 服务正常"
  else
    print_error "API 服务不可用，请检查日志"
    return 1
  fi

  # 获取模型信息
  echo -e "\n${BLUE}模型信息:${NC}"
  curl -s "$base_url/v1/models" | python -m json.tool 2>/dev/null ||
    curl -s "$base_url/v1/models"

  # 测试推理
  echo -e "\n${BLUE}测试推理:${NC}"
  local prompt="Hello, how are you?"
  echo -e "${CYAN}Prompt:${NC} $prompt"

  local response
  response=$(curl -s --max-time 60 \
    -X POST "$base_url/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"local\",\"messages\":[{\"role\":\"user\",\"content\":\"$prompt\"}],\"max_tokens\":100}" \
    2>&1)

  if echo "$response" | grep -q "content"; then
    echo -e "${GREEN}✅ 测试成功${NC}"
    echo -e "\n${CYAN}Response:${NC}"
    echo "$response" | python -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('choices', [{}])[0].get('message', {}).get('content', 'No content'))
" 2>/dev/null || echo "$response"
  else
    print_error "推理失败"
    echo "$response"
  fi
}

# ==================== 菜单 ====================
show_menu() {
  clear
  echo -e "${MAGENTA}"
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║                                                              ║"
  echo "║     Beancount Daoru - 完整开发流水线工具                     ║"
  echo "║                                                              ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo -e "${NC}"

  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${GREEN}环境管理${NC}"
  echo -e "  ${GREEN}1${NC}) 完整环境设置    ${GREEN}2${NC}) 重建虚拟环境    ${GREEN}3${NC}) 查看环境状态"
  echo
  echo -e "${GREEN}依赖管理${NC}"
  echo -e "  ${GREEN}4${NC}) 同步依赖        ${GREEN}5${NC}) 更新所有依赖    ${GREEN}6${NC}) 添加依赖"
  echo -e "  ${GREEN}7${NC}) 移除依赖"
  echo
  echo -e "${GREEN}代码质量${NC}"
  echo -e "  ${GREEN}8${NC}) 运行所有检查    ${GREEN}9${NC}) 自动修复问题    ${GREEN}10${NC}) 仅 Ruff 检查"
  echo -e "  ${GREEN}11${NC}) 仅格式化代码    ${GREEN}12${NC}) 仅类型检查"
  echo
  echo -e "${GREEN}测试${NC}"
  echo -e "  ${GREEN}13${NC}) 运行测试        ${GREEN}14${NC}) 测试+覆盖率     ${GREEN}15${NC}) 运行指定测试"
  echo
  echo -e "${GREEN}构建与发布${NC}"
  echo -e "  ${GREEN}16${NC}) 构建项目        ${GREEN}17${NC}) 发布到 TestPyPI ${GREEN}18${NC}) 发布到 PyPI"
  echo
  echo -e "${GREEN}清理${NC}"
  echo -e "  ${GREEN}19${NC}) 清理缓存        ${GREEN}20${NC}) 完全清理"
  echo
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${YELLOW}开发流水线${NC}"
  echo -e "  ${YELLOW}21${NC}) 完整开发流水线  ${YELLOW}22${NC}) CI 检查流水线"
  echo
  echo -e "${MAGENTA}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${MAGENTA}LLM (llama.cpp)${NC}"
  echo -e "  ${MAGENTA}23${NC}) LLM 服务状态    ${MAGENTA}24${NC}) 启动 LLM 服务"
  echo -e "  ${MAGENTA}25${NC}) 停止 LLM 服务   ${MAGENTA}26${NC}) 测试 LLM API"
  echo
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "  ${YELLOW}0${NC}) 退出            ${YELLOW}h${NC}) 显示快捷命令"
  echo
  echo -n "请选择 [0-26]: "
}

# ==================== 命令行参数处理 ====================
case "$1" in
  # 环境管理
  setup | install) setup_full ;;
  reset | recreate) recreate_venv ;;
  status | st) show_status ;;

  # 依赖管理
  sync | s) sync_deps ;;
  upgrade | up) sync_deps "upgrade" ;;
  add)
    shift
    add_dep "$@"
    ;;
  remove | rm)
    shift
    remove_dep "$@"
    ;;

  # 代码质量
  check | c) run_all_checks ;;
  fix | fmt) fix_code ;;
  lint | l) run_ruff_check ;;
  format) run_ruff_format ;;
  type | ty) run_basedpyright ;;
  shellcheck | sc) run_shellcheck ;;
  shfmt | sf) run_shfmt ;;

  # 测试
  test | t)
    shift
    run_tests "$@"
    ;;
  test-cov | coverage | cov) run_tests_with_coverage ;;
  test-file | tf)
    shift
    run_specific_test "$@"
    ;;

  # 构建与发布
  build | b) build_project ;;
  publish-test | publish-testpypi) publish_to_testpypi ;;
  publish | pypi) publish_to_pypi ;;

  # 清理
  clean | cache) clean_cache ;;
  clean-all | distclean) clean_all ;;

  # 流水线
  pipeline | full) run_full_pipeline ;;
  ci) run_ci_pipeline ;;

  # Pre-commit
  precommit-install) run_precommit_install ;;
  precommit | precommit-run) run_precommit ;;

  # LLM (llama.cpp)
  llm-status) run_llm_status ;;
  llm-start) run_llm_start ;;
  llm-stop) run_llm_stop ;;
  llm-test) run_llm_test ;;
  llm) run_llm_status ;;

  # 帮助
  alias | aliases) show_aliases ;;
  help | -h | --help | h) show_aliases ;;

  # 交互式菜单
  "")
    while true; do
      show_menu
      read -r choice
      echo
      case $choice in
        0)
          echo -e "${GREEN}再见！${NC}"
          exit 0
          ;;
        1) setup_full ;;
        2) recreate_venv ;;
        3) show_status ;;
        4) sync_deps ;;
        5) sync_deps "upgrade" ;;
        6)
          read -r -p "包名: " pkg
          add_dep "$pkg"
          ;;
        7)
          read -r -p "包名: " pkg
          remove_dep "$pkg"
          ;;
        8) run_all_checks ;;
        9) fix_code ;;
        10) run_ruff_check ;;
        11) run_ruff_format ;;
        12) run_basedpyright ;;
        13) run_tests ;;
        14) run_tests_with_coverage ;;
        15)
          read -r -p "测试路径: " path
          run_specific_test "$path"
          ;;
        16) build_project ;;
        17) publish_to_testpypi ;;
        18) publish_to_pypi ;;
        19) clean_cache ;;
        20) clean_all ;;
        21) run_full_pipeline ;;
        22) run_ci_pipeline ;;
        23) run_llm_status ;;
        24) run_llm_start ;;
        25) run_llm_stop ;;
        26) run_llm_test ;;
        h | H) show_aliases ;;
        *) print_error "无效选择" ;;
      esac
      echo
      read -r -p "按 Enter 键继续..."
    done
    ;;
  *)
    print_error "未知命令: $1"
    show_aliases
    exit 1
    ;;
esac
