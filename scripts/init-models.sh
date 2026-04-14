#!/bin/bash
# init-models.sh - 初始化模型卷

MODELS_DIR="/opt/models"
mkdir -p "$MODELS_DIR"

# 下载模型
echo "📦 下载 Embedding 模型..."
curl -L --retry 3 -o "$MODELS_DIR/embeddinggemma-300m-Q4_0.gguf" \
  "https://huggingface.co/unsloth/embeddinggemma-300m-GGUF/resolve/main/embeddinggemma-300m-Q4_0.gguf"

echo "📦 下载 Qwen3-4B 模型..."
curl -L --retry 3 -o "$MODELS_DIR/qwen3-4b-instruct.gguf" \
  "https://huggingface.co/MaziyarPanahi/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507.Q4_K_M.gguf"

echo "✅ 模型下载完成"
ls -lh "$MODELS_DIR/"
