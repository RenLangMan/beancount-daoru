"""美团导入器实现。

此模块提供了美团账单文件的导入器，用于将美团交易记录转换为 Beancount 条目。
"""

import re
from collections.abc import Iterator
from datetime import date, datetime
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
from beancount_daoru.readers import excel
from beancount_daoru.utils import search_patterns


def _validate_str(v: str | None) -> str | None:
    """验证并清理字符串值。

    参数：
        v: 待验证的字符串

    返回：
        如果值为空或斜杠则返回 None，否则返回原值
    """
    if v is None:
        return None
    if v in ("", "/"):
        return None
    return v


def _split_amount(v: str) -> tuple[str, str]:
    """拆分金额字符串，分离币种符号和数值。

    参数：
        v: 包含币种符号的金额字符串，如 "¥100.00"

    返回：
        (币种符号, 金额数值字符串) 元组
    """
    return v[0], v[1:]


AmountField = Annotated[tuple[str, Decimal], BeforeValidator(_split_amount)]
StrField = Annotated[str | None, AfterValidator(_validate_str)]


Record = TypedDict(
    "Record",
    {
        "交易成功时间": datetime,
        "交易类型": StrField,
        "订单标题": StrField,
        "收/支": StrField,
        "实付金额": AmountField,
        "支付方式": str,
        "备注": StrField,
    },
)


class Parser(BaseParser):
    """美团交易记录解析器。

    实现 Parser 协议，将美团交易记录转换为 Beancount 兼容的数据结构。
    处理美团特定的字段以及确定交易金额和方向的逻辑。
    """

    __validator = TypeAdapter(Record)
    __account_pattern = re.compile(r"美团用户名：\[([^\]]*)\]")  # noqa: RUF001
    __date_pattern = re.compile(r"终止时间：\[(\d{4}-\d{2}-\d{2})\]")  # noqa: RUF001

    @property
    @override
    def reversed(self) -> bool:
        """是否需要反转记账方向。

        返回：
            美团需要反转记账方向，始终返回 True
        """
        return True

    @override
    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        """从文本中提取元数据。

        参数：
            texts: 文本行迭代器

        返回：
            包含账户和日期的元数据对象
        """
        account_matches, date_matches = search_patterns(
            texts, self.__account_pattern, self.__date_pattern
        )
        return Metadata(
            account=next(account_matches).group(1),
            date=date.fromisoformat(next(date_matches).group(1)),
        )

    @override
    def parse(self, record: dict[str, str]) -> Transaction:
        """解析单条交易记录。

        参数：
            record: 原始交易记录字典

        返回：
            转换后的 Beancount 交易对象

        异常：
            ParserError: 当无法识别交易类型或收支类型时抛出
        """
        validated = self.__validator.validate_python(record)
        return Transaction(
            date=validated["交易成功时间"].date(),
            extra=Extra(
                time=validated["交易成功时间"].time(),
                dc=validated["收/支"],
                type=validated["交易类型"],
                remarks=validated["备注"],
            ),
            payee="美团",
            narration=validated["订单标题"],
            postings=(*self._parse_postings(validated),),
        )

    def _parse_postings(self, validated: Record) -> Iterator[Posting]:
        """解析记账分录。

        参数：
            validated: 验证后的交易记录

        返回：
            记账分录迭代器

        异常：
            ParserError: 当无法解析对方账户时抛出
        """
        amount = self._parse_amount(validated)
        currency = validated["实付金额"][0]

        yield Posting(
            account=validated["支付方式"],
            amount=amount,
            currency=currency,
        )

        counter_party = self._parse_counter_party(validated)
        if counter_party is not None:
            yield Posting(
                account=counter_party,
                amount=-amount,
                currency=currency,
            )

    def _parse_amount(self, validated: Record) -> Decimal:
        """解析交易金额和方向。

        根据收支类型判断金额的正负号。

        参数：
            validated: 验证后的交易记录

        返回：
            带正负号的金额值

        异常：
            ParserError: 当遇到无法识别的收支类型时抛出
        """
        dc_key = "收/支"

        match validated[dc_key]:
            case "支出":
                return -validated["实付金额"][1]
            case "收入":
                return validated["实付金额"][1]
            case _:
                raise ParserError(dc_key)

    def _parse_counter_party(self, validated: Record) -> str | None:
        """解析对方账户。

        根据交易类型和订单标题判断对方账户。

        参数：
            validated: 验证后的交易记录

        返回：
            对方账户名称，如果无对方账户则返回 None

        异常：
            ParserError: 当遇到无法识别的交易组合时抛出
        """
        type_key = "交易类型"
        narration_key = "订单标题"

        match (validated[type_key], validated[narration_key]):
            case ("还款", str(x)) if x.startswith("【美团月付】主动还款"):
                return "美团月付"
            case ("支付" | "退款", _):
                return None
            case _:
                raise ParserError(type_key, narration_key)


class Importer(BaseImporter):
    """美团账单文件导入器。

    使用美团解析器实现将美团交易记录转换为 Beancount 条目。
    """

    def __init__(self, **kwargs: Unpack[ImporterKwargs]) -> None:
        """初始化美团导入器。

        参数：
            **kwargs: 额外的配置参数
        """
        super().__init__(
            re.compile(r"美团账单\(\d{8}-\d{8}\)\.csv"),
            excel.Reader(header=19, encoding="utf-8-sig"),
            Parser(),
            **kwargs,
        )
