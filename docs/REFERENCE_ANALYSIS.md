# 参考脚本分析：alipay_parser

## 概述

本项目在开发过程中参考了一个外部的 `alipay_parser` 实现。以下是对该实现的分析与总结。

## 设计特点

### 配置驱动设计

```python
def get_default_config(self) -> ParserConfig:
    return {
        "file_patterns": ["alipay*.csv", "支付宝*.csv"],
        "encoding": "gbk",
        "field_mapping": {
            "交易时间": "date",
            "交易对方": "payee",
            # ...
        },
    }
```

- 通过字典配置字段映射关系
- 支持多种文件名模式
- 默认编码配置（GBK）

### 通用解析框架

- `BaseParser` 基类定义统一接口
- 子类通过配置覆盖实现差异化
- `normalize_transaction()` 钩子方法支持扩展

## 优点

| 特性       | 说明                                 |
| ---------- | ------------------------------------ |
| 可配置性强 | 通过配置即可适配新格式，无需修改代码 |
| 框架清晰   | 基类+子类的继承结构，职责分明        |
| 易于扩展   | 添加新字段只需扩展配置               |

## 缺点

| 特性       | 说明                                   |
| ---------- | -------------------------------------- |
| 类型安全弱 | 字段映射依赖运行时字典，缺少编译期检查 |
| 复杂度较高 | 通用框架带来额外的抽象开销             |
| 维护成本   | 配置与代码分离，调试时需要对照多处     |

## 本项目的设计决策

当前项目采用**硬编码 + TypedDict** 的方式：

```python
Record = TypedDict("Record", {
    "交易时间": datetime,
    "交易对方": StrField,
    # ...
})
```

### 选择硬编码的原因

1. **字段稳定**：支付宝等平台字段相对固定
2. **类型安全**：Pydantic + TypedDict 提供编译期检查
3. **代码直观**：字段映射一目了然
4. **调试简单**：无需追踪配置与代码的对应关系

### 已借鉴的特性

以下特性已从参考实现中提取并整合：

- [x] 灵活日期解析（`parse_datetime_flexible`）
- [x] ZIP 文件解压（`extract_zip_file`）
- [x] 文件验证（`validate_file`）
- [x] 编码自动检测（chardet）
- [x] 组合支付拆分（`_extract_payment_splits`）
- [x] 元数据扩展（`Extra` NamedTuple）

## 银行账单配置驱动设计

对于**银行账单**，不同银行的字段名差异较大（如"记账日期" vs "Trans Date\\n交易日期"），配置驱动设计更加合适。

### 设计方案：ConfigurableParser 基类

```python
@dataclass(frozen=True)
class BankFieldConfig:
    """银行账单字段配置."""
    file_patterns: tuple[str, ...] = ()
    encoding: str = "gbk"
    date_field: str = "交易日期"
    amount_field: str = "交易金额"
    balance_field: str | None = None
    payee_field: str = "对方户名"
    description_field: str | None = None
    channel_field: str | None = None
    dc_field: str | None = None
    dc_mapping: dict[str, str] = field(default_factory=lambda: {"借": "支出", "贷": "收入"})


class ConfigurableParser(ABC):
    """配置驱动的银行账单解析器基类."""

    bank_config: BankFieldConfig | None = None

    def parse_amount(self, record: dict[str, str]) -> tuple[Decimal, str] | None:
        """根据配置自动解析金额和方向."""
        ...

    def parse(self, record: dict[str, str]) -> Transaction:
        """使用配置映射解析记录."""
        ...
```

### 使用示例

```python
class ICBCParser(ConfigurableParser):
    """工商银行解析器."""

    bank_config = BankFieldConfig(
        file_patterns=("icbc*.csv", "工商银行*.csv"),
        date_field="交易日期",
        amount_field="交易金额",
        payee_field="对方户名",
        dc_field="借贷标志",
        dc_mapping={"借": "支出", "贷": "收入"},
    )

    # 可覆盖 extract_metadata 等方法
```

### 设计决策

