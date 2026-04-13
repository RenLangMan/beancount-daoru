FROM cnbcool/default-dev-env:latest

# 设置镜像源加速
ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ENV NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/
ENV GOPROXY=https://goproxy.cn,direct

# ==================== 统一安装基础工具 ====================
RUN apt-get update && apt-get install -y \
    build-essential \
    bison \
    flex \
    libffi-dev \
    libssl-dev \
    cmake \
    shellcheck \
    && rm -rf /var/lib/apt/lists/*

# ==================== 统一安装 Go 1.25 ====================
RUN curl -fsSL https://go.dev/dl/go1.25.5.linux-amd64.tar.gz | tar -C /usr/local -xzf - && \
    echo "export PATH=\$PATH:/usr/local/go/bin" >> /root/.bashrc
ENV PATH=$PATH:/usr/local/go/bin
ENV GOPATH=/root/go
ENV PATH=$PATH:$GOPATH/bin

# ==================== 安装 Node.js 20 ====================
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# ==================== 安装 npm 工具 ====================
RUN npm install -g markdownlint-cli2 basedpyright

# ==================== 安装 shfmt ====================
RUN go install mvdan.cc/sh/v3/cmd/shfmt@latest && \
    shfmt --version

# ==================== 安装 Python 3.12 和相关工具 ====================
ENV PATH="/root/.local/bin:$PATH"
RUN uv python install 3.12 && \
    uv python pin 3.12 && \
    ln -sf "$(uv python find 3.12)" /usr/local/bin/python && \
    uv tool install ruff && \
    uv tool install pre-commit --with pre-commit-uv && \
    python --version

# ==================== llama.cpp 集成 ====================
RUN git clone --depth 1 https://github.com/ggerganov/llama.cpp /opt/llama.cpp && \
    cd /opt/llama.cpp && \
    mkdir build && cd build && \
    cmake .. -DLLAMA_CURL=ON && \
    cmake --build . --config Release -j $(nproc) && \
    ln -sf /opt/llama.cpp/build/bin/llama-server /usr/local/bin/llama-server && \
    ln -sf /opt/llama.cpp/build/bin/llama-cli /usr/local/bin/llama-cli

# ==================== 下载模型（使用验证过的源）====================
RUN mkdir -p /opt/models

# 1. 下载 Embedding 模型 (300MB) - 使用 unsloth 源
RUN echo "📦 下载 Embedding 模型 (300MB)..." && \
    curl -L --retry 3 --retry-delay 2 -o /opt/models/embeddinggemma-300m-Q4_0.gguf \
    "https://huggingface.co/unsloth/embeddinggemma-300m-GGUF/resolve/main/embeddinggemma-300m-Q4_0.gguf" && \
    if [ $(stat -c%s "/opt/models/embeddinggemma-300m-Q4_0.gguf") -lt 1000000 ]; then \
        echo "❌ 下载失败，文件过小" && exit 1; \
    fi && \
    echo "✅ Embedding 模型下载完成: $(ls -lh /opt/models/embeddinggemma-300m-Q4_0.gguf)"

# 2. 下载 Chat Completion 模型 (2.5GB) - 使用 MaziyarPanahi 源（已验证可用）
RUN echo "📦 下载 Qwen3-4B 模型 (约 2.5GB，请耐心等待)..." && \
    curl -L --retry 3 --retry-delay 2 -o /opt/models/qwen3-4b-instruct.gguf \
    "https://huggingface.co/MaziyarPanahi/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507.Q4_K_M.gguf" && \
    if [ $(stat -c%s "/opt/models/qwen3-4b-instruct.gguf") -lt 1000000000 ]; then \
        echo "❌ 下载失败，文件过小" && exit 1; \
    fi && \
    echo "✅ Qwen3-4B 模型下载完成: $(ls -lh /opt/models/qwen3-4b-instruct.gguf)"

# # 3. 下载 TinyLlama 备用模型 (600MB) - 使用 TheBloke 源
# RUN echo "📦 下载 TinyLlama 备用模型 (600MB)..." && \
#     curl -L --retry 3 --retry-delay 2 -o /opt/models/tinyllama.gguf \
#     "https://huggingface.co/TheBloke/TinyLlama-1.1B-GGUF/resolve/main/tinyllama-1.1b-q4_0.gguf" && \
#     if [ $(stat -c%s "/opt/models/tinyllama.gguf") -lt 100000000 ]; then \
#         echo "❌ 下载失败，文件过小" && exit 1; \
#     fi && \
#     echo "✅ TinyLlama 模型下载完成: $(ls -lh /opt/models/tinyllama.gguf)"

# 验证所有模型文件
RUN echo "=== 预装模型列表 ===" && \
    ls -lh /opt/models/*.gguf && \
    echo "总大小: $(du -sh /opt/models)" && \
    echo "==================="

# 设置环境变量（更新 Chat 模型路径）
ENV TEST_EMBEDDING_MODEL=/opt/models/embeddinggemma-300m-Q4_0.gguf
ENV TEST_CHAT_MODEL=/opt/models/qwen3-4b-instruct.gguf
ENV TEST_FALLBACK_MODEL=/opt/models/tinyllama.gguf
ENV EMBEDDING_PORT=1314
ENV CHAT_PORT=9527
ENV CTX_SIZE=8192

# ==================== 创建管理脚本 ====================
RUN cat > /usr/local/bin/start-llama << 'EOF'
#!/bin/bash
# llama-server 启动脚本
MODEL="${LLAMA_MODEL:-/opt/models/tinyllama.gguf}"
HOST="${LLAMA_HOST:-0.0.0.0}"
PORT="${LLAMA_PORT:-8080}"
N_GPU_LAYERS="${LLAMA_N_GPU_LAYERS:-0}"
CTX_SIZE="${LLAMA_CONTEXT_SIZE:-4096}"
THREADS="${LLAMA_THREADS:-}"

if [ ! -f "$MODEL" ]; then
    echo "❌ 错误: 模型文件不存在: $MODEL"
    exit 1
fi

echo "🚀 启动 llama-server"
echo "  模型: $MODEL"
echo "  地址: $HOST:$PORT"
echo "  GPU 层数: $N_GPU_LAYERS"
echo "  上下文大小: $CTX_SIZE"

CMD="llama-server -m $MODEL --host $HOST --port $PORT -ngl $N_GPU_LAYERS -c $CTX_SIZE"
[ -n "$THREADS" ] && CMD="$CMD -t $THREADS"

echo "执行: $CMD"
exec $CMD
EOF

RUN cat > /usr/local/bin/stop-llama << 'EOF'
#!/bin/bash
echo "🛑 停止 llama-server..."
pkill -f "llama-server" && echo "✅ 已停止" || echo "⚠️ 没有运行中的服务"
EOF

RUN cat > /usr/local/bin/status-llama << 'EOF'
#!/bin/bash
if pgrep -f "llama-server" > /dev/null; then
    PID=$(pgrep -f "llama-server")
    PORT=$(ss -tlnp 2>/dev/null | grep "$PID" | grep -oP ':\K\d+' | head -1)
    echo "✅ llama-server 运行中 (PID: $PID, 端口: ${PORT:-未知})"
    exit 0
else
    echo "❌ llama-server 未运行"
    exit 1
fi
EOF

RUN cat > /usr/local/bin/test-llama << 'EOF'
#!/bin/bash
PORT="${LLAMA_PORT:-8080}"
HOST="${LLAMA_HOST:-0.0.0.0}"

echo "🔍 测试 llama-server API (http://$HOST:$PORT)"
sleep 2

if curl -s "http://$HOST:$PORT/health" > /dev/null 2>&1; then
    echo "✅ 服务健康检查通过"
else
    echo "❌ 服务健康检查失败"
    exit 1
fi

echo '{"prompt":"Hello","n_predict":10}' | \
    curl -s -X POST "http://$HOST:$PORT/completion" \
    -H "Content-Type: application/json" \
    -d @- > /dev/null && echo "✅ 补全接口测试通过" || echo "⚠️ 补全接口测试失败"
EOF

# ==================== 双服务启动脚本（用于测试）====================
RUN cat > /usr/local/bin/start-llama-services << 'EOF'
#!/bin/bash
# 启动两个 LLM 服务（支持本地模型和在线下载）

echo "🚀 启动 LLM 服务..."

# 配置参数
EMBEDDING_PORT="${EMBEDDING_PORT:-1314}"
CHAT_PORT="${CHAT_PORT:-9527}"
CTX_SIZE="${CTX_SIZE:-8192}"

# ==================== Embedding 服务 ====================
# 优先使用本地模型，否则在线下载
if [ -f "/opt/models/embeddinggemma-300m-Q4_0.gguf" ]; then
    echo "📁 使用本地 Embedding 模型"
    EMBEDDING_CMD="llama-server -m /opt/models/embeddinggemma-300m-Q4_0.gguf --host 0.0.0.0 --port $EMBEDDING_PORT --embedding -c 1024 -ngl 0"
else
    echo "🌐 在线下载 Embedding 模型"
    EMBEDDING_CMD="llama-server -hf unsloth/embeddinggemma-300m-GGUF:Q4_0 --host 0.0.0.0 --port $EMBEDDING_PORT --embedding -c 1024 -ngl 0"
fi

# ==================== Chat 服务 ====================
# 优先使用本地模型，否则在线下载
if [ -f "/opt/models/qwen3-4b-instruct.gguf" ]; then
    echo "📁 使用本地 Chat 模型"
    CHAT_CMD="llama-server -m /opt/models/qwen3-4b-instruct.gguf --host 0.0.0.0 --port $CHAT_PORT -c $CTX_SIZE -ngl 0"
else
    echo "🌐 在线下载 Chat 模型 (首次启动较慢)"
    CHAT_CMD="llama-server -hf unsloth/Qwen3-4B-Instruct-2507-GGUF:IQ4_NL --host 0.0.0.0 --port $CHAT_PORT --ctx-size $CTX_SIZE -ngl 0"
fi

echo ""
echo "📊 服务配置："
echo "  Embedding: 端口 $EMBEDDING_PORT, 上下文 1024"
echo "  Chat: 端口 $CHAT_PORT, 上下文 $CTX_SIZE"
echo ""

# 启动服务
echo "启动 Embedding 服务..."
$EMBEDDING_CMD &
EMBEDDING_PID=$!

echo "启动 Chat 服务..."
$CHAT_CMD &
CHAT_PID=$!

echo ""
echo "✅ 服务已启动"
echo "  Embedding PID: $EMBEDDING_PID"
echo "  Chat PID: $CHAT_PID"
echo ""
echo "📝 测试命令："
echo "  curl http://localhost:$EMBEDDING_PORT/health"
echo "  curl http://localhost:$CHAT_PORT/health"
echo "  curl -X POST http://localhost:$CHAT_PORT/completion -H 'Content-Type: application/json' -d '{\"prompt\":\"Hello\",\"n_predict\":20}'"

# 等待进程
wait $EMBEDDING_PID $CHAT_PID
EOF

RUN chmod +x /usr/local/bin/start-llama \
    /usr/local/bin/stop-llama \
    /usr/local/bin/status-llama \
    /usr/local/bin/test-llama \
    /usr/local/bin/start-llama-services

# ==================== 验证工具版本 ====================
RUN echo "=== Tool Versions ===" && \
    echo "Go: $(go version)" && \
    echo "Node: $(node --version)" && \
    echo "npm: $(npm --version)" && \
    echo "markdownlint-cli2: $(markdownlint-cli2 --version 2>/dev/null | head -n1)" && \
    echo "basedpyright: $(basedpyright --version 2>/dev/null | head -n1)" && \
    echo "shellcheck: $(shellcheck --version 2>/dev/null | head -n1)" && \
    echo "shfmt: $(shfmt --version)" && \
    echo "uv: $(uv --version)" && \
    echo "Python: $(python --version)" && \
    echo "ruff: $(ruff --version)" && \
    echo "pre-commit: $(pre-commit --version 2>/dev/null | head -n1)" && \
    echo "gcc: $(gcc --version 2>/dev/null | head -n1)" && \
    echo "bison: $(bison --version 2>/dev/null | head -n1)" && \
    echo "cmake: $(cmake --version 2>/dev/null | head -n1)" && \
    echo "llama-server: $(llama-server --version 2>&1 | head -n1)" && \
    echo "===================="

# 显示模型文件信息
RUN echo "=== 预装模型文件 ===" && \
    ls -lh /opt/models/ && \
    echo "===================="

WORKDIR /workspace

# 默认命令（单服务模式）
# CMD ["start-llama"]

# 推荐使用双服务模式（取消注释下面这行）
# CMD ["start-llama-services"]