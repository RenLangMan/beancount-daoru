#!/bin/bash
# download-embedding-model.sh - 下载 Embedding 模型

set -e

MODELS_DIR="${MODELS_DIR:-/opt/models}"
MODEL_NAME="embeddinggemma-300m-Q4_0.gguf"
MODEL_URL="https://huggingface.co/unsloth/embeddinggemma-300m-GGUF/resolve/main/embeddinggemma-300m-Q4_0.gguf"

mkdir -p "$MODELS_DIR"

TARGET_PATH="$MODELS_DIR/$MODEL_NAME"

# 检查是否已存在
if [ -f "$TARGET_PATH" ]; then
	echo "✅ 模型已存在: $TARGET_PATH"
	ls -lh "$TARGET_PATH"
	exit 0
fi

echo "📦 下载 Embedding 模型..."
echo "   URL: $MODEL_URL"
echo "   目标: $TARGET_PATH"

wget --progress=bar:force \
	-O "$TARGET_PATH" \
	"$MODEL_URL"

echo ""
echo "✅ 下载完成!"
ls -lh "$TARGET_PATH"