| 方案               | 适用场景             | 优缺点             |
| ------------------ | -------------------- | ------------------ |
| 硬编码 Parser      | 字段固定（如支付宝） | 类型安全、调试简单 |
| ConfigurableParser | 字段差异大（如银行） | 配置灵活、易扩展   |

## 微信支付

- 状态：已实现 (`src/beancount_daoru/importers/wechat.py`)
- 设计：遵循项目统一决策，采用硬编码 TypedDict + Pydantic 验证
- 借鉴：金额拆分、日期解析等工具函数

## 账户映射模块分析

参考项目中提供了 `AccountMapper` 类，提供智能账户映射功能：

### 账户映射功能对比

| 功能         | 当前项目                                        | 参考项目             |
| ------------ | ----------------------------------------------- | -------------------- |
| **映射方式** | 静态嵌套字典 `account_mapping[account][method]` | 动态智能匹配         |
| **配置来源** | 用户手动配置                                    | SQLite 数据库 + 规则 |
| **组合支付** | 不支持                                          | `&` 分隔符支持       |
| **复式记账** | 不支持                                          | 借方/贷方分离        |
| **分类映射** | 不支持                                          | category → account   |

### 账户映射设计决策

**当前不需要借鉴**，理由：

1. **项目定位**：beancount-daoru 是轻量级导入器，用户手动配置映射更可控
2. **复杂度**：参考项目 ~500 行，当前 `Importer.account_mapping` 10 行搞定
3. **组合支付**：当前通过 `Extra.payment_splits` 已支持，无需额外处理

### 未来可借鉴部分

如果未来需要，可仅借鉴智能匹配逻辑：

```python
def _match_bank_account(payment_method: str) -> str | None:
    """从支付方式自动识别银行卡账户"""
    bank_keywords = ["工商银行", "建设银行", ...]
    # 简单匹配逻辑
```

## 类型定义分析

参考项目使用 TypedDict 定义中间数据结构：

```python
class TransactionData(TypedDict):
    datetime: str
    date: str
    payee: str
    amount: float
    # ...
```

### 对比

| 类型           | 参考项目                      | 当前项目                   |
| -------------- | ----------------------------- | -------------------------- |
| **核心交易**   | `TransactionData` (TypedDict) | `Transaction` (NamedTuple) |
| **记账分录**   | 无                            | `Posting` (NamedTuple)     |
| **额外元数据** | `extra_fields: Dict`          | `Extra` (NamedTuple)       |

### 当前项目类型更优

1. **NamedTuple 优于 TypedDict**：

   - 不可变，运行时更高效
   - 固定字段，IDE 自动补全更好
   - 与 Beancount 原生数据结构一致

2. **当前核心类型已完整**：

   - `Extra`：交易元数据（时间、状态、类型等）
   - `Posting`：记账分录（金额、账户、货币）
   - `Transaction`：完整交易（日期、对方、说明、分录）
   - `Metadata`：文件元数据（账户、日期、货币）

## utils 模块对比

参考项目的 `utils` 模块包含丰富的工具函数：

```python
def parse_date(date_str: str) -> datetime
def clean_amount(amount_str: str) -> float
def detect_encoding(file_path: str) -> str
def normalize_path(path: str) -> str
class TransactionNormalizer:
    def normalize_payee(payee: str) -> str
    def normalize_payment_method(payment_method: str) -> str
```

### utils 功能对比

| 功能       | 参考项目                | 当前项目                  |
| ---------- | ----------------------- | ------------------------- |
| 日期解析   | `parse_date`            | `parse_datetime_flexible` |
| ZIP 解压   | ✓                       | ✓                         |
| 路径规范化 | ✓                       | ✗                         |
| 金额清理   | ✓                       | ✗                         |
| 编码检测   | ✓                       | ✗                         |
| 交易标准化 | `TransactionNormalizer` | ✗                         |

### utils 借鉴状态

