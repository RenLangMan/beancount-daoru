"""交通银行（BCM）导入器实现。

此模块提供了交通银行账单文件的导入器，用于将交通银行交易记录转换为 Beancount 条目。
"""

import re
from collections.abc import Iterator
from datetime import date, time
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, TypeAdapter
from typing_extensions import TypedDict, Unpack, override

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
from beancount_daoru.readers import pdf_table
from beancount_daoru.utils import search_patterns


def _amount_validator(v: str) -> Decimal:
    """验证并转换金额字符串为 Decimal 类型。

    参数：
        v: 金额字符串

    返回：
        转换后的 Decimal 金额值
    """
    return Decimal(v.replace(",", ""))


def _validate_str(v: str | None) -> str | None:
    """验证并清理字符串值。

    参数：
        v: 待验证的字符串

    返回：
        如果值为空则返回 None，否则返回清理后的值
    """
    if v is None:
        return None
    return v.replace("\n", "") or None


DecimalField = Annotated[Decimal, BeforeValidator(_amount_validator)]
StrField = Annotated[str | None, AfterValidator(_validate_str)]


Record = TypedDict(
    "Record",
    {
        "Trans Date\n交易日期": date,
        "Trans Time\n交易时间": time,
        "Trading Type\n交易类型": StrField,
        "Dc Flg\n借贷": StrField,
        "Trans Amt\n交易金额": DecimalField,
        "Balance\n余额": DecimalField,
        "Payment Receipt\nAccount\n对方账号": StrField,
        "Payment Receipt\nAccount Name\n对方户名": StrField,
        "Trading Place\n交易地点": StrField,
        "Abstract\n摘要": StrField,
    },
)


class Parser(BaseParser):
    """交通银行交易记录解析器。

    实现 Parser 协议，将交通银行交易记录转换为 Beancount 兼容的数据结构。
    处理交通银行特定的字段以及确定交易金额和方向的逻辑。
    """

    __validator = TypeAdapter(Record)
    __account_pattern = re.compile(r"账号/卡号Account/Card No:\s*(\d{19})\s*")
    __date_pattern = re.compile(r"查询止日Query Ending Date:\s*(\d{4}-\d{2}-\d{2})\s*")
    __currency_pattern = re.compile(r"币种Currency:\s*(\w+)\s*")

    @property
    @override
    def reversed(self) -> bool:
        """是否需要反转记账方向。

        返回：
            交通银行需要反转记账方向，始终返回 True
        """
        return True

    @override
    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        """从文本中提取元数据。

        参数：
            texts: 文本行迭代器

        返回：
            包含账户、日期和币种的元数据对象
        """
        account_matches, date_matches, currency_matches = search_patterns(
            texts, self.__account_pattern, self.__date_pattern, self.__currency_pattern
        )
        return Metadata(
            account=next(account_matches).group(1),
            date=date.fromisoformat(next(date_matches).group(1)),
            currency=next(currency_matches).group(1),
        )

    @override
    def parse(self, record: dict[str, str]) -> Transaction:
        """解析单条交易记录。

        参数：
            record: 原始交易记录字典

        返回：
            转换后的 Beancount 交易对象
        """
        validated = self.__validator.validate_python(record)
        return Transaction(
            date=validated["Trans Date\n交易日期"],
            extra=Extra(
                time=validated["Trans Time\n交易时间"],
                dc=validated["Dc Flg\n借贷"],
                type=validated["Trading Type\n交易类型"],
                payee_account=validated["Payment Receipt\nAccount\n对方账号"],
                place=validated["Trading Place\n交易地点"],
            ),
            payee=validated["Payment Receipt\nAccount Name\n对方户名"],
            narration=validated["Abstract\n摘要"],
            postings=(
                Posting(
                    amount=self._parse_amount(validated),
                ),
            ),
            balance=Posting(
                amount=validated["Balance\n余额"],
            ),
        )

    def _parse_amount(self, validated: Record) -> Decimal:
        """解析交易金额和方向。

        根据借贷标志判断金额的正负号。

        参数：
            validated: 验证后的交易记录

        返回：
            带正负号的金额值

        异常：
            ParserError: 当遇到无法识别的借贷标志时抛出
        """
        dc_key = "Dc Flg\n借贷"
        match validated[dc_key]:
            case "借 Dr":
                return -validated["Trans Amt\n交易金额"]
            case "贷 Cr":
                return validated["Trans Amt\n交易金额"]
            case _:
                raise ParserError(dc_key)


class Importer(BaseImporter):
    """交通银行账单文件导入器。

    使用交通银行解析器实现将交通银行交易记录转换为 Beancount 条目。
    """

    def __init__(self, **kwargs: Unpack[ImporterKwargs]) -> None:
        """初始化交通银行导入器。

        参数：
            **kwargs: 额外的配置参数
        """
        super().__init__(
            re.compile(r"交通银行交易流水\(申请时间[^)]*\).pdf"),
            pdf_table.Reader(table_bbox=(0, 148, 842, 491)),
            Parser(),
            **kwargs,
        )
