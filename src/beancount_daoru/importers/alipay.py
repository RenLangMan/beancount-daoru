"""支付宝导入器实现.

此模块提供了支付宝账单文件的导入器,用于将支付宝交易记录转换为 Beancount 条目。
"""

import re
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, TypeAdapter
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
    """验证并清理字符串值.

    参数:
        v: 待验证的字符串

    返回:
        如果值为空或斜杠则返回 None,否则返回原值
    """
    if v is None:
        return None
    if v in ("", "/"):
        return None
    return v


StrField = Annotated[str | None, AfterValidator(_validate_str)]


Record = TypedDict(
    "Record",
    {
        "交易时间": datetime,
        "交易分类": StrField,
        "交易对方": StrField,
        "对方账号": StrField,
        "商品说明": StrField,
        "收/支": StrField,
        "金额": Decimal,
        "收/付款方式": str,
        "交易状态": StrField,
        "备注": StrField,
    },
)


class Parser(BaseParser):
    """支付宝交易记录解析器.

    实现 Parser 协议,将支付宝交易记录转换为 Beancount 兼容的数据结构。
    处理支付宝特定的字段以及确定交易金额和方向的逻辑。
    """

    __validator = TypeAdapter(Record)
    __account_pattern = re.compile(r"支付宝账户[:：](\S+)")
    __date_pattern = re.compile(
        r"终止时间[:：]\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}]"
    )

    @property
    @override
    def reversed(self) -> bool:
        """是否需要反转记账方向.

        返回:
            支付宝需要反转记账方向,始终返回 True
        """
        return True

    @override
    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        """从文本中提取元数据.

        参数:
            texts: 文本行迭代器

        返回:
            包含账户和日期的元数据对象

        异常:
            ValueError: 当无法提取账户或日期信息时抛出
        """
        account_matches, date_matches = search_patterns(
            texts, self.__account_pattern, self.__date_pattern
        )

        # 提取账户信息, 处理空迭代器情况
        account_match = next(account_matches, None)
        if account_match is None:
            msg = "无法从文件中提取账户信息, 请检查文件格式"
            raise ValueError(msg)

        # 提取日期信息, 处理空迭代器情况
        date_match = next(date_matches, None)
        if date_match is None:
            msg = "无法从文件中提取日期信息, 请检查文件格式"
            raise ValueError(msg)

        return Metadata(
            account=account_match.group(1),
            date=date.fromisoformat(date_match.group(1)),
        )

    @override
    def parse(self, record: dict[str, str]) -> Transaction:
        """解析单条交易记录.

        参数:
            record: 原始交易记录字典

        返回:
            转换后的 Beancount 交易对象

        异常:
            ParserError: 当无法识别交易类型时抛出
        """
        validated = self.__validator.validate_python(record)
        postings = ()
        if amount_and_payee := self._parse_amount(validated):
            amount, payee = amount_and_payee
            postings += (
                Posting(
                    account=validated["收/付款方式"],
                    amount=amount,
                ),
            )
            if payee is not None:
                postings += (
                    Posting(
                        account=payee,
                        amount=-amount,
                    ),
                )
        return Transaction(
            date=validated["交易时间"].date(),
            extra=Extra(
                time=validated["交易时间"].time(),
                dc=validated["收/支"],
                status=validated["交易状态"],
                payee_account=validated["对方账号"],
                type=validated["交易分类"],
                remarks=validated["备注"],
            ),
            payee=validated["交易对方"],
            narration=validated["商品说明"],
            postings=postings,
        )

    def _parse_amount(  # noqa: PLR0911
        self, validated: Record
    ) -> tuple[Decimal, str | None] | None:
        """解析交易金额和方向.

        根据收支类型和交易状态判断金额的正负号以及是否生成对手方记账。

        参数:
            validated: 验证后的交易记录

        返回:
            (金额, 对手方账户) 元组,如果无需生成记账则返回 None

        异常:
            ParserError: 当遇到无法识别的交易组合时抛出
        """
        dc_key = "收/支"
        status_key = "交易状态"
        desc_key = "商品说明"
        amount = validated["金额"]
        match (validated[dc_key], validated[status_key]):
            case ("支出", "交易成功" | "等待确认收货" | "交易关闭"):
                return -amount, None
            case ("收入" | "不计收支", "交易关闭"):
                return None
            case ("收入", "交易成功") | ("不计收支", "退款成功"):
                return amount, None
            case ("不计收支", "交易成功"):
                match validated[desc_key]:
                    case "提现-实时提现":
                        return amount, None
                    case "余额宝-更换货基转入":
                        return amount, None
                    case (
                        "余额宝-单次转入"
                        | "余额宝-安心自动充-自动攒入"
                        | "余额宝-自动转入"
                    ):
                        return -amount, "余额宝"
                    case str(x) if x.startswith("余额宝-") and x.endswith("-收益发放"):
                        return amount, None
                    case _:
                        raise ParserError(dc_key, status_key, desc_key)
            case _:
                raise ParserError(dc_key, status_key)


class Importer(BaseImporter):
    """支付宝账单文件导入器.

    使用支付宝解析器实现将支付宝交易记录转换为 Beancount 条目。
    """

    def __init__(self, **kwargs: Unpack[ImporterKwargs]) -> None:
        """初始化支付宝导入器.

        参数:
            **kwargs: 额外的配置参数
        """
        super().__init__(
            re.compile(r"支付宝交易明细\(\d{8}-\d{8}\).csv"),
            excel.Reader(header=24, encoding="gbk"),
            Parser(),
            **kwargs,
        )
