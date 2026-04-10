FROM cnbcool/default-dev-env:latest

# 设置镜像源加速
ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ENV NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/

# 安装 C 编译工具链和 bison（解决 beancount==3.2.0 原生编译问题）
RUN apt-get update && apt-get install -y \
    build-essential \
    bison \
    flex \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装 markdownlint-cli2
RUN npm install -g markdownlint-cli2

# 安装并固定 Python 3.12（覆盖默认的 3.14）
RUN uv python install 3.12 && \
    uv python pin 3.12 && \
    export PATH="/root/.local/bin:$PATH" && \
    ln -sf $(which python3.12) /usr/local/bin/python

# 验证工具版本
RUN echo "=== Tool Versions ===" && \
    echo "Node: $(node --version)" && \
    echo "npm: $(npm --version)" && \
    echo "markdownlint: $(markdownlint-cli2 --version)" && \
    echo "uv: $(uv --version)" && \
    echo "Python: $(python --version)" && \
    echo "gcc: $(gcc --version | head -n1)" && \
    echo "bison: $(bison --version | head -n1)" && \
    echo "===================="

WORKDIR /workspace
