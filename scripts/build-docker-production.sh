#!/bin/bash
set -euo pipefail

cd /workspace

# 验证必需的环境变量
if [ -z "${CNB_REPO_SLUG_LOWERCASE:-}" ]; then
    echo "❌ 错误: CNB_REPO_SLUG_LOWERCASE 环境变量未设置"
    exit 1
fi

# 镜像配置
IMAGE_REGISTRY="${CNB_DOCKER_REGISTRY:-docker.cnb.cool}"
IMAGE_NAMESPACE="${CNB_REPO_SLUG_LOWERCASE}"
IMAGE_NAME="beancount-daoru"
FULL_IMAGE="${IMAGE_REGISTRY}/${IMAGE_NAMESPACE}/${IMAGE_NAME}"

# 标签优先级: CNB_TAG > CNB_BRANCH > CNB_COMMIT_SHORT > latest
if [ "${CNB_IS_TAG:-false}" = "true" ]; then
    IMAGE_TAG="${CNB_BRANCH#v}"  # 去掉 v 前缀
elif [ -n "${CNB_BRANCH:-}" ] && [ "${CNB_BRANCH}" = "${CNB_DEFAULT_BRANCH:-}" ]; then
    IMAGE_TAG="latest"
else
    IMAGE_TAG="${CNB_COMMIT_SHORT:-latest}"
fi

# 日志配置
LOG_DIR="build-logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/build-${CNB_BUILD_ID:-$(date +%Y%m%d-%H%M%S)}.log"

# 打印构建信息
cat << EOF
==========================================
CNB 构建信息：
  构建 ID: ${CNB_BUILD_ID:-N/A}
  事件类型: ${CNB_EVENT:-N/A}
  分支/Tag: ${CNB_BRANCH:-N/A}
  Commit: ${CNB_COMMIT_SHORT:-N/A}
  触发者: ${CNB_BUILD_USER:-N/A} (${CNB_BUILD_USER_NICKNAME:-N/A})

镜像信息：
  仓库: ${IMAGE_REGISTRY}
  命名空间: ${IMAGE_NAMESPACE}
  名称: ${IMAGE_NAME}
  完整地址: ${FULL_IMAGE}
  标签: ${IMAGE_TAG}

日志文件: ${LOG_FILE}
==========================================
EOF

# 构建镜像
echo "🏗️  开始构建镜像..."
if docker build --progress=plain \
    -f .ide/Dockerfile \
    -t "${FULL_IMAGE}:${IMAGE_TAG}" \
    -t "${FULL_IMAGE}:latest" \
    . 2>&1 | tee "${LOG_FILE}"; then
    echo "✅ 镜像构建成功"
else
    echo "❌ 镜像构建失败"
    exit 1
fi

# 推送镜像（仅在 CI 环境或明确需要推送时）
if [ "${CI:-false}" = "true" ] || [ "${PUSH_IMAGE:-false}" = "true" ]; then
    echo "📤 推送镜像到 ${IMAGE_REGISTRY}..."
    
    # 推送特定标签
    echo "推送 ${FULL_IMAGE}:${IMAGE_TAG}"
    docker push "${FULL_IMAGE}:${IMAGE_TAG}"
    
    # 如果是默认分支，推送 latest 标签
    if [ "${CNB_BRANCH:-}" = "${CNB_DEFAULT_BRANCH:-}" ] || [ "${IMAGE_TAG}" = "latest" ]; then
        echo "推送 ${FULL_IMAGE}:latest"
        docker push "${FULL_IMAGE}:latest"
    fi
    
    echo "✅ 镜像推送完成"
fi

# 输出构建结果
cat << EOF
==========================================
✅ 构建完成！

镜像地址:
  ${FULL_IMAGE}:${IMAGE_TAG}
  ${FULL_IMAGE}:latest

日志文件: ${LOG_FILE}

构建信息:
  状态: 成功
  耗时: ${SECONDS}s
  构建 ID: ${CNB_BUILD_ID:-N/A}
==========================================
