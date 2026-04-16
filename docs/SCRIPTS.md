# 开发者指南

本文档介绍如何使用 `scripts/dev.sh` 脚本进行项目开发和维护。该脚本是一站式开发流水线工具，集成了环境管理、依赖管理、代码检查、测试、构建发布等功能。

## 前置要求

在开始之前，请确保已安装以下软件：

- **Python 3.10+** - 项目运行环境
- **Git** - 版本控制系统
- **uv** - 推荐的包管理器（可使用 pip 安装）

安装 uv：

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip
pip install uv
```

## 快速上手

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd beancount-daoru

# 2. 设置环境
./scripts/dev.sh setup

# 3. 运行完整流水线
./scripts/dev.sh pipeline
```

______________________________________________________________________

## 环境管理

本节介绍如何管理 Python 虚拟环境和项目环境。

### setup - 完整环境设置

`./scripts/dev.sh setup`

这是最常用的环境初始化命令。它会执行以下操作：

1. 检查 uv 是否已安装
2. 创建或检查虚拟环境（`.venv`）
3. 同步所有依赖到虚拟环境
4. 显示当前环境状态

如果虚拟环境已存在，脚本会询问是否重建。这是一个**幂等操作**，可以安全重复执行。

别名：`install`

### reset - 重建虚拟环境

`./scripts/dev.sh reset`

删除现有的虚拟环境并重新创建。如果遇到依赖问题或环境损坏，可以使用此命令重建干净的环境。

使用前请注意：

- 会删除 `.venv` 目录
- 需要重新同步所有依赖
- 不会影响代码文件

别名：`recreate`

### status - 查看环境状态

`./scripts/dev.sh status`

显示当前开发环境的详细信息，包括：

- 项目目录路径
- 操作系统类型
- 虚拟环境状态和 Python 版本
- uv 版本和路径
- 已安装的 Python 包列表（显示前 20 个）
- LLM 模型文件状态

别名：`st`

______________________________________________________________________

## 依赖管理

本节介绍如何管理项目依赖。

### sync - 同步依赖

`./scripts/dev.sh sync`

根据 `pyproject.toml` 和 `uv.lock` 文件同步虚拟环境中的所有依赖。推荐在以下情况使用：

- 首次克隆项目后
- `git pull` 获取最新代码后
- 修改 `pyproject.toml` 后

该命令使用 `--link-mode=copy` 确保依赖在虚拟环境中的可移植性。

别名：`s`

### upgrade - 更新所有依赖

`./scripts/dev.sh upgrade`

将所有依赖更新到 `pyproject.toml` 中允许的最新版本。这对于获取安全补丁和新功能很有用。

使用建议：

- 更新前建议提交或备份当前更改
- 更新后运行测试确保兼容性
- 注意查看是否有破坏性变更

别名：`up`

### add - 添加依赖

`./scripts/dev.sh add <package>`

向项目添加新的依赖包。例如：

```bash
./scripts/dev.sh add requests
./scripts/dev.sh add "requests>=2.28"
./scripts/dev.sh add httpx --dev  # 添加开发依赖
```

该命令会自动：

- 更新 `pyproject.toml`
- 更新 `uv.lock`
- 同步到虚拟环境

### remove - 移除依赖

`./scripts/dev.sh remove <package>`

从项目中移除指定的依赖包。例如：

```bash
./scripts/dev.sh remove requests
```

该命令会自动：

- 从 `pyproject.toml` 中移除
- 更新 `uv.lock`
- 同步虚拟环境

别名：`rm`

______________________________________________________________________

## 代码质量检查

本节介绍代码质量检查工具。检查对齐 CI Checks 配置。

### check - 运行所有检查

`./scripts/dev.sh check`

一次性运行所有代码质量检查工具，是提交前最完整的检查命令。包含：

- Markdownlint - Markdown 格式检查
- Mdformat - Markdown 格式化检查
- Ruff Check - Python 代码检查
- Ruff Format - Python 代码格式化检查
- ShellCheck - Shell 脚本检查
- shfmt - Shell 脚本格式化检查
- uv.lock - 锁文件一致性检查
- Basedpyright - Python 类型检查

别名：`c`

