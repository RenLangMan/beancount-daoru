FROM cnbcool/default-dev-env:latest

# 设置镜像源加速（可选）
ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ENV NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/

# 安装 Node.js 20（基础镜像缺少 node/npm）
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 全局安装 markdownlint-cli2（CI 和开发环境都需要）
RUN npm install -g markdownlint-cli2

# 关键修改：安装并固定 Python 3.12（覆盖默认的 3.14）
RUN uv python install 3.12 && \
    uv python pin 3.12 && \
    # 将 uv 安装的 Python 3.12 路径加入 PATH 并创建软链接
    export PATH="/root/.local/bin:$PATH" && \
    ln -sf $(which python3.12) /usr/local/bin/python

# 验证工具版本（同时验证 python3 和 python）
RUN node --version && npm --version && markdownlint-cli2 --version && uv --version && python3 --version && python --version

WORKDIR /workspace