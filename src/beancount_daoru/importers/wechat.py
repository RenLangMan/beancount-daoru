"""微信支付导入器实现.

此模块提供了微信支付账单文件的导入器,用于将微信支付交易记录转换为 Beancount 条目。
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


def _split_amount(v: str) -> tuple[str, str]:
    """拆分金额字符串,分离币种符号和数值.

    参数:
        v: 包含币种符号的金额字符串,如 "¥100.00"

    返回:
        (币种符号, 金额数值字符串) 元组
    """
    return v[0], v[1:]


AmountField = Annotated[tuple[str, Decimal], BeforeValidator(_split_amount)]
StrField = Annotated[str | None, AfterValidator(_validate_str)]


Record = TypedDict(
    "Record",
    {
        "交易时间": datetime,
        "交易类型": StrField,
        "交易对方": StrField,
        "商品": StrField,
        "收/支": StrField,
        "金额(元)": AmountField,
        "支付方式": str,
        "当前状态": StrField,
        "备注": StrField,
    },
)


class Parser(BaseParser):
    """微信支付交易记录解析器.

    实现 Parser 协议,将微信支付交易记录转换为 Beancount 兼容的数据结构。
    处理微信支付特定的字段以及确定交易金额和方向的逻辑。
    """

    __validator = TypeAdapter(Record)
    __account_pattern = re.compile(r"微信昵称[:：]\[([^\]]*)\]")
    __date_pattern = re.compile(
        r"终止时间[:：]\[(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}]"
    )

    @property
    @override
    def reversed(self) -> bool:
        """是否需要反转记账方向.

        返回:
            微信支付需要反转记账方向,始终返回 True
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
        return Transaction(
            date=validated["交易时间"].date(),
            extra=Extra(
                time=validated["交易时间"].time(),
                dc=validated["收/支"],
                status=validated["当前状态"],
                type=validated["交易类型"],
                remarks=validated["备注"],
            ),
            payee=validated["交易对方"],
            narration=validated["商品"],
            postings=(*self._parse_postings(validated),),
        )

    def _parse_postings(self, validated: Record) -> Iterator[Posting]:
        """解析记账分录.

        参数:
            validated: 验证后的交易记录

        返回:
            记账分录迭代器

        异常:
            ParserError: 当无法解析交易类型时抛出
        """
        account, amount, counter_party, other_posting = self._parse_simple_postings(
            validated
        )
        currency = validated["金额(元)"][0]

        yield Posting(
            account=account,
            amount=amount,
            currency=currency,
        )

        if counter_party is not None:
            yield Posting(
                account=counter_party,
                amount=-amount,
                currency=currency,
            )

        if other_posting is not None:
            yield other_posting

    def _parse_simple_postings(
        self, validated: Record
    ) -> tuple[str, Decimal, str | None, Posting | None]:
        """解析基础记账分录,处理微信支付的各种交易场景.

        参数:
            validated: 验证后的交易记录

        返回:
            (支付账户, 金额, 对方账户, 额外分录) 元组

        异常:
            ParserError: 当遇到无法识别的交易组合时抛出
        """
        dc_key = "收/支"
        type_key = "交易类型"
        status_key = "当前状态"
        remarks_key = "备注"

        method = validated["支付方式"]
        amount = validated["金额(元)"][1]

        status = validated[status_key]
        if status is not None and status.startswith("已退款"):
            status = "已退款"

        txn_type = validated[type_key]
        if txn_type is not None and txn_type.endswith("-退款"):
            txn_type = "退款"

        match (
            validated[dc_key],
            txn_type,
            status,
            validated[remarks_key],
        ):
            # 普通消费支出
            case (
                (
                    "支出",
                    "商户消费" | "分分捐" | "亲属卡交易",
                    "支付成功" | "已退款" | "已全额退款",
                    _,
                )
                | ("支出", "赞赏码" | "转账", "朋友已收钱", _)
                | ("支出", "扫二维码付款", "已转账", _)
                | ("支出", "转账", "对方已收钱", _)
            ):
                return method, -amount, None, None
            # 收入类交易
            case (
                ("收入", "其他", "已到账", _)
                | ("收入", "商户消费", "充值成功", _)
                | ("收入", "二维码收款", "已收钱", _)
                | ("收入", "微信红包", "已存入零钱", _)
                | (None, "购买理财通" | "信用卡还款", "支付成功", _)
                | ("收入", "退款", "已退款" | "已全额退款", _)
            ):
                return method, amount, None, None
            # 转入零钱通
            case (None, str(x), "支付成功", _) if x.startswith("转入零钱通-来自"):
                return method, -amount, "零钱通", None
            # 零钱通转出
            case (None, str(x), "支付成功", _) if x.startswith("零钱通转出-到"):
                return "零钱通", -amount, x[len("零钱通转出-到") :], None
            # 零钱充值
            case (None, "零钱充值", "充值完成", _):
                return method, -amount, "零钱", None
            # 处理零钱提现(可能包含服务费)  # noqa: ERA001
            case (None, "零钱提现", "提现已到账", str(x)) if x.startswith("服务费"):
                currency_and_amount = x[len("服务费") :]
                return (
                    method,
                    -amount,
                    "零钱",
                    Posting(
                        amount=Decimal(currency_and_amount[1:]),
                        account="零钱提现服务费",
                        currency=currency_and_amount[0],
                    ),
                )
            case _:
                raise ParserError(dc_key, type_key, status_key, remarks_key)


class Importer(BaseImporter):
    """微信支付账单文件导入器.

    使用微信支付解析器实现将微信支付交易记录转换为 Beancount 条目。
    """

    def __init__(self, **kwargs: Unpack[ImporterKwargs]) -> None:
        """初始化微信支付导入器.

        参数:
            **kwargs: 额外的配置参数
        """
        super().__init__(
            re.compile(r"微信支付账单流水文件\(\d{8}-\d{8}\).*\.xlsx"),
            excel.Reader(header=16),
            Parser(),
            **kwargs,
        )