### fix - 自动修复问题

`./scripts/dev.sh fix`

自动修复代码质量问题，按顺序执行：

1. **Markdown** - 使用 markdownlint-cli2 修复 Markdown 格式问题
2. **Markdown 格式化** - 使用 mdformat 格式化 Markdown 文件
3. **Python 格式** - 使用 ruff format 格式化代码
4. **Python 检查** - 使用 ruff check --fix 修复代码问题
5. **Shell 脚本** - 使用 shfmt 格式化 Shell 脚本

使用建议：在提交代码前运行此命令可以快速修复大部分格式问题。

别名：`fmt`

### lint - Ruff 代码检查

`./scripts/dev.sh lint`

使用 [Ruff](https://github.com/astral-sh/ruff) 检查 Python 代码问题。Ruff 是一个极速的 Python linter，兼容 PEP 8 和许多常见代码规范。

它会检查：

- 未使用的导入
- 未使用的变量
- 代码风格问题
- 常见错误模式

别名：`l`

### format - Ruff 格式化检查

`./scripts/dev.sh format`

检查 Python 代码是否符合项目的格式化规范（使用 Black 兼容格式）。此命令**不会**修改文件，只是检查差异。

要自动格式化代码，请使用 `fix` 命令。

### type - 类型检查

`./scripts/dev.sh type`

使用 [Basedpyright](https://github.com/DetachHead/basedpyright) 进行 Python 类型检查。这有助于发现类型相关的 bug 和提高代码质量。

执行前会先同步 `llm` extra 和 `dev` 依赖组。

别名：`ty`

### markdownlint - Markdown 检查

`./scripts/dev.sh markdownlint`

使用 markdownlint-cli2 检查项目中所有 Markdown 文件的格式问题。

别名：`md`

### mdformat - Markdown 格式化

`./scripts/dev.sh mdformat`

使用 [mdformat](https://github.com/executablebooks/mdformat) 格式化 Markdown 文件。这会调整代码块样式、表格格式、链接格式等，使文档风格一致。

格式化的文件包括：

- `docs/**/*.md`
- `scripts/**/*.md`
- `README.md`
- `CONTRIBUTING.md`
- `NOTICE.md`
- `QUICKSTART.md`

该命令是破坏性操作，会修改文件内容。建议在提交前运行。

别名：`mdf`

### shellcheck - Shell 脚本检查

`./scripts/dev.sh shellcheck`

使用 [ShellCheck](https://www.shellcheck.net/) 检查 Shell 脚本的潜在问题和错误。此工具可以发现许多常见的 Shell 脚本 bug。

别名：`sc`

### shfmt - Shell 格式化检查

`./scripts/dev.sh shfmt`

使用 [shfmt](https://github.com/mvdan/sh) 检查 Shell 脚本的格式化规范。使用 `-sr` 选项启用简化重定向样式。

别名：`sf`

### uvlock - 锁文件一致性检查

`./scripts/dev.sh uvlock`

检查 `pyproject.toml` 和 `uv.lock` 的一致性，并自动更新锁文件以确保同步。

别名：`lock`

______________________________________________________________________

## 测试

本节介绍测试相关的命令。测试分为**单元测试**和 **LLM 测试**两组。

### test - 运行单元测试

`./scripts/dev.sh test`

运行所有单元测试（不包括标记为 `llm` 的测试）。默认参数：

- `--verbose` - 详细输出
- `-m "not llm"` - 排除 LLM 测试

可以传递额外的 pytest 参数：

```bash
./scripts/dev.sh test -- -k "test_specific"
./scripts/dev.sh test -- --lf  # 只运行上次失败的测试
```

别名：`t`

### test-llm - 运行 LLM 测试

`./scripts/dev.sh test-llm`

运行需要 LLM 模型的测试（标记为 `llm` 的测试）。此命令会：

1. 检查模型文件是否存在
2. 同步 llm 依赖
3. 运行标记为 `-m "llm"` 的测试

**前提条件**：需要已下载 LLM 模型文件到 `/opt/models/` 目录。

别名：`tl`

### test-all - 运行全部测试

`./scripts/dev.sh test-all`

运行所有测试，包括单元测试和 LLM 测试。默认参数：

- `--verbose` - 详细输出

别名：`ta`

### test-cov - 测试覆盖率

`./scripts/dev.sh test-cov`

运行单元测试并生成覆盖率报告。生成三种格式的报告：

- **终端报告** - 直接在终端显示
- **HTML 报告** - `htmlcov/index.html`（可在浏览器打开）
- **XML 报告** - `coverage.xml`（用于 CI 集成）

注意：

- 需要安装 `pytest-cov`
- 只运行非 LLM 测试（`-m "not llm"`）
- 覆盖率基于 `src/` 目录计算

别名：`coverage`、`cov`

### test-file - 运行指定测试

`./scripts/dev.sh test-file <path>`

运行指定的测试文件或目录。例如：

```bash
./scripts/dev.sh test-file tests/test_example.py
./scripts/dev.sh test-file tests/unit/
```

别名：`tf`

______________________________________________________________________

## 构建与发布

本节介绍如何构建和发布项目。

### build - 构建项目

`./scripts/dev.sh build`

使用 uv 构建项目包。构建产物位于 `dist/` 目录，包括：

- 源码分发包（`.tar.gz`）
- wheel 包（`.whl`）

构建前请确保：

- 所有测试通过
- 版本号已更新（在 `pyproject.toml` 中）

别名：`b`

### publish-test - 发布到 TestPyPI

`./scripts/dev.sh publish-test`

将构建产物发布到 TestPyPI（测试环境）。TestPyPI 允许在正式发布前测试安装流程。

发布前需要：

1. 确保 `dist/` 目录有构建产物
2. 配置 TestPyPI 凭据

### publish - 发布到 PyPI

`./scripts/dev.sh publish`

将构建产物发布到正式的 PyPI。在执行前会：

1. 提示确认版本号
2. 要求用户输入 `y` 确认

**警告**：此操作不可逆，发布到正式 PyPI 后无法撤回。

别名：`pypi`

______________________________________________________________________

## 清理

本节介绍清理环境的方法。

### clean - 清理缓存

`./scripts/dev.sh clean`

清理所有临时文件和缓存，包括：

- uv 缓存
- Python `__pycache__` 目录
- Python `.pyc` 文件
- `.coverage` 测试覆盖率文件
- `.pytest_cache` 目录
- `htmlcov/` 目录
- `.ruff_cache` 目录
- `.mypy_cache` 目录

不会删除虚拟环境（`.venv`）或构建产物（`dist/`）。

别名：`cache`

### clean-all - 完全清理

`./scripts/dev.sh clean-all`

执行完全清理，包括：

1. 所有 `clean` 清理的内容
2. 删除虚拟环境（`.venv`）
3. 删除构建产物（`dist/`、`build/`、`*.egg-info/`）

**警告**：此命令需要确认，因为会删除虚拟环境。

别名：`distclean`

______________________________________________________________________

## 开发流水线

本节介绍一键式开发流水线命令。

### pipeline - 完整开发流水线

`./scripts/dev.sh pipeline`

执行完整的开发流水线，包括 5 个阶段：

1. **环境检查** - 检查虚拟环境，不存在则创建
2. **同步依赖** - 同步所有依赖
3. **代码修复** - 自动修复格式问题
4. **代码检查** - 运行所有质量检查
5. **运行测试** - 执行单元测试和 LLM 测试

这是日常开发中使用最频繁的命令，在提交代码前运行可以确保代码质量。

别名：`full`

### ci - CI 检查流水线

`./scripts/dev.sh ci`

模拟 CI 环境的检查流水线，执行与 `.cnb.yml` 完全对齐的检查流程：

**Checks 阶段**：

- Markdownlint
- Ruff Check
- Ruff Format
- ShellCheck
- shfmt
- uv.lock 一致性
- Basedpyright 类型检查

**Test 阶段**：

- 单元测试（`-m "not llm"`）
- LLM 测试（`-m "llm"`，需要模型）

此命令适合在本地模拟 CI 环境，提前发现问题。

______________________________________________________________________

## Pre-commit

本节介绍 Git pre-commit 钩子的使用方法。

### precommit-install - 安装 pre-commit hooks

`./scripts/dev.sh precommit-install`

安装 Git pre-commit hooks。安装后，每次 `git commit` 会自动运行检查。

安装的钩子配置位于项目根目录的 `.pre-commit-config.yaml` 中。

### precommit - 运行 pre-commit 检查

`./scripts/dev.sh precommit`

手动运行 pre-commit hooks，对所有文件进行检查。相当于 `git commit` 时自动触发的检查。

别名：`precommit-run`

______________________________________________________________________

## LLM (llama.cpp)

本节介绍 LLM 服务的管理命令。项目使用 llama.cpp 运行本地 LLM 推理。

### llm-status - LLM 服务状态

`./scripts/dev.sh llm-status`

检查 LLM 服务的当前状态，包括：

- llama-server 可执行文件是否存在
- 模型文件是否存在及大小
- 服务是否正在运行
- 如果运行中，显示 PID、端口和 URL

别名：`llm`

### llm-start - 启动 LLM 服务

`./scripts/dev.sh llm-start`

启动 llama-server 服务。后台运行，默认配置：

- 模型：`/opt/models/qwen3-4b-instruct.gguf`（或 `$LLAMA_MODEL`）
- 地址：`0.0.0.0`
- 端口：`8080`（可通过 `$LLAMA_PORT` 修改）
- 上下文大小：`2048`（可通过 `$LLAMA_CONTEXT_SIZE` 修改）
- GPU 层数：`0`（可通过 `$LLAMA_N_GPU_LAYERS` 修改）

日志输出到 `logs/llama-server.log`。

### llm-stop - 停止 LLM 服务

`./scripts/dev.sh llm-stop`

停止正在运行的 llama-server 服务。使用 `pkill` 优雅停止，如失败则强制终止。

### llm-test - 测试 LLM API

`./scripts/dev.sh llm-test`

测试 LLM API 的可用性，包括：

1. 检查服务是否运行，未运行则询问是否启动
2. 测试健康检查端点
3. 获取模型信息
4. 执行推理测试（发送 prompt 并获取响应）

如果服务未运行，会提示启动。

### llm-download - 下载模型

`./scripts/dev.sh llm-download`

下载 LLM 模型文件。执行 `scripts/init-models.sh` 脚本下载模型到 `/opt/models/` 目录。

支持的模型：

- Qwen3-4B-Instruct
- EmbeddingGemma-300M
- TinyLlama

______________________________________________________________________

## 环境变量

以下环境变量可用于自定义行为：

| 变量                      | 说明              | 默认值                             |
| ------------------------- | ----------------- | ---------------------------------- |
| `UV_PATH`                 | uv 可执行文件路径 | -                                  |
| `PYTHON_PATH`             | Python 解释器路径 | -                                  |
| `UV_INDEX_URL`            | PyPI 镜像 URL     | -                                  |
| `UV_CONCURRENT_DOWNLOADS` | 并发下载数        | -                                  |
| `UV_LINK_MODE`            | 依赖链接模式      | copy                               |
| `LLAMA_SERVER`            | llama-server 路径 | -                                  |
| `LLAMA_MODEL`             | LLM 模型文件路径  | /opt/models/qwen3-4b-instruct.gguf |
| `LLAMA_HOST`              | 服务监听地址      | 0.0.0.0                            |
| `LLAMA_PORT`              | 服务监听端口      | 8080                               |
| `LLAMA_N_GPU_LAYERS`      | GPU 加速层数      | 0                                  |
| `LLAMA_CONTEXT_SIZE`      | 上下文窗口大小    | 2048                               |
| `TEST_CHAT_MODEL`         | 测试用模型路径    | -                                  |

______________________________________________________________________

## 常见工作流

### 首次贡献代码

```bash
# 1. 克隆项目
git clone <repo>
cd beancount-daoru

# 2. 安装 uv（如未安装）
pip install uv

# 3. 设置环境
./scripts/dev.sh setup

# 4. 创建功能分支
git checkout -b feat/my-feature

# 5. 开发代码...

# 6. 提交前检查
./scripts/dev.sh pipeline

# 7. 提交并推送
git commit -m "feat: add my feature"
git push origin feat/my-feature
```

### 继续已有工作

```bash
# 1. 拉取最新代码
git pull

# 2. 同步依赖（如有变化）
./scripts/dev.sh sync

# 3. 运行快速检查
./scripts/dev.sh check

# 4. 开始开发...
```

### 添加新依赖

```bash
# 添加新依赖
./scripts/dev.sh add requests

# 验证安装
./scripts/dev.sh test
```

### 运行特定测试

```bash
# 单个测试文件
./scripts/dev.sh test-file tests/test_example.py

# 带覆盖率的测试
./scripts/dev.sh test-cov

# 只运行失败的测试
./scripts/dev.sh test -- --lf
```

### 发布新版本

```bash
# 1. 更新版本号（编辑 pyproject.toml）

# 2. 运行完整流水线
./scripts/dev.sh pipeline

# 3. 构建项目
./scripts/dev.sh build

# 4. 发布到 TestPyPI 测试
./scripts/dev.sh publish-test

# 5. 安装测试
pip install --index-url https://test.pypi.org/simple/ <package>

# 6. 确认无误后发布到正式 PyPI
./scripts/dev.sh publish
```

______________________________________________________________________

## 故障排除

### 问题：提示 "uv: command not found"

```bash
# 重新安装 uv
pip install --upgrade uv

# 或重启终端
```

### 问题：虚拟环境不存在

```bash
# 重新设置
./scripts/dev.sh setup
```

### 问题：依赖安装失败

```bash
# 清理缓存后重试
./scripts/dev.sh clean
./scripts/dev.sh sync
```

### 问题：LLM 测试失败

```bash
# 检查模型状态
./scripts/dev.sh llm-status

# 下载模型
./scripts/dev.sh llm-download

# 或检查服务是否运行
./scripts/dev.sh llm-start
```

### 问题：pre-commit 失败

```bash
# 重新安装 hooks
./scripts/dev.sh precommit-install

# 或跳过 hooks 提交（不推荐）
git commit --no-verify
```

______________________________________________________________________

## 获取帮助

```bash
# 显示所有命令
./scripts/dev.sh aliases

# 交互式菜单（数字选择）
./scripts/dev.sh

# 显示帮助
./scripts/dev.sh help
```

______________________________________________________________________

## 命令索引

| 命令              | 别名             | 说明               |
| ----------------- | ---------------- | ------------------ |
| setup             | install          | 完整环境设置       |
| reset             | recreate         | 重建虚拟环境       |
| status            | st               | 查看环境状态       |
| sync              | s                | 同步依赖           |
| upgrade           | up               | 更新所有依赖       |
| add               | -                | 添加依赖           |
| remove            | rm               | 移除依赖           |
| check             | c                | 运行所有检查       |
| fix               | fmt              | 自动修复问题       |
| lint              | l                | Ruff 代码检查      |
| format            | -                | Ruff 格式化检查    |
| type              | ty               | 类型检查           |
| markdownlint      | md               | Markdown 检查      |
| mdformat          | mdf              | Markdown 格式化    |
| shellcheck        | sc               | Shell 脚本检查     |
| shfmt             | sf               | Shell 格式化检查   |
| uvlock            | lock             | uv.lock 一致性检查 |
| test              | t                | 运行单元测试       |
| test-llm          | tl               | 运行 LLM 测试      |
| test-all          | ta               | 运行全部测试       |
| test-cov          | coverage, cov    | 测试覆盖率         |
| test-file         | tf               | 运行指定测试       |
| build             | b                | 构建项目           |
| publish-test      | publish-testpypi | 发布到 TestPyPI    |
| publish           | pypi             | 发布到 PyPI        |
| clean             | cache            | 清理缓存           |
| clean-all         | distclean        | 完全清理           |
| pipeline          | full             | 完整开发流水线     |
| ci                | -                | CI 检查流水线      |
| precommit-install | -                | 安装 pre-commit    |
| precommit         | precommit-run    | 运行 pre-commit    |
| llm-status        | llm              | LLM 服务状态       |
| llm-start         | -                | 启动 LLM 服务      |
| llm-stop          | -                | 停止 LLM 服务      |
| llm-test          | -                | 测试 LLM API       |
| llm-download      | -                | 下载模型           |
