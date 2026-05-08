# 开发者指南

本文档面向希望扩展或定制 beancount-daoru 的开发者，介绍项目的核心架构和扩展方法。

## 核心概念

beancount-daoru 将账单文件转换为 Beancount 条目，采用模块化架构：

```text
账单文件 (CSV/Excel/PDF)
    ↓
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ Reader  │ →  │ Parser  │ →  │Importer │ →  │  Hook   │
└─────────┘    └─────────┘    └─────────┘    └─────────┘
```

| 组件         | 职责                     | 协议/基类                |
| ------------ | ------------------------ | ------------------------ |
| **Reader**   | 读取文件，提取原始数据行 | `Reader` Protocol        |
| **Parser**   | 解析记录，转换为中间结构 | `Parser` Protocol        |
| **Importer** | 转换并映射账户/货币      | 继承 `beangulp.Importer` |
| **Hook**     | 后处理，修改最终输出     | `Hook` Protocol          |

______________________________________________________________________

## 项目结构

```text
src/beancount_daoru/
├── importer.py          # 核心 Importer 基类和数据结构
├── reader.py            # Reader 接口定义
├── hook.py              # Hook 接口定义
├── utils.py             # 通用工具函数
├── importers/           # 各平台导入器实现
│   ├── alipay.py        # 支付宝
│   ├── wechat.py        # 微信支付
│   ├── jd.py            # 京东
│   ├── meituan.py       # 美团
│   ├── boc.py           # 中国银行
│   └── bocom.py         # 交通银行
├── readers/             # 文件读取器
│   ├── excel.py         # Excel/CSV 读取器
│   └── pdf_table.py     # PDF 表格读取器
└── hooks/               # 后处理钩子
    ├── path_to_name.py
    ├── reorder_by_importer_name.py
    └── predict_missing_posting.py  # AI 预测钩子
```

______________________________________________________________________

## 核心接口

### Reader 协议

```python
from pathlib import Path
from collections.abc import Iterator

class Reader(Protocol):
    """读取器：负责从文件提取原始数据"""

    def read_captions(self, file: Path) -> Iterator[str]:
        """读取文件头部的元数据行（如账户名、日期范围）"""
        ...

    def read_records(self, file: Path) -> Iterator[dict[str, str]]:
        """读取数据记录，返回字典列表"""
        ...
```

### Parser 协议

```python
from collections.abc import Iterator
from datetime import date

class Metadata(NamedTuple):
    """从文件头部提取的元数据"""
    account: str | None      # 账户标识
    date: date | None        # 账单日期
    currency: str | None = None

class Transaction(NamedTuple):
    """标准化的交易结构"""
    date: date
    extra: Extra             # 扩展信息（时间、类型等）
    payee: str | None = None
    narration: str | None = None
    postings: Iterable[Posting] = ()
    balance: Posting | None = None

class Parser(Protocol):
    """解析器：负责将原始记录转换为标准结构"""

    @property
    def reversed(self) -> bool:
        """记录是否按逆时间顺序排列"""
        return False

    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        """从文件头部提取元数据"""
        ...

    def parse(self, record: dict[str, str]) -> Transaction:
        """解析单条交易记录"""
        ...
```

### Importer 基类

```python
import beangulp
from beancount_daoru.importer import Importer as BaseImporter

class Importer(BaseImporter):
    """导入器：继承 beangulp.Importer"""

    def __init__(
        self,
        account_mapping: dict,
        currency_mapping: dict,
        ...
    ):
        super().__init__(
            filename_pattern,  # 正则表达式匹配文件名
            reader,            # Reader 实例
            parser,            # Parser 实例
            account_mapping=account_mapping,
            currency_mapping=currency_mapping,
        )
```

### Hook 协议

```python
from beancount import Directives
from beangulp import Importer

Imported = tuple[str, Directives, str, Importer]  # (filename, directives, account, importer)

class Hook(Protocol):
    """钩子：对导入条目进行后处理"""

    def __call__(
        self, imported: list[Imported], existing: Directives
    ) -> list[Imported]:
        """处理并返回修改后的条目列表"""
        ...
```

______________________________________________________________________

## 添加新导入器

以添加"拼多多"导入器为例：

### 1. 创建文件

```python
# src/beancount_daoru/importers/pinduoduo.py

import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BeforeValidator, TypeAdapter

from beancount_daoru.importer import (
    Extra,
    ImporterKwargs,
    Metadata,
    ParserError,
    Posting,
    Transaction,
)
from beancount_daoru.importer import Importer as BaseImporter
from beancount_daoru.importer import Parser as BaseParser
from beancount_daoru.readers import excel
```

### 2. 定义记录类型

```python
# 使用 Pydantic 定义字段验证
AmountField = Annotated[tuple[str, Decimal], BeforeValidator(_split_amount)]

Record = TypedDict("Record", {
    "交易时间": datetime,
    "交易类型": str,
    "金额": AmountField,
    "支付方式": str,
})
```

### 3. 实现 Parser

```python
class Parser(BaseParser):
    """拼多多交易记录解析器"""

    __account_pattern = re.compile(r"拼多多用户名[:：]\[([^\]]*)\]")
    __date_pattern = re.compile(r"终止时间[:：]\[(\d{4}-\d{2}-\d{2})\]")

    @property
    def reversed(self) -> bool:
        return True  # 或 False，取决于账单顺序

    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        # 解析文件头部，提取账户和日期
        ...

    def parse(self, record: dict[str, str]) -> Transaction:
        # 解析单条记录
        ...
```

