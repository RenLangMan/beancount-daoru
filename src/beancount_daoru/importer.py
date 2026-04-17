"""将提取的记录转换为 Beancount 条目的主导入器模块.

此模块提供了核心导入器功能,作为提取的财务记录与 Beancount 会计系统之间的桥梁。
它负责将记录转换为 Beancount 交易、账户映射、货币转换以及与 Beangulp 框架的集成。
"""

from __future__ import annotations

import contextlib
import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Protocol

import beancount
import beangulp
from beangulp.extract import DUPLICATE
from typing_extensions import TypedDict, Unpack, override

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Mapping
    from re import Pattern

    from beancount_daoru.reader import Reader


class Extra(NamedTuple):
    """交易的额外元数据.

    与金融交易相关联的额外元数据,这些数据不属于交易的标准字段。
    这些字段为分类、对账和报告提供额外的上下文信息。

    属性:
        time: 交易时间。
        dc: 借贷方向标识(例如:"收入"表示收入,"支出"表示支出)。
        type: 交易类型或类别。
        payee_account: 对手方的账户信息。
        status: 交易状态(例如:成功、处理中、失败)。
        place: 交易地点或场所。
        remarks: 关于交易的额外备注或说明。
        datetime_str: 原始日期时间字符串(例如:"2023-02-12 21:32:14")。
        timestamp: Unix 时间戳(秒),用于精确排序同一日期内的多笔交易。
        source_file: 源文件名。
        row_number: 原始文件中的行号。
        payment_splits: 组合支付的拆分信息列表。
        trade_no: 交易订单号(用于跨平台去重)。
        amount: 交易金额。
    """

    time: datetime.time | None = None
    dc: str | None = None
    type: str | None = None
    payee_account: str | None = None
    status: str | None = None
    place: str | None = None
    remarks: str | None = None
    datetime_str: str | None = None
    timestamp: int | None = None
    source_file: str | None = None
    row_number: int | None = None
    payment_splits: list[dict[str, object]] | None = None
    trade_no: str | None = None
    amount: Decimal | None = None


class Posting(NamedTuple):
    """Beancount 交易中的一笔记账分录.

    表示交易中的一个单腿记录,包含金额、账户和可选的货币信息。
    在复式记账中,一笔交易通常由两个或多个金额之和为零的记账分录组成。

    属性:
        amount: 记账分录的货币金额。
        account: 受此记账分录影响的账户。
        currency: 金额的货币类型(可选,可从上下文中推断)。
    """

    amount: Decimal
    account: str | None = None
    currency: str | None = None


class Transaction(NamedTuple):
    """具有 Beancount 兼容结构的金融交易.

    表示一笔完整的金融交易,包含日期、收款方、说明和一个或多个记账分录。
    此结构作为源数据格式与 Beancount 条目之间的中间表示。

    属性:
        date: 交易日期。
        extra: 关于交易的额外元数据。
        payee: 交易对方实体(例如:商家、收款人)。
        narration: 交易的描述或备注。
        postings: 组成此交易的记账分录。
        balance: 用于账户对账的可选余额信息。
    """

    date: datetime.date
    extra: Extra
    payee: str | None = None
    narration: str | None = None
    postings: Iterable[Posting] = ()
    balance: Posting | None = None


class Metadata(NamedTuple):
    """从金融文档中提取的元数据.

    包含源文档的相关信息,如账户标识符和账单周期。
    这些元数据用于正确分类和处理文档中的交易。

    属性:
        account: 从文档中提取的账户标识符。
        date: 与文档关联的日期(通常是账单日期)。
        currency: 文档中交易的默认货币。
    """

    account: str | None
    date: datetime.date | None
    currency: str | None = None


class ParserError(Exception):
    """解析失败时抛出的异常."""

    def __init__(self, *fields: str) -> None:
        """初始化 ParserError 异常.

        参数:
            *fields: 导致解析失败的未支持字段名的元组。
        """
        msg = f"unsupported value combination of fields: {fields!r}"
        super().__init__(msg)


