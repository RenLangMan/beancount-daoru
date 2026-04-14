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

# ==================== 创建模型目录（挂载点）====================
RUN mkdir -p /opt/models

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
    echo "💡 提示: 请确保卷已挂载且模型文件存在"
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

RUN chmod +x /usr/local/bin/start-llama \
    /usr/local/bin/stop-llama \
    /usr/local/bin/status-llama \
    /usr/local/bin/test-llama

# ==================== VSCode 配置 ====================
RUN mkdir -p /root/.vscode-server/data/Machine && \
    cat > /root/.vscode-server/data/Machine/settings.json << 'EOF'
{
    "files.watcherExclude": {
        "**/opt/models/**": true,
        "**/models/**": true,
        "**/llama.cpp/**": true,
        "**/.git/objects/**": true,
        "**/__pycache__/**": true,
        "**/.pytest_cache/**": true
    },
    "search.exclude": {
        "**/opt/models": true,
        "**/llama.cpp": true
    },
    "git.autoRepositoryDetection": true,
    "git.enabled": true
}
EOF

# 设置 bash 启动时自动进入工作目录
RUN echo 'cd /workspace 2>/dev/null || true' >> /root/.bashrc

# 验证工具版本
RUN echo "=== Tool Versions ===" && \
    echo "Go: $(go version)" && \
    echo "Node: $(node --version)" && \
    echo "uv: $(uv --version)" && \
    echo "Python: $(python --version)" && \
    echo "llama-server: $(llama-server --version 2>&1 | head -n1)" && \
    echo "===================="
