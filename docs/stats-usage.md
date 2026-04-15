# stats.py 使用说明

Beancount 导入管理脚本，整合了导入后的所有统计、查看、搜索、验证、合并和归档操作。

## 快速开始

```bash
# 运行所有统计（默认行为）
python scripts/stats.py

# 查看帮助
python scripts/stats.py -h
```

## 全局选项

| 选项 | 说明 | 默认值 |
| ------------ | ----------------------- | ---------------- |
| `--data-dir` | beancount-data 目录路径 | `beancount-data` |

所有子命令都支持 `--data-dir` 指定数据目录，需放在子命令之前：

```bash
python scripts/stats.py --data-dir /path/to/beancount-data stats --all
```

______________________________________________________________________

## 子命令一览

| 子命令 | 功能 | 对应原 shell 命令 |
| --------- | ------------ | --------------------------- |
| `stats` | 统计分析 | `grep` + `awk` 各种统计 |
| `view` | 查看交易记录 | `head` / `tail` / `cat` |
| `search` | 搜索交易 | `grep -A 6 "账户名"` |
| `check` | 语法验证 | `bean-check` |
| `report` | 生成报表 | `bean-report` |
| `merge` | 合并到主账本 | `echo include >> main.bean` |
| `archive` | 归档账单文件 | 移动 CSV 到归档目录 |
| `clean` | 清理空行 | `sed -i '/^$/d'` |

______________________________________________________________________

## stats - 统计分析

### stats - 统计分析-选项

| 选项 | 说明 |
| ------------- | ------------------------------ |
| `--all` | 运行所有统计（默认，无需指定） |
| `--accounts` | 各账户交易次数和金额 |
| `--types` | 交易类型、状态、收支方向 |
| `--integrity` | 交易完整性检查 |
| `--payment` | 原始收付款方式汇总 |
| `--mapping` | 支付方式 → Beancount 账户映射 |

### stats - 统计分析-示例

```bash
# 运行所有统计
python scripts/stats.py stats

# 只看账户统计
python scripts/stats.py stats --accounts

# 只看类型统计和完整性检查
python scripts/stats.py stats --types --integrity

# 查看原始支付方式和映射
python scripts/stats.py stats --payment --mapping
```

### stats - 统计分析-输出说明

**--accounts** 输出每个 Beancount 账户的交易次数和金额合计，并按 Assets / Liabilities / Expenses 等类别汇总。

**--types** 统计交易类型（餐饮美食、充值缴费等）、交易状态（交易成功、交易关闭等）和收支方向（支出、收入、不计收支）。

**--integrity** 检查：

**--payment** 从原始 CSV 中统计收付款方式，分"原始（含优惠变体）"和"清理后（去掉 & 后缀）"两组。

**--mapping** 对比 CSV 中的原始支付方式与 `fava_import_config.py` 中的账户映射，标注未映射的支付方式。

______________________________________________________________________

## view - 查看交易记录

### view - 查看交易记录-选项

| 选项 | 说明 |
| ------------------------ | ---------------------- |
| `--head N` | 查看前 N 条交易 |
| `--tail N` | 查看最后 N 条交易 |
| `--date YYYY-MM-DD` | 查看指定日期的交易 |
| `--date-range START,END` | 查看日期范围内的交易 |
| `--brief` | 简洁模式，不显示元数据 |

### view - 查看交易记录-示例

```bash
# 查看前 10 条交易
python scripts/stats.py view --head 10

# 查看最后 5 条交易
python scripts/stats.py view --tail 5

# 查看 2026-01-15 的交易
python scripts/stats.py view --date 2026-01-15

# 查看 2026-01 到 2026-02 的交易
python scripts/stats.py view --date-range 2026-01-01,2026-02-28

# 简洁模式（不显示 time/dc/type 等元数据）
python scripts/stats.py view --head 20 --brief

# 无选项：显示所有交易的概览列表
python scripts/stats.py view
```

______________________________________________________________________

## search - 搜索交易

### search - 搜索交易-选项