| 功能       | 状态     | 说明                                 |
| ---------- | -------- | ------------------------------------ |
| 日期解析   | ✓ 已借鉴 | 格式支持略有差异                     |
| ZIP 解压   | ✓ 已借鉴 | 核心功能一致                         |
| 路径规范化 | ✗ 不需要 | beancount-daoru 不涉及跨平台路径问题 |
| 金额清理   | ✗ 不需要 | Parser 层已通过 Pydantic 验证        |
| 编码检测   | ✗ 不需要 | Reader 层处理                        |
| 交易标准化 | ✗ 不需要 | Parser 层硬编码实现                  |

### utils 结论

当前项目的 `utils` 已覆盖核心需求（日期解析、ZIP 解压），其他功能分散在 Reader/Parser 层处理。

## 规则匹配方案

当前项目使用 LLM（`predict_missing_posting.py`）预测缺失的会计科目。参考项目使用规则匹配。

### 简单规则配置方案（YAML）

对于不需要 LLM 的简单场景，可以设计轻量级规则配置：

```yaml
# rules/payee.yaml
payee_rules:
  - match: "美团外卖"
    account: "Expenses:食品酒水:外卖"
    type: "expense"

  - match: "饿了么"
    account: "Expenses:食品酒水:外卖"
    type: "expense"

  - match: "地铁"
    account: "Expenses:交通出行"
    type: "expense"

  - match: "工资"
    account: "Income:薪资收入"
    type: "income"
```

```yaml
# rules/regex.yaml
regex_rules:
  - pattern: "(.+)超市"
    account: "Expenses:购物消费:超市"
    group: 1  # 提取括号内容作为备注

  - pattern: "便利店-(.+)"
    account: "Expenses:购物消费:便利店"
    group: 1
```

### 实现示例

```python
# src/beancount_daoru/rules.py
from dataclasses import dataclass
from pathlib import Path
import re
import yaml

@dataclass
class Rule:
    pattern: str
    account: str
    type: str  # expense/income
    group: int | None = None
    narration_template: str | None = None

class RuleMatcher:
    def __init__(self, rules_dir: Path):
        self.payee_rules: list[Rule] = []
        self.regex_rules: list[tuple[re.Pattern, Rule]] = []
        self._load_rules(rules_dir)

    def _load_rules(self, rules_dir: Path):
        # 加载 payee.yaml
        payee_file = rules_dir / "payee.yaml"
        if payee_file.exists():
            with open(payee_file) as f:
                data = yaml.safe_load(f)
                for item in data.get("payee_rules", []):
                    self.payee_rules.append(Rule(**item))

        # 加载 regex.yaml
        regex_file = rules_dir / "regex.yaml"
        if regex_file.exists():
            with open(regex_file) as f:
                data = yaml.safe_load(f)
                for item in data.get("regex_rules", []):
                    pattern = re.compile(item["pattern"])
                    self.regex_rules.append((pattern, Rule(**item)))

    def match(self, payee: str, narration: str) -> Rule | None:
        # 1. 精确匹配收款方
        for rule in self.payee_rules:
            if rule.pattern in payee:
                return rule

        # 2. 正则匹配
        text = f"{payee} {narration}"
        for pattern, rule in self.regex_rules:
            if m := pattern.search(text):
                return rule

        return None
```

### 方案对比

| 方案          | 适用场景                 | 优点           | 缺点             |
| ------------- | ------------------------ | -------------- | ---------------- |
| **YAML 规则** | 固定模式（超市、地铁等） | 简单、无需 LLM | 无法处理复杂语义 |
| **LLM 预测**  | 复杂/模糊场景            | 智能理解       | 需要 API、成本   |

### 设计建议

- **当前状态**：LLM Hook 适合复杂场景
- **可选增强**：添加轻量级 YAML 规则作为补充
- **优先级**：低。YAML 规则可作为用户自定义扩展，暂不内置

## 结论

- **支付平台**（支付宝/微信）：字段固定，保持硬编码 TypedDict
- **银行账单**：字段差异大，使用 ConfigurableParser + BankFieldConfig
- **账户映射**：保持当前简单静态配置，不引入动态匹配
- **类型定义**：当前 NamedTuple 方案优于 TypedDict
- **规则匹配**：YAML 规则可作为 LLM 的轻量补充（暂不内置）