class Parser(Protocol):
    """金融交易记录解析器接口.

    定义了所有解析器实现必须遵循的协议,用于将源交易记录转换为
    Beancount 兼容的数据结构。每个具体的导入器(支付宝、微信等)
    都必须实现此协议。
    """

    @property
    def reversed(self) -> bool:
        """指示源记录是否为逆时间顺序排列.

        返回:
            如果记录为逆时间顺序返回 True,否则返回 False。
        """
        return False

    @property
    def file_patterns(self) -> tuple[str, ...]:
        """文件匹配模式.

        返回:
            支持的文件名模式元组,支持通配符。
        """
        return ()

    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        """从文本迭代器中提取元数据.

        解析输入文本以提取文档级别的元数据,如账户标识符和账单日期。
        这些信息用于正确分类和处理文档中的交易。

        参数:
            texts: 源文档文本行的迭代器。

        返回:
            包含提取信息的元数据对象。
        """
        ...

    def validate_file(self, filepath: str) -> bool:
        """验证文件是否为有效的数据源.

        通过读取文件头部验证文件格式是否符合预期。
        此方法会读取文件的前几行进行验证,不会影响后续的完整读取。

        参数:
            filepath: 文件路径

        返回:
            如果文件有效返回 True,否则返回 False。
        """
        path = Path(filepath)
        # 检查文件扩展名
        return path.suffix.lower() in (".csv", ".xlsx", ".xls")

    def parse(self, record: dict[str, str]) -> Transaction:
        """将单条交易记录解析为 Beancount 兼容结构.

        将源格式中的单条交易记录的字典表示转换为标准化的
        Transaction 对象,该对象可进一步处理为 Beancount 条目。

        参数:
            record: 表示单条交易记录的字典,键和值为源文档中的原始内容。

        异常:
            ParserError: 如果记录包含未支持的值组合。

        返回:
            包含解析后数据的 Transaction 对象,格式与 Beancount 兼容。
        """
        ...


@dataclass(frozen=True)
class BankFieldConfig:
    """银行账单字段配置.

    用于配置不同银行账单文件的字段映射关系。
    """

    # 文件匹配模式
    file_patterns: tuple[str, ...] = ()
    # 文件编码
    encoding: str = "gbk"
    # 表头跳过行数
    header_rows: int = 0

    # 字段名配置
    date_field: str = "交易日期"
    amount_field: str = "交易金额"
    balance_field: str | None = None
    payee_field: str = "对方户名"
    description_field: str | None = None
    channel_field: str | None = None  # 交易渠道
    dc_field: str | None = None  # 借贷标志
    currency_field: str | None = None
    trade_no_field: str | None = None  # 流水号

    # 借贷标志映射 (某些银行用符号表示)  # noqa: ERA001
    dc_mapping: dict[str, str] = field(
        default_factory=lambda: {"借": "支出", "贷": "收入"}
    )


# 常用银行配置预定义
PREDEFINED_BANK_CONFIGS: dict[str, BankFieldConfig] = {}


