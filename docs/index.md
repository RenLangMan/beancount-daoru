# Beancount-Daoru 项目介绍

## 项目概述

**beancount-daoru** 是一个专为中文用户设计的 Beancount 账单导入工具。"Daoru" 是中文 "导入" 的拼音，意为 "import"。
该项目旨在简化复式记账流程，通过自动化处理中文主流支付平台和银行的账单文件，帮助用户高效地将原始账单转换为 Beancount 格式。

## 核心价值

### 降低使用门槛

- 针对中文账单格式优化，无需手动格式转换
- 支持支付宝、微信、京东、美团等主流平台
- 兼容中国银行、交通银行等银行账单

### 提升记账效率

- 自动化解析原始文件（PDF/CSV/XLSX）
- 智能识别交易类型和账户信息
- 支持批量处理和归档

### 智能化辅助

- 集成 LLM 智能分类预测（可选）
- 基于历史数据的相似交易推荐
- 灵活的账户映射和配置

## 功能特性

### 支持的账单类型

| 平台/银行 | 导出方式            | 文件格式 | 状态      |
| --------- | ------------------- | -------- | --------- |
| 支付宝    | APP导出，发送到邮箱 | CSV      | ✅ 已支持 |
| 微信支付  | APP导出，发送到邮箱 | XLSX     | ✅ 已支持 |
| 京东      | APP导出，发送到邮箱 | CSV      | ✅ 已支持 |
| 美团      | APP导出，发送到邮箱 | CSV      | ✅ 已支持 |
| 中国银行  | APP导出，APP内下载  | PDF      | ✅ 已支持 |
| 交通银行  | APP导出，发送到邮箱 | PDF      | ✅ 已支持 |

### 核心功能

1. **原生格式解析**：直接处理原始账单文件，无需中间转换
2. **多账户支持**：灵活映射不同支付工具到对应会计科目
3. **交易状态处理**：支持成功、失败、退款等多种状态
4. **元数据提取**：自动从账单头部提取账户信息和日期范围
5. **重复检测**：智能识别并处理重复交易
6. **归档管理**：支持原始文件的自动归档和整理

## 架构设计

### 模块化架构

项目采用插件化架构，主要包含以下组件：

#### 1. 读取器 (Readers)

- `excel.Reader`：处理 Excel/CSV 格式文件
- `pdf_table.Reader`：提取 PDF 表格数据

#### 2. 解析器 (Parsers)

- 各平台专用解析器（支付宝、微信、京东等）
- 将原始记录转换为标准化交易结构

#### 3. 导入器 (Importers)

- 继承自 `beangulp.Importer` 基类
- 将标准化交易转换为 Beancount 条目

#### 4. 钩子 (Hooks)

- `path_to_name`：路径转文件名
- `reorder_by_importer_name`：条目排序
- `predict_missing_posting`：AI 预测缺失分录（需要 LLM 依赖）

### 数据流

```plaintext
原始账单文件 → 读取器 → 原始记录 → 解析器 → 标准交易 → 导入器 → Beancount条目 → 钩子 → 最终输出
```

## 使用方法

### 快速开始

1. **安装包**：

   ```bash
   pip install beancount-daoru
   ```

2. **基础配置**（`import.py`）：

   ```python
   import beangulp
   from beancount_daoru import AlipayImporter

   CONFIG = [
       AlipayImporter(
           account_mapping={
               "your-alipay-account-name": {
                   None: "Assets:Alipay",
                   "余额": "Assets:Alipay:Balance",
                   "余额宝": "Assets:Alipay:YuEBao",
               }
           },
           currency_mapping={
               None: "CNY",
           },
       ),
   ]

   if __name__ == "__main__":
       ingest = beangulp.Ingest(CONFIG)
       ingest()
   ```

3. **运行导入**：

   ```bash
   # 识别账单文件
   python import.py identify /path/to/bills

   # 导入交易数据
   python import.py extract /path/to/bills -o output.beancount

   # 归档原始文件
   python import.py archive /path/to/bills -o /path/to/archive
   ```

### Fava 集成

支持在 Fava 中进行可视化导入，需要在主账本中添加：

```beancount
option "import-config" "/path/to/import.py"
option "import-dirs" "/path/to/bills"
```

## 技术特色

### 现代化开发栈

- **Python ≥ 3.10**：使用最新语言特性
- **类型安全**：全面使用类型注解和 Pydantic 验证
- **模块化设计**：组件松耦合，易于扩展和维护
- **性能优化**：LRU 缓存和向量索引加速处理

### 智能化功能

1. **AI 辅助分类**：使用 OpenAI 兼容 API 进行交易分类预测
2. **Few-shot 学习**：基于相似历史交易提供上下文
3. **向量相似度搜索**：使用 `usearch` 库快速查找相似交易
4. **智能缓存**：`diskcache` 提高重复查询性能

### 配置灵活性

```python
# 账户映射（支持多级映射）
account_mapping={
    "source_account": {
        None: "Assets:Default",  # 默认账户
        "余额": "Assets:Cash",    # 特定子账户
        "信用卡": "Liabilities:CreditCard",
    }
}

# 货币映射
currency_mapping={
    None: "CNY",    # 默认货币
    "¥": "CNY",     # 符号映射
    "USD": "USD",   # 外币支持
}
```

## 扩展开发

### 添加新导入器

1. 在 `src/beancount_daoru/importers/` 创建新文件
2. 实现 `Parser` 协议类处理特定格式
3. 创建 `Importer` 类继承基类
4. 在 `__init__.py` 中导出

### 添加新读取器

1. 在 `src/beancount_daoru/readers/` 创建新文件
2. 实现 `Reader` 协议类

### 添加新钩子

1. 在 `src/beancount_daoru/hooks/` 创建新文件
2. 实现 `Hook` 协议类

## 项目生态

### 兼容性

- **Beangulp**：完全兼容官方导入框架
- **Fava**：支持可视化导入界面
- **Beancount 3**：支持最新版本

### 相关项目

- **double-entry-generator**：基于规则的账单转换工具
- **china_bean_importers**：其他中文账单导入器
- **smart_importer**：官方机器学习分类器

## 质量保证

### 代码质量

- **Ruff**：代码格式化和静态检查
- **Pyright**：类型检查
- **Pytest**：单元测试（覆盖率 > 90%）
- **GitHub Actions**：持续集成和自动发布

### 开发流程

- 使用 `uv` 进行依赖管理
- 严格的代码审查
- 语义化版本控制

## 贡献指南

欢迎提交 Issue 和 Pull Request，包括：

- Bug 报告和功能请求
- 文档改进
- 新导入器实现
- 测试用例添加

详见 [CONTRIBUTING.md](../CONTRIBUTING.md) 和 [开发者指南](DEVELOPMENT.md)

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE.txt](../LICENSE.txt)

## 获取帮助

- **GitHub Issues**：报告问题或请求功能
- **示例代码**：参考 `examples/` 目录
- **相关文档**：查看项目 README 和代码注释

______________________________________________________________________

**beancount-daoru** 致力于为中文 Beancount 用户提供最佳账单导入体验，让复式记账变得更简单、更高效。
