"""京东（JD.com）导入器实现。

此模块提供了京东账单文件的导入器，用于将京东交易记录转换为 Beancount 条目。
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

_STATUS_PATTERN = re.compile(r"\(.*\)")


def _validate_amount(v: str) -> str:
    """验证并清理金额字符串，移除状态标记。

    参数：
        v: 金额字符串

    返回：
        移除括号内状态标记后的金额字符串
    """
    return _STATUS_PATTERN.sub("", v)


def _empty_to_none(v: object | None) -> object:
    """将空字符串转换为 None。

    参数：
        v: 待转换的值

    返回：
        如果值为空字符串则返回 None，否则返回原值
    """
    if v == "":
        return None
    return v


DecimalField = Annotated[Decimal, BeforeValidator(_validate_amount)]
StrField = Annotated[str | None, AfterValidator(_empty_to_none)]


Record = TypedDict(
    "Record",
    {
        "交易时间": datetime,
        "商户名称": StrField,
        "交易说明": StrField,
        "金额": DecimalField,
        "收/付款方式": str,
        "交易状态": StrField,
        "收/支": StrField,
        "交易分类": StrField,
        "备注": StrField,
    },
)


class Parser(BaseParser):
    """京东交易记录解析器。

    实现 Parser 协议，将京东交易记录转换为 Beancount 兼容的数据结构。
    处理京东特定的字段以及确定交易金额和方向的逻辑。
    """

    __validator = TypeAdapter(Record)
    __account_pattern = re.compile(r"京东账号名：(\S+)")  # noqa: RUF001
    __date_pattern = re.compile(r"日期区间：\d{4}-\d{2}-\d{2} 至 (\d{4}-\d{2}-\d{2})")  # noqa: RUF001

    @property
    @override
    def reversed(self) -> bool:
        """是否需要反转记账方向。

        返回：
            京东需要反转记账方向，始终返回 True
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
            ParserError: 当无法识别交易类型时抛出
        """
        validated = self.__validator.validate_python(record)
        return Transaction(
            date=validated["交易时间"].date(),
            extra=Extra(
                time=validated["交易时间"].time(),
                dc=validated["收/支"],
                status=validated["交易状态"],
                type=validated["交易分类"],
                remarks=validated["备注"],
            ),
            payee=validated["商户名称"],
            narration=validated["交易说明"],
            postings=(
                Posting(
                    account=validated["收/付款方式"],
                    amount=self._parse_amount(validated),
                ),
            ),
        )

    def _parse_amount(self, validated: Record) -> Decimal:
        """解析交易金额和方向。

        根据收支类型和交易状态判断金额的正负号。

        参数：
            validated: 验证后的交易记录

        返回：
            带正负号的金额值

        异常：
            ParserError: 当遇到无法识别的交易组合时抛出
        """
        dc_key = "收/支"
        status_key = "交易状态"
        match (validated[dc_key], validated[status_key]):
            case ("支出" | "不计收支", "交易成功"):
                return -validated["金额"]
            case ("不计收支", "退款成功"):
                return validated["金额"]
            case _:
                raise ParserError(dc_key, status_key)


class Importer(BaseImporter):
    """京东账单文件导入器。

    使用京东解析器实现将京东交易记录转换为 Beancount 条目。
    """

    def __init__(self, **kwargs: Unpack[ImporterKwargs]) -> None:
        """初始化京东导入器。

        参数：
            **kwargs: 额外的配置参数
        """
        super().__init__(
            re.compile(r"京东交易流水\(申请时间[^)]*\)_\d+\.csv"),
            excel.Reader(header=21, encoding="utf-8-sig"),
            Parser(),
            **kwargs,
        )
