# 开发者指南

## 前置要求

- Python 3.10 或更高版本
- Git

## 5分钟快速上手

### 1. 安装 uv（包管理器）

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pip
pip install uv
```

### 2. 克隆并设置项目

```bash
git clone <your-repo-url>
cd beancount-daoru
./scripts/dev.sh setup
```

### 3. 运行完整检查

```bash
./scripts/dev.sh pipeline
```

## 常见工作流

### 场景1：首次贡献代码

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

### 场景2：已有开发环境，继续工作

```bash
# 1. 拉取最新代码
git pull

# 2. 同步依赖（如有变化）
./scripts/dev.sh sync

# 3. 开始开发...
```

### 场景3：添加新依赖

```bash
# 添加依赖
./scripts/dev.sh add requests

# 同步（自动执行）
# 更新 pyproject.toml 和 uv.lock
```

## 命令速查

| 步骤 | 命令 | 说明 |
| ------ | ------ | ------ |
| 安装 uv | `pip install uv` | 首次使用 |
| 设置环境 | `./scripts/dev.sh setup` | 创建虚拟环境+安装依赖 |
| 完整流水线 | `./scripts/dev.sh pipeline` | 修复→检查→测试 |
| 代码检查 | `./scripts/dev.sh check` | Ruff + 类型检查 |
| 运行测试 | `./scripts/dev.sh test` | 运行所有测试 |
| 查看状态 | `./scripts/dev.sh status` | 查看环境信息 |
| 清理缓存 | `./scripts/dev.sh clean` | 清理临时文件 |

## 获取帮助

```bash
# 显示所有命令
./scripts/dev.sh aliases

# 交互式菜单
./scripts/dev.sh
```

## 故障排除

### **问题：提示 "uv: command not found"**

```bash
# 重新安装 uv
pip install --upgrade uv
# 或重启终端
```

### **问题：虚拟环境不存在**

```bash
# 重新设置
./scripts/dev.sh setup
```

### **问题：依赖安装失败**

```bash
# 清理缓存后重试
./scripts/dev.sh clean
./scripts/dev.sh sync
```