| 选项 | 说明 |
| -------------------------- | ---------------------------- |
| `--account KEYWORD` / `-a` | 按账户关键词搜索（模糊匹配） |
| `--payee KEYWORD` / `-p` | 按收款方搜索（模糊匹配） |
| `--type KEYWORD` / `-t` | 按交易类型搜索（模糊匹配） |
| `--brief` | 简洁模式 |

搜索结果会附带金额汇总。

### search - 搜索交易-示例

```bash
# 搜索农业银行相关交易
python scripts/stats.py search --account ABC

# 搜索花呗交易
python scripts/stats.py search -a Huabei

# 搜索特定商户
python scripts/stats.py search --payee 刘记

# 搜索餐饮类交易
python scripts/stats.py search --type 餐饮

# 简洁模式
python scripts/stats.py search -a ICBC --brief
```

______________________________________________________________________

## check - 验证 Beancount 语法

### check - 验证 Beancount 语法-选项

| 选项 | 说明 |
| -------- | ------------------------------ |
| `--main` | 检查主账本（默认检查导入文件） |

需要系统已安装 `bean-check`（`pip install beancount`）。

### check - 验证 Beancount 语法-示例

```bash
# 检查导入文件的语法
python scripts/stats.py check

# 检查主账本的语法
python scripts/stats.py check --main
```

______________________________________________________________________

## report - 生成报表

### report - 生成报表-选项

| 选项 | 说明 |
| ------------- | ------------------------------ |
| `report_type` | 报表类型，默认 `balances` |
| `--main` | 使用主账本（默认使用导入文件） |

常用报表类型：`balances`、`income_statement`、`journal`、`holdings`。

需要系统已安装 `bean-report`（`pip install beancount`）。

### report - 生成报表-示例

```bash
# 余额报表
python scripts/stats.py report balances

# 收支统计
python scripts/stats.py report income_statement

# 使用主账本
python scripts/stats.py report balances --main
```

______________________________________________________________________

## merge - 合并到主账本

### merge - 合并到主账本-选项

| 选项 | 说明 |
| ----------- | ----------------------------- |
| `--include` | 使用 include 方式引用（推荐） |

两种合并方式：

1. **include 方式**（推荐）：在主账本中添加 `include "imported_transactions.bean"`，不修改原文件内容，方便后续重新导入。

1. **直接追加**：将导入文件内容追加到主账本末尾，会提示确认。

### merge - 合并到主账本-示例

```bash
# 推荐：使用 include 引用
python scripts/stats.py merge --include

# 直接追加（会提示确认）
python scripts/stats.py merge
```

______________________________________________________________________

## archive - 归档账单文件

### archive - 归档账单文件-选项

| 选项 | 说明 |
| ----------------- | -------------------------- |
| `-o` / `--output` | 归档目录名，默认 `archive` |

将 `downloads/` 中的 CSV 文件移动到归档目录。如果目标文件已存在，自动添加时间戳避免覆盖。

### archive - 归档账单文件-示例

```bash
# 归档到默认 archive/ 目录
python scripts/stats.py archive

# 归档到指定目录
python scripts/stats.py archive -o archive/2026-q1
```

______________________________________________________________________

## clean - 清理空行

移除 `imported_transactions.bean` 中的空行，保持原文件编码不变。

### clean - 清理空行-示例

```bash
python scripts/stats.py clean
```

______________________________________________________________________

## 典型工作流

```bash
1. 导入账单
   cd beancount-data
   python fava_import_config.py extract downloads/ -o imported_transactions.bean

2. 查看统计
   python ../scripts/stats.py stats

3. 检查完整性
   python ../scripts/stats.py stats --integrity

4. 搜索特定交易
   python ../scripts/stats.py search -a Huabei

5. 验证语法
   python ../scripts/stats.py check

6. 合并到主账本
   python ../scripts/stats.py merge --include

7. 归档原始账单
   python ../scripts/stats.py archive
```

## 注意事项

- 脚本自动检测文件编码（UTF-8 / GBK），兼容 Windows 环境
- `--payment` 和 `--mapping` 依赖 `downloads/` 目录下的支付宝 CSV 文件
- `check` 和 `report` 子命令需要系统安装 beancount (`pip install beancount`)
- `mapping` 统计中的映射关系硬编码在脚本中，如果 `fava_import_config.py` 中的映射有变更，需同步更新脚本
