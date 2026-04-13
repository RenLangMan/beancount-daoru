#!/bin/bash

cd /workspace

# 使用 CNB 标准环境变量
IMAGE_REGISTRY="${CNB_DOCKER_REGISTRY:-docker.cnb.cool}"
IMAGE_NAMESPACE="${CNB_REPO_SLUG_LOWERCASE}"
IMAGE_NAME="beancount-daoru"

# 构建完整的镜像地址
FULL_IMAGE="${IMAGE_REGISTRY}/${IMAGE_NAMESPACE}/${IMAGE_NAME}"

# 使用 CNB_COMMIT_SHORT 作为标签，如果没有则使用 latest
IMAGE_TAG="${CNB_COMMIT_SHORT:-latest}"

# 设置日志目录
LOG_DIR="build-logs"
mkdir -p "$LOG_DIR"

# 生成日志文件名（使用 CNB_BUILD_ID 确保唯一性）
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/build-${CNB_BUILD_ID:-${IMAGE_TAG}}-${TIMESTAMP}.log"
ERROR_LOG="$LOG_DIR/build-errors-${CNB_BUILD_ID:-${IMAGE_TAG}}-${TIMESTAMP}.log"

echo "=================================="
echo "CNB 构建环境信息："
echo "构建 ID: ${CNB_BUILD_ID:-未设置}"
echo "事件类型: ${CNB_EVENT:-未设置}"
echo "分支/Tag: ${CNB_BRANCH:-未设置}"
echo "Commit SHA: ${CNB_COMMIT_SHORT:-未设置}"
echo ""
echo "镜像信息："
echo "镜像仓库: ${IMAGE_REGISTRY}"
echo "镜像命名空间: ${IMAGE_NAMESPACE}"
echo "镜像名称: ${IMAGE_NAME}"
echo "完整镜像: ${FULL_IMAGE}"
echo "镜像标签: ${IMAGE_TAG}"
echo ""
echo "开始构建镜像"
echo "日志文件: $LOG_FILE"
echo "错误日志: $ERROR_LOG"
echo "=================================="

# 执行构建并记录日志
docker build --progress=plain \
  -f .ide/Dockerfile \
  -t ${FULL_IMAGE}:${IMAGE_TAG} \
  -t ${FULL_IMAGE}:latest \
  . 2>&1 | tee "$LOG_FILE"

# 检查构建是否成功
BUILD_STATUS=$?

# 提取错误和警告
grep -E "(ERROR|WARNING|FAILED|Step.*failed)" "$LOG_FILE" > "$ERROR_LOG" 2>/dev/null

# 显示结果
echo "=================================="
if [ $BUILD_STATUS -eq 0 ]; then
    echo "✅ 构建成功！"
    
    # 如果是 CI 环境，自动推送
    if [ "${CI}" = "true" ]; then
        echo "📤 推送镜像到 ${IMAGE_REGISTRY}..."
        docker push ${FULL_IMAGE}:${IMAGE_TAG}
        docker push ${FULL_IMAGE}:latest
        echo "✅ 推送完成"
    fi
else
    echo "❌ 构建失败！退出码: ${BUILD_STATUS}"
    echo "失败信息: ${CNB_BUILD_FAILED_MSG:-无详细信息}"
fi
echo "完整日志: $LOG_FILE"
echo "错误摘要: $ERROR_LOG"
echo "=================================="

# 显示错误数量
if [ -f "$ERROR_LOG" ]; then
    ERROR_COUNT=$(wc -l < "$ERROR_LOG")
    if [ "$ERROR_COUNT" -gt 0 ]; then
        echo "⚠️  发现 $ERROR_COUNT 条错误/警告"
        echo "--- 错误摘要 ---"
        cat "$ERROR_LOG"
        echo "--- 结束 ---"
    else
        echo "✅ 没有发现错误"
    fi
else
    echo "✅ 没有发现错误"
fi

exit $BUILD_STATUS