class ConfigurableParser(ABC):
    """配置驱动的银行账单解析器基类.

    通过 BankFieldConfig 配置支持不同银行的字段映射,
    适用于字段名差异大、需要灵活配置的银行账单。
    """

    # 子类应覆盖此配置
    bank_config: BankFieldConfig | None = None

    @property
    def field_config(self) -> BankFieldConfig:
        """获取字段配置."""
        if self.bank_config is None:
            msg = "子类必须定义 bank_config 属性"
            raise NotImplementedError(msg)
        return self.bank_config

    @property
    def reversed(self) -> bool:
        """记录是否为逆时间顺序."""
        return True

    @property
    def file_patterns(self) -> tuple[str, ...]:
        """文件匹配模式."""
        return self.field_config.file_patterns

    @abstractmethod
    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        """从文本迭代器中提取元数据."""
        ...

    def validate_file(self, filepath: str) -> bool:
        """验证文件是否为有效的银行账单."""
        path = Path(filepath)
        return path.suffix.lower() in (".csv", ".xlsx", ".xls")

    def get_field(self, record: dict[str, str], field_name: str | None) -> str | None:
        """从记录中获取字段值.

        参数:
            record: 交易记录字典
            field_name: 字段名

        返回:
            字段值,如果字段不存在返回 None
        """
        if field_name is None:
            return None
        value = record.get(field_name)
        if isinstance(value, str):
            return value.strip() or None
        return str(value) if value is not None else None

    def get_decimal(
        self, record: dict[str, str], field_name: str | None
    ) -> Decimal | None:
        """从记录中获取金额值.

        参数:
            record: 交易记录字典
            field_name: 字段名

        返回:
            Decimal 金额值,如果无效返回 None
        """
        value = self.get_field(record, field_name)
        if value is None:
            return None
        try:
            return Decimal(value.replace(",", ""))
        except Exception:  # noqa: BLE001
            return None

    def get_date(
        self, record: dict[str, str], field_name: str | None
    ) -> datetime.date | None:
        """从记录中获取日期值.

        参数:
            record: 交易记录字典
            field_name: 字段名

        返回:
            date 对象,如果无效返回 None
        """
        value = self.get_field(record, field_name)
        if value is None:
            return None
        # 尝试多种日期格式
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%d/%m/%Y"):
            with contextlib.suppress(ValueError):
                return datetime.datetime.strptime(value[:10], fmt).date()  # noqa: DTZ007
        return None

    def parse_dc(self, record: dict[str, str]) -> str | None:
        """解析借贷方向.

        参数:
            record: 交易记录字典

        返回:
            "支出" 或 "收入",如果无法确定返回 None
        """
        dc_field = self.field_config.dc_field
        if dc_field is None:
            return None

        dc_value = self.get_field(record, dc_field)
        if dc_value is None:
            return None

        return self.field_config.dc_mapping.get(dc_value)

    def parse_amount(self, record: dict[str, str]) -> tuple[Decimal, str] | None:
        """解析金额和方向.

        参数:
            record: 交易记录字典

        返回:
            (金额, 方向) 元组,如果无效返回 None
        """
        amount = self.get_decimal(record, self.field_config.amount_field)
        if amount is None:
            return None

        dc = self.parse_dc(record)
        if dc == "支出":
            return -abs(amount), dc
        if dc == "收入":
            return abs(amount), dc
        # 默认: 负数为支出,正数为收入
        return (amount, "支出" if amount < 0 else "收入")

    def parse(self, record: dict[str, str]) -> Transaction:
        """解析单条交易记录.

        子类可覆盖此方法以自定义解析逻辑。

        参数:
            record: 原始交易记录字典

        返回:
            转换后的 Transaction 对象
        """
        amount_info = self.parse_amount(record)
        if amount_info is None:
            raise ParserError(self.field_config.amount_field)

        amount, dc = amount_info

        return Transaction(
            date=self.get_date(record, self.field_config.date_field)
            or datetime.date.today(),  # noqa: DTZ011
            extra=Extra(
                dc=dc,
                type=self.get_field(record, self.field_config.channel_field),
                payee_account=self.get_field(record, self.field_config.trade_no_field),
            ),
            payee=self.get_field(record, self.field_config.payee_field),
            narration=self.get_field(record, self.field_config.description_field),
            postings=(
                Posting(
                    amount=abs(amount),
                    currency=self.get_field(record, self.field_config.currency_field),
                ),
            ),
            balance=(
                Posting(
                    amount=self.get_decimal(record, self.field_config.balance_field)
                    or Decimal(0),
                )
                if self.field_config.balance_field
                else None
            ),
        )


class ImporterKwargs(TypedDict):
    """Importer 类的配置参数.

    属性:
        account_mapping: 嵌套字典,将源账户信息和交易类型映射到
            Beancount 账户。结构:
            - 第1级键:源账户名称(例如:支付应用的用户账户)
            - 第2级键:支付方式(例如:"余额"、"花呗")
            - 特殊键 None:该源的默认归档文件夹账户

        示例:
            {
                "user@example.com": {
                    None: "Assets:Alipay",  # 归档文件夹账户
                    "余额": "Assets:Alipay:Balance",
                    "花呗": "Liabilities:Huabei"
                }
            }
            `account_mapping["user@example.com"][None]` 映射到用于归档的
            "Assets/Alipay" 文件夹。

        currency_mapping: 源货币标识符到 Beancount 货币代码的映射
            (例如:{"RMB": "CNY", "USD": "USD"})。
    """

    account_mapping: Mapping[str | None, Mapping[str | None, beancount.Account]]
    currency_mapping: Mapping[str | None, beancount.Currency]


