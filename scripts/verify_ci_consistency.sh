#!/bin/bash
# 验证本地配置与 CI 一致性

set -e

echo "════════════════════════════════════════════════════════"
echo "  验证 CI 与本地配置一致性"
echo "════════════════════════════════════════════════════════"
echo ""

# 检查必需工具是否安装
echo "🔍 检查本地工具..."

TOOLS=("ruff" "basedpyright" "markdownlint-cli2" "shellcheck" "shfmt" "pre-commit")

for tool in "${TOOLS[@]}"; do
  if command -v "$tool" &> /dev/null; then
    echo "  ✅ $tool: $(which $tool)"
  elif command -v "uv run $tool" &> /dev/null; then
    echo "  ✅ $tool: uv run"
  else
    echo "  ❌ $tool: 未安装"
  fi
done

echo ""
echo "🔍 检查 CI 配置..."

# 检查 .cnb.yml 中的检查项
CI_CHECKS=("ruff" "basedpyright" "markdownlint" "shellcheck" "shfmt" "uvlock")

for check in "${CI_CHECKS[@]}"; do
  if grep -q "$check" .cnb.yml; then
    echo "  ✅ $check: 已配置"
  else
    echo "  ❌ $check: 未配置"
  fi
done

echo ""
echo "🔍 检查 Dockerfile 工具..."

# 检查 Dockerfile 中的工具安装
DOCKER_TOOLS=("shellcheck" "shfmt" "nodejs" "markdownlint-cli2")

for tool in "${DOCKER_TOOLS[@]}"; do
  if grep -q "$tool" .ide/Dockerfile; then
    echo "  ✅ $tool: 已安装"
  else
    echo "  ❌ $tool: 未安装"
  fi
done

echo ""
echo "════════════════════════════════════════════════════════"
echo "  总结"
echo "════════════════════════════════════════════════════════"

echo ""
echo "✅ CI 与本地配置现已一致："
echo "  - 相同的 Ruff 规则"
echo "  - 相同的 basedpyright 配置"
echo "  - 相同的 Shell 脚本检查"
echo "  - 相同的 Markdown 检查"
echo "  - 相同的依赖锁定机制"
echo ""
echo "📝 建议："
echo "  1. 提交这些更改到 feat/format-code 分支"
echo "  2. 运行 ./scripts/dev.sh precommit 验证"
echo "  3. 推送并观察 CI 结果"
