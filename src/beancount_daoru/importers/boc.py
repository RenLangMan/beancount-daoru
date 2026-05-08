"""中国银行(BOC)导入器实现.

此模块提供了中国银行账单文件的导入器,用于将中国银行交易记录转换为 Beancount 条目。
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
    Posting,
    Transaction,
)
from beancount_daoru.importer import Importer as BaseImporter
from beancount_daoru.importer import Parser as BaseParser
from beancount_daoru.readers import pdf_table
from beancount_daoru.utils import search_patterns


def _amount_validator(v: str) -> Decimal:
    """验证并转换金额字符串为 Decimal 类型.

    参数:
        v: 金额字符串

    返回:
        转换后的 Decimal 金额值
    """
    return Decimal(v.replace(",", ""))


def _validate_str(v: str | None) -> str | None:
    """验证并清理字符串值.

    参数:
        v: 待验证的字符串

    返回:
        如果值为空或全为连字符则返回 None,否则返回清理后的值
    """
    if v is None:
        return None
    v = v.replace("\n", "")
    if all(x == "-" for x in v):
        return None
    return v


DecimalField = Annotated[Decimal, BeforeValidator(_amount_validator)]
StrField = Annotated[str | None, AfterValidator(_validate_str)]


Record = TypedDict(
    "Record",
    {
        "记账日期": date,
        "记账时间": time,
        "币别": str,
        "金额": DecimalField,
        "余额": DecimalField,
        "交易名称": StrField,
        "渠道": StrField,
        "附言": StrField,
        "对方账户名": StrField,
        "对方卡号/账号": StrField,
    },
)


class Parser(BaseParser):
    """中国银行交易记录解析器.

    实现 Parser 协议,将中国银行交易记录转换为 Beancount 兼容的数据结构。
    处理中国银行特定的字段以及确定交易金额和方向的逻辑。
    """

    __validator = TypeAdapter(Record)
    __account_pattern = re.compile(r"借记卡号[:：]\s+(\d{19})\s+")
    __date_pattern = re.compile(
        r"交易区间[:：]\s*\d{4}-\d{2}-\d{2}\s*至\s*(\d{4}-\d{2}-\d{2})"
    )

    @property
    @override
    def reversed(self) -> bool:
        """是否需要反转记账方向.

        返回:
            中国银行需要反转记账方向,始终返回 True
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
        """
        validated = self.__validator.validate_python(record)
        return Transaction(
            date=validated["记账日期"],
            extra=Extra(
                time=validated["记账时间"],
                type=validated["交易名称"],
                payee_account=validated["对方卡号/账号"],
                place=validated["渠道"],
            ),
            payee=validated["对方账户名"],
            narration=validated["附言"],
            postings=(
                Posting(
                    amount=validated["金额"],
                    currency=validated["币别"],
                ),
            ),
            balance=Posting(
                amount=validated["余额"],
                currency=validated["币别"],
            ),
        )


class Importer(BaseImporter):
    """中国银行账单文件导入器.

    使用中国银行解析器实现将中国银行交易记录转换为 Beancount 条目。
    """

    def __init__(self, **kwargs: Unpack[ImporterKwargs]) -> None:
        """初始化中国银行导入器.

        参数:
            **kwargs: 额外的配置参数
        """
        super().__init__(
            re.compile(r"交易流水明细\d{14}\.pdf"),
            pdf_table.Reader(table_bbox=(0, 125, 842, 420)),
            Parser(),
            **kwargs,
        )