class Importer(beangulp.Importer):
    """与 Beangulp 集成的主导入器类.

    此类实现 Beangulp Importer 接口,并协调将金融文档
    转换为 Beancount 条目的完整流程。
    """

    def __init__(
        self,
        filename: Pattern[str],
        reader: Reader,
        parser: Parser,
        /,
        **kwargs: Unpack[ImporterKwargs],
    ) -> None:
        """初始化导入器.

        设置导入器的文件名模式匹配、用于从文件提取记录的读取器、
        将记录转换为交易的解析器,以及账户和货币转换的映射。

        参数:
            filename: 用于识别文件的文件名匹配模式。
            reader: 用于从文件提取记录的读取器实例。
            parser: 用于将记录转换为交易的解析器实例。
            **kwargs: 额外配置,包括账户和货币映射。
        """
        self.__filename_pattern = filename
        self.__reader = reader
        self.__parser = parser
        self.__account_mappings = kwargs["account_mapping"]
        self.__currency_mapping = kwargs["currency_mapping"]

    @override
    def identify(self, filepath: str) -> bool:
        """识别文件是否由此导入器处理.

        参数:
            filepath: 文件路径

        返回:
            如果文件名匹配模式则返回 True,否则返回 False
        """
        return self.__filename_pattern.fullmatch(Path(filepath).name) is not None

    @override
    def account(self, filepath: str) -> str:
        """返回文件对应的归档账户.

        参数:
            filepath: 文件路径

        返回:
            归档账户名称
        """
        return self._analyse_account(self._cached_metadata(filepath))

    @override
    def date(self, filepath: str) -> datetime.date | None:
        """返回文件对应的日期.

        参数:
            filepath: 文件路径

        返回:
            从文件元数据中提取的日期
        """
        return self._cached_metadata(filepath).date

    @override
    def filename(self, filepath: str) -> str:
        """返回文件名.

        参数:
            filepath: 文件路径

        返回:
            不带路径的文件名
        """
        return Path(filepath).name

    @override
    def extract(
        self,
        filepath: str,
        existing: beancount.Directives,
    ) -> beancount.Directives:
        """从文件中提取 Beancount 条目.

        参数:
            filepath: 文件路径
            existing: 现有的 Beancount 指令(用于去重)

        返回:
            提取的 Beancount 指令列表
        """
        metadata = self._cached_metadata(filepath)
        directives: list[beancount.Directive] = []
        for index, record in enumerate(self.__reader.read_records(Path(filepath))):
            directives.extend(self._extract_record(filepath, index, metadata, record))
        return directives

    @override
    def deduplicate(
        self, entries: beancount.Directives, existing: beancount.Directives
    ) -> None:
        """对条目进行去重处理.

        参数:
            entries: 待去重的条目列表
            existing: 现有的 Beancount 条目
        """
        # 交易去重: 基于 trade_no 和时间戳+金额+账户
        if existing:
            dedup = Deduplicator(timestamp_window=10)
            dedup.load_entries(existing)
            dedup.mark_duplicates(entries)

        # Balance 去重: 同日期保留一条
        balances = sorted(
            (e for e in entries if isinstance(e, beancount.Balance)),
            key=attrgetter("date"),
        )
        max_balance_per_date = {
            date: max(group, key=lambda e: self._lineno_key(e.meta["lineno"]))  # pyright: ignore[reportAny]
            for date, group in groupby(balances, key=attrgetter("date"))  # pyright: ignore[reportAny]
        }

        for balance in balances:
            if (target := max_balance_per_date[balance.date]) != balance:
                balance.meta[DUPLICATE] = target

    @override
    def sort(
        self,
        entries: beancount.Directives,
        reverse: bool = False,
        by_timestamp: bool = False,
    ) -> None:
        """对条目进行排序.

        参数:
            entries: 待排序的条目列表
            reverse: 是否反向排序
            by_timestamp: 是否按日期+时间戳排序(跨文件场景)
        """

        def sort_key(entry: beancount.Directive) -> tuple[int, int]:
            lineno = entry.meta["lineno"]  # pyright: ignore[reportAny]
            if by_timestamp and isinstance(entry, beancount.Transaction):
                # 按日期 + timestamp 排序
                ts = entry.meta.get("timestamp")
                ts_key = ts if ts is not None else 0
                return (entry.date.toordinal(), ts_key)
            return (
                self._lineno_key(lineno),  # pyright: ignore[reportAny]
                0 if isinstance(entry, beancount.Transaction) else 1,
            )

        entries.sort(key=sort_key, reverse=reverse)

    @staticmethod
    def sort_entries_by_timestamp(
        entries: beancount.Directives, *, reverse: bool = False
    ) -> None:
        """对条目按日期+时间戳全局排序(跨文件场景).

        此方法用于多个文件合并后的全局排序,按日期升序,
        同一天内按 timestamp 升序。

        参数:
            entries: 待排序的条目列表
            reverse: 是否反向排序

        示例:
            >>> from beancount_daoru.importer import Importer
            >>> all_entries = []
            >>> for importer in importers:
            ...     all_entries.extend(importer.extract(filepath, []))
            >>> Importer.sort_entries_by_timestamp(all_entries)
        """
        transactions: list[beancount.Transaction] = []
        others: list[beancount.Directive] = []

        for entry in entries:
            if isinstance(entry, beancount.Transaction):
                transactions.append(entry)
            else:
                others.append(entry)

        def tx_key(entry: beancount.Transaction) -> tuple[int, int]:
            ts = entry.meta.get("timestamp")
            try:
                ts_key = int(ts) if ts is not None else 0
            except (ValueError, TypeError):
                ts_key = 0
            return (entry.date.toordinal(), ts_key)

        transactions.sort(key=tx_key, reverse=reverse)
        entries[:] = transactions + others

    def _lineno_key(self, lineno: int) -> int:
        """生成行号排序键.

        参数:
            lineno: 行号

        返回:
            根据解析器的 reversed 属性调整后的排序键
        """
        return -lineno if self.__parser.reversed else lineno

    @lru_cache(maxsize=1)  # noqa: B019
    def _cached_metadata(self, filepath: str) -> Metadata:
        """缓存文件的元数据.

        参数:
            filepath: 文件路径

        返回:
            文件的元数据对象
        """
        return self.__parser.extract_metadata(
            self.__reader.read_captions(Path(filepath))
        )

    def _extract_record(
        self,
        filepath: str,
        lineno: int,
        metadata: Metadata,
        record: dict[str, str],
    ) -> Iterator[beancount.Directive]:
        """提取单条记录并转换为 Beancount 指令.

        参数:
            filepath: 文件路径
            lineno: 行号
            metadata: 文件元数据
            record: 原始记录数据

        返回:
            Beancount 指令迭代器
        """
        try:
            transaction = self.__parser.parse(record)
        except ParserError as e:
            yield beancount.Transaction(
                meta=self._build_meta(
                    filepath,
                    lineno,
                    record,
                    error=f"{e} @ {record!r}",
                ),
                date=datetime.date(1970, 1, 1),
                flag=beancount.FLAG_WARNING,
                payee=None,
                narration=None,
                tags=frozenset(),
                links=frozenset(),
                postings=[],
            )
            return

        yield beancount.Transaction(
            meta=self._build_meta(
                filepath,
                lineno,
                record,
                include_record_fields=True,
                **transaction.extra._asdict(),  # pyright: ignore[reportAny]
            ),
            date=transaction.date,
            flag=beancount.FLAG_OKAY,
            payee=transaction.payee,
            narration=transaction.narration,
            tags=frozenset(),
            links=frozenset(),
            postings=[
                beancount.Posting(
                    account=self._analyse_account(metadata, posting),
                    units=self._analyse_amount(metadata, posting),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                )
                for posting in transaction.postings
            ],
        )

        if transaction.balance is not None:
            yield beancount.Balance(
                meta=self._build_meta(filepath, lineno, record),
                date=transaction.date + datetime.timedelta(days=1),
                account=self._analyse_account(metadata, transaction.balance),
                amount=self._analyse_amount(metadata, transaction.balance),
                tolerance=None,
                diff_amount=None,
            )

    def _build_meta(
        self,
        filepath: str,
        lineno: int,
        record: dict[str, str],
        **meta: object | None,
    ) -> dict[str, str]:
        """构建 Beancount 条目的元数据字典.

        参数:
            filepath: 文件路径
            lineno: 行号
            record: 原始记录
            **meta: 额外的元数据,包含 include_record_fields 和其他元数据

        返回:
            元数据字典
        """
        kvlist: dict[str, str] = {}

        # 提取 include_record_fields 参数
        include_record_fields = meta.pop("include_record_fields", False)

        # 字段名映射: 中文键名 -> 英文/标准键名
        field_mapping: dict[str, str] = {
            # 支付宝
            "交易时间": "datetime",
            "交易分类": "type",
            "交易对方": "payee",
            "对方账号": "payee_account",
            "商品说明": "narration",
            "收/支": "dc",
            "金额": "amount",
            "收/付款方式": "payment_method",
            "交易状态": "status",
            "备注": "remarks",
            "交易订单号": "trade_no",
            "商家订单号": "merchant_no",
            # 京东
            "商户名称": "payee",
            "交易说明": "narration",
            # 微信
            "交易类型": "type",
            "商品": "narration",
            "金额(元)": "amount",
            "支付方式": "payment_method",
            "当前状态": "status",
            "商户单号": "merchant_no",
            # 美团
            "交易成功时间": "datetime",
            "交易创建时间": "datetime_created",
            "订单标题": "narration",
            "订单金额": "order_amount",
            "实付金额": "actual_amount",
            "交易单号": "trade_no",
            "商家单号": "merchant_no",
        }

        excluded_fields: set[str] = {"payee", "narration", "time"}

        # 添加原始记录的每个字段作为独立的元数据行
        if include_record_fields:
            for key, value in record.items():
                if value is not None and str(value).strip():
                    mapped_key = field_mapping.get(key, key)
                    if mapped_key not in excluded_fields:
                        kvlist[mapped_key] = str(value)

        # 添加额外元数据
        for key, value in meta.items():
            if value is not None and key not in excluded_fields:
                kvlist[key] = str(value)

        kvlist["source"] = Path(filepath).name

        # 按键名字母排序元数据, 确保输出顺序一致
        sorted_kvlist = dict(sorted(kvlist.items()))

        return beancount.new_metadata(
            self.filename(filepath), lineno, kvlist=sorted_kvlist
        )

    def _analyse_account(
        self,
        metadata: Metadata,
        posting: Posting | None = None,
    ) -> beancount.Account:
        """分析并映射账户名称.

        参数:
            metadata: 文件元数据
            posting: 记账分录(可选)

        返回:
            映射后的 Beancount 账户

        异常:
            KeyError: 当账户未配置映射时抛出
        """
        if metadata.account not in self.__account_mappings:
            msg = f"account is not mapped: {metadata.account!r}"
            raise KeyError(msg)
        account_submapping = self.__account_mappings[metadata.account]

        posting_account = posting.account if posting is not None else None
        if posting_account not in account_submapping:
            msg = f"account of {metadata.account!r} is not mapped: {posting_account!r}"
            raise KeyError(msg)
        return account_submapping[posting_account]

    def _analyse_amount(self, metadata: Metadata, posting: Posting) -> beancount.Amount:
        """分析并转换金额和货币.

        参数:
            metadata: 文件元数据
            posting: 记账分录

        返回:
            Beancount 金额对象

        异常:
            KeyError: 当货币未配置映射时抛出
        """
        currency_name = posting.currency
        if currency_name is None:
            currency_name = metadata.currency

        if currency_name not in self.__currency_mapping:
            msg = f"currency name '{currency_name}' is not mapped"
            raise KeyError(msg)
        currency = self.__currency_mapping[currency_name]
        return beancount.Amount(number=posting.amount, currency=currency)


