# Docker 构建脚本

## 脚本说明

### 1. build-docker-optimized.sh（优化版）

- **特点**: 简洁、快速、容错性高
- **适用**: 开发测试环境
- **标签策略**: 使用 CNB_COMMIT_SHORT
- **推送**: CI 环境自动推送

### 2. build-docker-production.sh（生产版）

- **特点**: 严格错误处理、智能标签策略
- **适用**: 生产环境、CI/CD
- **标签策略**: Tag > 默认分支 > commit SHA
- **推送**: 条件推送（仅默认分支推送 latest）

## 使用方法

### 本地构建

```bash
# 使用优化版
./scripts/build-docker-optimized.sh

# 使用生产版
./scripts/build-docker-production.sh
```

### CI 环境

```yaml
# .cnb.yml 示例
main:
  push:
    - stages:
        - name: 构建镜像
          script: ./scripts/build-docker-production.sh
```

## 环境变量

| 变量 | 说明 | 必需 |
| ----------------------- | --------------- | ------------ |
| CNB_REPO_SLUG_LOWERCASE | 仓库路径小写 | 是（生产版） |
| CNB_DOCKER_REGISTRY | Docker 仓库地址 | 否 |
| CNB_COMMIT_SHORT | Commit SHA | 否 |
| CNB_BRANCH | 分支名 | 否 |
| CNB_DEFAULT_BRANCH | 默认分支 | 否 |
| CNB_IS_TAG | 是否 Tag | 否 |
| CI | CI 环境标识 | 否 |

## 日志

构建日志保存在 `build-logs/` 目录：

- 完整构建日志
- 错误和警告摘要
