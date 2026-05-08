"""支付宝导入器实现.

此模块提供了支付宝账单文件的导入器,用于将支付宝交易记录转换为 Beancount 条目。
"""

import csv
import fnmatch
import re
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import chardet
import pyexcel
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
from beancount_daoru.utils import TZ_UTC8, search_patterns


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

    # 支付宝文件匹配模式
    __file_patterns = (
        "支付宝交易明细*.csv",
        "支付宝交易明细*.xlsx",
        "支付宝交易明细*.xls",
        "alipay*.csv",
        "alipay*.xlsx",
        "alipay*.xls",
    )

    # 必需的表头字段
    __required_headers: frozenset[str] = frozenset(
        {"交易时间", "交易对方", "金额", "收/支"}
    )

    @property
    @override
    def reversed(self) -> bool:
        """是否需要反转记账方向.

        返回:
            支付宝需要反转记账方向,始终返回 True
        """
        return True

    @property
    @override
    def file_patterns(self) -> tuple[str, ...]:
        """文件匹配模式.

        返回:
            支持的文件名模式元组
        """
        return self.__file_patterns

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
    def validate_file(self, filepath: str) -> bool:
        """验证文件是否为有效的支付宝账单.

        通过检查文件名和文件内容头部进行验证。

        参数:
            filepath: 文件路径

        返回:
            如果文件有效返回 True,否则返回 False
        """
        path = Path(filepath)

        # 检查文件扩展名
        if path.suffix.lower() not in (".csv", ".xlsx", ".xls"):
            return False

        # 检查文件名是否匹配模式
        filename = path.name
        if not any(
            fnmatch.fnmatch(filename, pattern) for pattern in self.__file_patterns
        ):
            return False

        # 尝试读取文件头部验证内容格式
        try:
            if path.suffix.lower() == ".csv":
                # 检测编码并读取头部
                encoding = self.__detect_encoding(path)
                with path.open(encoding=encoding, newline="") as f:
                    reader = csv.reader(f)
                    headers = next(reader, [])

                # 检查必需字段
                return self.__required_headers.issubset(set(headers))
            # Excel 文件 - 尝试读取表头
            records = list(
                pyexcel.iget_records(
                    file_name=path,
                    start_row=0,
                    row_limit=1,
                    auto_detect_int=False,
                    auto_detect_float=False,
                    auto_detect_datetime=False,
                )
            )
            if not records:
                return False
            headers = set(records[0].keys())
            return self.__required_headers.issubset(headers)

        except (OSError, ValueError, KeyError, zipfile.BadZipFile):
            return False

    @staticmethod
    def __detect_encoding(path: Path) -> str:
        """检测文件编码.

        参数:
            path: 文件路径

        返回:
            检测到的编码,默认为 utf-8
        """
        detected = chardet.detect(path.read_bytes())
        return detected.get("encoding") or "utf-8"

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
        payment_splits = self._extract_payment_splits(validated)
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

        # 获取原始时间字符串
        raw_datetime_str = record.get("交易时间", "")

        # 使用统一时区生成时间戳
        dt = validated["交易时间"]
        # 如果 datetime 对象没有时区信息, 添加 UTC+8 时区
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ_UTC8)
        timestamp = int(dt.timestamp())

        # 提取源文件信息
        source_file = record.get("source_file")
        row_number = record.get("row_number")
        if row_number is not None:
            try:
                row_number = int(row_number)
            except (ValueError, TypeError):
                row_number = None

        return Transaction(
            date=validated["交易时间"].date(),
            extra=Extra(
                time=validated["交易时间"].time(),
                datetime_str=raw_datetime_str or None,
                timestamp=timestamp,
                dc=validated["收/支"],
                status=validated["交易状态"],
                payee_account=validated["对方账号"],
                type=validated["交易分类"],
                remarks=validated["备注"],
                source_file=source_file,
                row_number=row_number,
                payment_splits=payment_splits,
                trade_no=validated.get("交易订单号"),
                amount=abs(Decimal(str(record.get("金额", "0")))),
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

    def _extract_payment_splits(self, record: Record) -> list[dict[str, object]] | None:
        """提取支付拆分信息.

        支付宝组合支付格式示例:
        - 单一支付: "农业银行储蓄卡(6773)"
        - 组合支付: "农业银行储蓄卡(6773)&碰一下立减"
        - 组合支付: "农业银行储蓄卡(6773)&余额&优惠券"

        参数:
            record: 验证后的交易记录

        返回:
            支付拆分列表,如果没有组合支付则返回 None
        """
        payment_method = record.get("收/付款方式", "")
        if not payment_method or "&" not in payment_method:
            return None

        splits: list[dict[str, object]] = []
        parts = payment_method.split("&")

        for idx, original_part in enumerate(parts):
            part = original_part.strip()
            if not part:
                continue

            # 判断是否为优惠类型
            is_discount = any(
                keyword in part
                for keyword in ["立减", "红包", "优惠券", "减免", "折扣"]
            )

            split_info: dict[str, object] = {
                "payment_method": part,
                "split_order": idx,
                "is_discount": is_discount,
            }
            splits.append(split_info)

        # 如果只有一个主要支付方式,不拆分
        main_splits = [s for s in splits if not s.get("is_discount")]
        if len(main_splits) == 1 and len(splits) == 1:
            return None

        return splits if len(splits) > 1 else None


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
            re.compile(r"支付宝交易明细\(\d{8}-\d{8}\)\.csv"),
            excel.Reader(header=24, encoding="gbk"),
            Parser(),
            **kwargs,
        )
