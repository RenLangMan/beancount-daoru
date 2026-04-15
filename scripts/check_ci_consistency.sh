#!/bin/bash
# 检查本地配置与 CI 是否一致

echo "🔍 检查 CI 配置一致性..."

# 检查 CI 中是否包含所有必要的检查
REQUIRED_CHECKS=("ruff" "basedpyright" "markdownlint" "shellcheck" "shfmt")

for check in "${REQUIRED_CHECKS[@]}"; do
  if grep -q "$check" .cnb.yml; then
    echo "✅ $check 已在 CI 中配置"
  else
    echo "❌ $check 未在 CI 中配置"
  fi
done

# 检查本地 pre-commit 配置
echo ""
echo "📋 Pre-commit 配置:"
pre-commit run --all-files --dry-run

echo ""
echo "📊 总结:"
echo "如果 CI 缺少某些检查，请更新 .cnb.yml"
