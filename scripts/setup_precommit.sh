#!/bin/bash
# 设置 pre-commit 环境（支持 Windows/Linux/macOS）

set -e

# 检测操作系统
detect_os() {
    case "$OSTYPE" in
        msys*|cygwin*|win32*) echo "windows";;
        linux*) echo "linux";;
        darwin*) echo "macos";;
        *) echo "unknown";;
    esac
}

OS=$(detect_os)
echo "🔍 检测到操作系统: $OS"

# 激活项目虚拟环境
echo "🔧 激活项目虚拟环境..."
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
    echo "✅ 已激活虚拟环境 (Windows)"
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo "✅ 已激活虚拟环境 (Linux/Mac)"
else
    echo "⚠️ 虚拟环境不存在，正在创建..."
    uv venv
    if [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    else
        source .venv/bin/activate
    fi
    echo "✅ 虚拟环境创建并激活完成"
fi

# 安装 pre-commit 到虚拟环境
echo "🔧 安装 pre-commit 到虚拟环境..."
uv pip install pre-commit

# 验证 pre-commit 是否可用
echo "📦 验证 pre-commit 安装..."
if command -v pre-commit &> /dev/null; then
    echo "✅ pre-commit 已安装: $(which pre-commit)"
    pre-commit --version
else
    echo "❌ pre-commit 安装失败"
    exit 1
fi

# 安装 pre-commit hooks
echo "📦 安装 pre-commit hooks..."
pre-commit install
pre-commit install --hook-type pre-push

# 安装 shellcheck
echo "🔧 安装 shellcheck..."
if ! command -v shellcheck &> /dev/null; then
    case "$OS" in
        windows)
            echo "⚠️ 请手动安装 shellcheck:"
            echo "   1. 下载: https://github.com/koalaman/shellcheck/releases"
            echo "   2. 解压并将 shellcheck.exe 添加到 PATH"
            echo "   3. 或使用 Scoop: scoop install shellcheck"
            echo "   4. 或使用 Chocolatey: choco install shellcheck"
            ;;
        linux)
            if command -v apt-get &> /dev/null; then
                sudo apt-get update && sudo apt-get install -y shellcheck
            elif command -v yum &> /dev/null; then
                sudo yum install -y shellcheck
            else
                echo "请手动安装 shellcheck"
            fi
            ;;
        macos)
            brew install shellcheck
            ;;
    esac
else
    echo "✅ shellcheck 已安装: $(which shellcheck)"
fi

# 安装 shfmt
echo "🔧 安装 shfmt..."
if ! command -v shfmt &> /dev/null; then
    case "$OS" in
        windows)
            echo "⚠️ 请手动安装 shfmt:"
            echo "   1. 下载: https://github.com/mvdan/sh/releases"
            echo "   2. 解压并将 shfmt.exe 添加到 PATH"
            echo "   3. 或使用 Scoop: scoop install shfmt"
            echo "   4. 或使用 Chocolatey: choco install shfmt"
            ;;
        linux)
            if command -v apt-get &> /dev/null; then
                sudo apt-get update && sudo apt-get install -y shfmt
            elif command -v yum &> /dev/null; then
                sudo yum install -y shfmt
            else
                # 从源码安装
                go install mvdan.cc/sh/v3/cmd/shfmt@latest
            fi
            ;;
        macos)
            brew install shfmt
            ;;
    esac
else
    echo "✅ shfmt 已安装: $(which shfmt)"
fi

# 安装 markdownlint-cli2
echo "🔧 安装 markdownlint-cli2..."
if ! command -v markdownlint-cli2 &> /dev/null; then
    if command -v npm &> /dev/null; then
        npm install -g markdownlint-cli2
        echo "✅ markdownlint-cli2 安装完成"
    else
        echo "⚠️ npm 未安装，请先安装 Node.js"
        echo "   下载地址: https://nodejs.org/"
    fi
else
    echo "✅ markdownlint-cli2 已安装"
fi

echo ""
echo "✅ pre-commit 配置完成"
echo ""
echo "📝 当前虚拟环境: $VIRTUAL_ENV"
echo ""
echo "📝 验证安装:"
echo "  - pre-commit --version"
echo "  - shellcheck --version"
echo "  - shfmt --version"
echo "  - markdownlint-cli2 --version"
echo ""
echo "🎯 运行检查:"
echo "  - pre-commit run --all-files  # 运行所有检查"
echo "  - git commit                   # 自动运行检查"
echo "  - pre-commit run --hook-stage push  # 运行 push 阶段检查"
echo ""
echo "💡 提示: pre-commit 已安装到项目虚拟环境"
echo "   每次开发前请确保虚拟环境已激活: source .venv/Scripts/activate"