class Deduplicator:
    """跨平台交易去重器.

    用于检测新导入的交易是否与现有交易重复,
    支持 trade_no 精确匹配和时间戳+金额+账户模糊匹配。
    """

    AMOUNT_TOLERANCE = 0.01

    def __init__(self, timestamp_window: int = 10) -> None:
        """初始化去重器.

        参数:
            timestamp_window: 时间戳窗口(秒),默认10秒
        """
        self.timestamp_window = timestamp_window
        self._existing: list[dict[str, object]] = []

    def load_entries(self, entries: beancount.Directives) -> None:
        """加载已有的 Beancount 条目.

        参数:
            entries: 现有的 Beancount 条目列表
        """
        self._existing = []
        for entry in entries:
            if isinstance(entry, beancount.Transaction):
                tx_info = self._extract_transaction_info(entry)
                if tx_info:
                    self._existing.append(tx_info)

    def _extract_transaction_info(
        self, entry: beancount.Transaction
    ) -> dict[str, object] | None:
        """从交易条目中提取去重所需的信息.

        参数:
            entry: Beancount 交易条目

        返回:
            包含去重信息的字典,失败返回 None
        """
        meta = entry.meta
        timestamp = meta.get("timestamp")
        trade_no = meta.get("trade_no")
        payee_account = meta.get("payee_account")
        amount_str = meta.get("amount")

        amount: float | None = None
        if amount_str:
            with contextlib.suppress(ValueError, TypeError):
                amount = float(str(amount_str).strip('"'))

        return {
            "date": entry.date,
            "timestamp": timestamp,
            "trade_no": trade_no,
            "payee_account": payee_account,
            "amount": amount,
        }

    def _parse_meta(
        self, entry: beancount.Transaction
    ) -> tuple[str | None, int | None, str | None, float | None]:
        """解析交易元数据.

        返回:
            (trade_no, timestamp, payee_account, amount) 元组
        """
        meta = entry.meta
        trade_no = meta.get("trade_no")
        timestamp_str = meta.get("timestamp")
        payee_account = meta.get("payee_account")
        amount_str = meta.get("amount")

        amount: float | None = None
        if amount_str:
            with contextlib.suppress(ValueError, TypeError):
                amount = float(str(amount_str).strip('"'))

        timestamp: int | None = None
        if timestamp_str:
            with contextlib.suppress(ValueError, TypeError):
                timestamp = int(timestamp_str)

        return trade_no, timestamp, payee_account, amount

    def _match_by_trade_no(self, trade_no: str | None) -> tuple[bool, str]:
        """通过 trade_no 精确匹配."""
        if not (trade_no and str(trade_no).strip() not in ("", "/")):
            return False, ""
        for existing in self._existing:
            if existing.get("trade_no") == trade_no:
                return True, f"trade_no: {trade_no}"
        return False, ""

    def _match_by_timestamp(
        self, timestamp: int, amount: float, payee_account: str | None
    ) -> tuple[bool, str]:
        """通过时间戳+金额+账户模糊匹配."""
        for existing in self._existing:
            existing_ts = existing.get("timestamp")
            if existing_ts is None:
                continue
            ts_diff = abs(int(existing_ts) - timestamp)  # type: ignore[arg-type]
            if ts_diff > self.timestamp_window:
                continue
            existing_amount = existing.get("amount")
            if (
                existing_amount is not None
                and abs(existing_amount - amount) < self.AMOUNT_TOLERANCE  # type: ignore[arg-type]
                and existing.get("payee_account") == payee_account
            ):
                return True, f"时间戳差{ts_diff}秒, 金额{amount}"
        return False, ""

    def is_duplicate(self, entry: beancount.Transaction) -> tuple[bool, str]:
        """检查交易是否与已有交易重复."""
        trade_no, timestamp, payee_account, amount = self._parse_meta(entry)

        # 1. trade_no 完全匹配(最可靠)
        is_dup, reason = self._match_by_trade_no(trade_no)
        if is_dup:
            return True, reason

        # 2. 时间戳在窗口内 + 金额 + 账户匹配
        if timestamp is not None and amount is not None:
            is_dup, reason = self._match_by_timestamp(timestamp, amount, payee_account)
            if is_dup:
                return True, reason

        return False, ""

    def mark_duplicates(self, entries: beancount.Directives) -> int:
        """标记重复交易.

        参数:
            entries: 待检查的 Beancount 条目列表

        返回:
            标记的重复交易数量
        """
        count = 0
        for entry in entries:
            if isinstance(entry, beancount.Transaction):
                is_dup, reason = self.is_duplicate(entry)
                if is_dup:
                    entry.meta[DUPLICATE] = reason
                    count += 1
        return count