### 4. 实现 Importer

```python
class Importer(BaseImporter):
    """拼多多账单导入器"""

    def __init__(self, **kwargs: Unpack[ImporterKwargs]) -> None:
        super().__init__(
            re.compile(r"拼多多账单\(\d{8}-\d{8}\)\.csv"),
            excel.Reader(header=19, encoding="utf-8-sig"),
            Parser(),
            **kwargs,
        )
```

### 5. 导出

```python
# src/beancount_daoru/importers/__init__.py

from beancount_daoru.importers.pinduoduo import Importer as PinduoduoImporter

__all__ = [
    ...,
    "PinduoduoImporter",
]
```

______________________________________________________________________

## 添加新 Hook

Hook 用于对导入结果进行后处理，如重命名、排序、AI 预测等。

### 基础 Hook 示例

```python
# src/beancount_daoru/hooks/my_custom_hook.py

from beancount import Directives
from typing_extensions import override

from beancount_daoru.hook import Hook as BaseHook
from beancount_daoru.hook import Imported


class Hook(BaseHook):
    """自定义钩子：过滤特定账户的条目"""

    def __init__(self, exclude_accounts: set[str] | None = None):
        self.exclude_accounts = exclude_accounts or set()

    @override
    def __call__(
        self, imported: list[Imported], existing: Directives
    ) -> list[Imported]:
        result = []
        for filename, directives, account, importer in imported:
            if account not in self.exclude_accounts:
                result.append((filename, directives, account, importer))
        return result
```

### AI 预测钩子

`predict_missing_posting.py` 是一个复杂的 Hook 示例，展示了：

- 使用 LLM 预测缺失的会计科目
- 向量相似度搜索查找相似历史交易
- 异步处理大量条目

______________________________________________________________________

## 测试策略

### 单元测试结构

```python
# tests/beancount_daoru/importers/test_pinduoduo.py

import pytest
from datetime import date

from beancount_daoru.importers.pinduoduo import Importer, Parser


class TestParser:
    """测试 Parser 解析逻辑"""

    @pytest.fixture
    def parser(self) -> Parser:
        return Parser()

    def test_extract_metadata(self, parser: Parser) -> None:
        """测试元数据提取"""
        texts = iter([
            "拼多多用户名:[test_user]",
            "终止时间:[2024-01-31]",
        ])
        metadata = parser.extract_metadata(texts)
        assert metadata.account == "test_user"
        assert metadata.date == date(2024, 1, 31)

    def test_parse_income(self, parser: Parser) -> None:
        """测试收入交易解析"""
        record = {
            "交易时间": "2024-01-15 10:30:00",
            "交易类型": "收入",
            "金额": "¥100.00",
            "支付方式": "微信支付",
        }
        transaction = parser.parse(record)
        assert transaction.date == date(2024, 1, 15)


class TestImporter:
    """测试 Importer 集成"""

    def test_identify(self, tmp_path: Path) -> None:
        """测试文件识别"""
        importer = Importer(
            account_mapping={"test": {None: "Assets:Test"}},
            currency_mapping={"¥": "CNY"},
        )
        test_file = tmp_path / "拼多多账单(20240101-20240131).csv"
        assert importer.identify(str(test_file)) is True
```

### Mock 策略

对于需要外部依赖的测试：

```python
from unittest.mock import patch

def test_with_mocked_llm(self) -> None:
    """测试 AI 预测功能"""
    with patch("beancount_daoru.hooks.predict_missing_posting.ChatBot") as mock:
        mock.return_value.chat.return_value = "Assets:Food:Dining"
        # 执行测试...
```

______________________________________________________________________

## 调试技巧

### 查看导入结果

```python
# 在 import.py 中添加调试输出
if __name__ == "__main__":
    ingest = beangulp.Ingest(CONFIG, HOOKS)

    # 调试：查看识别结果
    for filepath in ingest.identify("downloads"):
        print(f"识别: {filepath}")
```

### 打印 Beancount 条目

```bash
bean-query ledger/imported.beancount \
  "SELECT date, payee, narration, account, units WHERE date = 2024-01-15"
```

### 常见问题

| 问题         | 解决方案                                      |
| ------------ | --------------------------------------------- |
| 文件无法识别 | 检查文件名正则是否匹配                        |
| 账户映射错误 | 确认 `account_mapping` 中的键与文件元数据一致 |
| 金额解析失败 | 检查 `currency_mapping` 是否包含所有货币符号  |
| AI 预测超时  | 增加超时时间或检查 LLM 服务状态               |

______________________________________________________________________

## 扩展开发清单

添加新导入器时，确保完成以下步骤：

- [ ] 创建 `src/beancount_daoru/importers/xxx.py`
- [ ] 实现 `Parser` 协议
- [ ] 实现 `Importer` 类
- [ ] 在 `__init__.py` 中导出
- [ ] 添加示例文件到 `examples/`
- [ ] 编写单元测试（覆盖率 > 90%）
- [ ] 运行 `scripts/dev.sh test` 确保通过
- [ ] 运行 `scripts/dev.sh check` 确保代码质量

______________________________________________________________________

## 相关资源

- [beangulp 文档](https://github.com/beancount/beangulp)
- [Beancount 官方文档](https://beancount.readthedocs.io/)
- [项目主文档](index.md)
- [开发脚本说明](SCRIPTS.md)
