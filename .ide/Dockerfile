FROM cnbcool/default-dev-env:latest

# 设置镜像源加速
ENV PIP_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ENV NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/
ENV GOPROXY=https://goproxy.cn,direct

# 安装 C 编译工具链和 bison（解决 beancount==3.2.0 原生编译问题）
RUN apt-get update && apt-get install -y \
    build-essential \
    bison \
    flex \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Go 1.22（用于安装 shfmt 等 Go 工具）
RUN curl -fsSL https://go.dev/dl/go1.22.5.linux-amd64.tar.gz | tar -C /usr/local -xzf - \
    && echo "export PATH=\$PATH:/usr/local/go/bin" >> /root/.bashrc
ENV PATH=$PATH:/usr/local/go/bin

# 安装 Node.js 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# 安装 markdownlint-cli2
RUN npm install -g markdownlint-cli2

# 安装 basedpyright
RUN npm install -g basedpyright

# 安装 shellcheck（Shell 脚本静态检查）
RUN apt-get update && apt-get install -y shellcheck \
    && rm -rf /var/lib/apt/lists/*

# 安装 shfmt（Shell 脚本格式化）
RUN go install mvdan.cc/sh/v3/cmd/shfmt@latest \
    && ln -sf $(go env GOPATH)/bin/shfmt /usr/local/bin/shfmt

# 安装并固定 Python 3.12（覆盖默认的 3.14）
RUN uv python install 3.12 && \
    uv python pin 3.12 && \
    export PATH="/root/.local/bin:$PATH" && \
    ln -sf $(which python3.12) /usr/local/bin/python

# 安装 ruff（通过 uv 作为全局工具）
RUN uv tool install ruff

# 安装 pre-commit（通过 uv 作为全局工具）
RUN uv tool install pre-commit --with pre-commit-uv

# 验证工具版本
RUN echo "=== Tool Versions ===" && \
    echo "Go: $(go version)" && \
    echo "Node: $(node --version)" && \
    echo "npm: $(npm --version)" && \
    echo "markdownlint-cli2: $(markdownlint-cli2 --version)" && \
    echo "basedpyright: $(basedpyright --version)" && \
    echo "shellcheck: $(shellcheck --version | head -n1)" && \
    echo "shfmt: $(shfmt --version)" && \
    echo "uv: $(uv --version)" && \
    echo "Python: $(python --version)" && \
    echo "ruff: $(ruff --version)" && \
    echo "pre-commit: $(pre-commit --version | head -n1)" && \
    echo "gcc: $(gcc --version | head -n1)" && \
    echo "bison: $(bison --version | head -n1)" && \
    echo "===================="

WORKDIR /workspace
