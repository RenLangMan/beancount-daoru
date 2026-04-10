"""将提取的记录转换为 Beancount 条目的主导入器模块。

此模块提供了核心导入器功能，作为提取的财务记录与 Beancount 会计系统之间的桥梁。
它负责将记录转换为 Beancount 交易、账户映射、货币转换以及与 Beangulp 框架的集成。
"""

import datetime
from collections.abc import Iterable, Iterator, Mapping
from decimal import Decimal
from functools import lru_cache
from itertools import groupby
from operator import attrgetter
from pathlib import Path
from re import Pattern
from typing import NamedTuple, Protocol

import beancount
import beangulp
from beangulp.extract import DUPLICATE
from typing_extensions import TypedDict, Unpack, override

from beancount_daoru.reader import Reader


class Extra(NamedTuple):
    """交易的额外元数据。

    与金融交易相关联的额外元数据，这些数据不属于交易的标准字段。
    这些字段为分类、对账和报告提供额外的上下文信息。

    属性：
        time: 交易时间。
        dc: 借贷方向标识（例如："收入"表示收入，"支出"表示支出）。
        type: 交易类型或类别。
        payee_account: 对手方的账户信息。
        status: 交易状态（例如：成功、处理中、失败）。
        place: 交易地点或场所。
        remarks: 关于交易的额外备注或说明。
    """

    time: datetime.time | None = None
    dc: str | None = None
    type: str | None = None
    payee_account: str | None = None
    status: str | None = None
    place: str | None = None
    remarks: str | None = None


class Posting(NamedTuple):
    """Beancount 交易中的一笔记账分录。

    表示交易中的一个单腿记录，包含金额、账户和可选的货币信息。
    在复式记账中，一笔交易通常由两个或多个金额之和为零的记账分录组成。

    属性：
        amount: 记账分录的货币金额。
        account: 受此记账分录影响的账户。
        currency: 金额的货币类型（可选，可从上下文中推断）。
    """

    amount: Decimal
    account: str | None = None
    currency: str | None = None


class Transaction(NamedTuple):
    """具有 Beancount 兼容结构的金融交易。

    表示一笔完整的金融交易，包含日期、收款方、说明和一个或多个记账分录。
    此结构作为源数据格式与 Beancount 条目之间的中间表示。

    属性：
        date: 交易日期。
        extra: 关于交易的额外元数据。
        payee: 交易对方实体（例如：商家、收款人）。
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
    """从金融文档中提取的元数据。

    包含源文档的相关信息，如账户标识符和账单周期。
    这些元数据用于正确分类和处理文档中的交易。

    属性：
        account: 从文档中提取的账户标识符。
        date: 与文档关联的日期（通常是账单日期）。
        currency: 文档中交易的默认货币。
    """

    account: str | None
    date: datetime.date | None
    currency: str | None = None


class ParserError(Exception):
    """解析失败时抛出的异常。"""

    def __init__(self, *fields: str) -> None:
        """初始化 ParserError 异常。

        参数：
            *fields: 导致解析失败的未支持字段名的元组。
        """
        msg = f"unsupported value combination of fields: {fields!r}"
        super().__init__(msg)


class Parser(Protocol):
    """金融交易记录解析器接口。

    定义了所有解析器实现必须遵循的协议，用于将源交易记录转换为
    Beancount 兼容的数据结构。每个具体的导入器（支付宝、微信等）
    都必须实现此协议。
    """

    @property
    def reversed(self) -> bool:
        """指示源记录是否为逆时间顺序排列。

        返回：
            如果记录为逆时间顺序返回 True，否则返回 False。
        """
        return False

    def extract_metadata(self, texts: Iterator[str]) -> Metadata:
        """从文本迭代器中提取元数据。

        解析输入文本以提取文档级别的元数据，如账户标识符和账单日期。
        这些信息用于正确分类和处理文档中的交易。

        参数：
            texts: 源文档文本行的迭代器。

        返回：
            包含提取信息的元数据对象。
        """
        ...

    def parse(self, record: dict[str, str]) -> Transaction:
        """将单条交易记录解析为 Beancount 兼容结构。

        将源格式中的单条交易记录的字典表示转换为标准化的
        Transaction 对象，该对象可进一步处理为 Beancount 条目。

        参数：
            record: 表示单条交易记录的字典，键和值为源文档中的原始内容。

        异常：
            ParserError: 如果记录包含未支持的值组合。

        返回：
            包含解析后数据的 Transaction 对象，格式与 Beancount 兼容。
        """
        ...


class ImporterKwargs(TypedDict):
    """Importer 类的配置参数。

    属性：
        account_mapping: 嵌套字典，将源账户信息和交易类型映射到
            Beancount 账户。结构：
            - 第1级键：源账户名称（例如：支付应用的用户账户）
            - 第2级键：支付方式（例如："余额"、"花呗"）
            - 特殊键 None：该源的默认归档文件夹账户

        示例：
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
            （例如：{"RMB": "CNY", "USD": "USD"}）。
    """

    account_mapping: Mapping[str | None, Mapping[str | None, beancount.Account]]
    currency_mapping: Mapping[str | None, beancount.Currency]


class Importer(beangulp.Importer):
    """与 Beangulp 集成的主导入器类。

    此类实现 Beangulp Importer 接口，并协调将金融文档
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
        """初始化导入器。

        设置导入器的文件名模式匹配、用于从文件提取记录的读取器、
        将记录转换为交易的解析器，以及账户和货币转换的映射。

        参数：
            filename: 用于识别文件的文件名匹配模式。
            reader: 用于从文件提取记录的读取器实例。
            parser: 用于将记录转换为交易的解析器实例。
            **kwargs: 额外配置，包括账户和货币映射。
        """
        self.__filename_pattern = filename
        self.__reader = reader
        self.__parser = parser
        self.__account_mappings = kwargs["account_mapping"]
        self.__currency_mapping = kwargs["currency_mapping"]

    @override
    def identify(self, filepath: str) -> bool:
        """识别文件是否由此导入器处理。

        参数：
            filepath: 文件路径

        返回：
            如果文件名匹配模式则返回 True，否则返回 False
        """
        return self.__filename_pattern.fullmatch(Path(filepath).name) is not None

    @override
    def account(self, filepath: str) -> str:
        """返回文件对应的归档账户。

        参数：
            filepath: 文件路径

        返回：
            归档账户名称
        """
        return self._analyse_account(self._cached_metadata(filepath))

    @override
    def date(self, filepath: str) -> datetime.date | None:
        """返回文件对应的日期。

        参数：
            filepath: 文件路径

        返回：
            从文件元数据中提取的日期
        """
        return self._cached_metadata(filepath).date

    @override
    def filename(self, filepath: str) -> str:
        """返回文件名。

        参数：
            filepath: 文件路径

        返回：
            不带路径的文件名
        """
        return Path(filepath).name

    @override
    def extract(
        self,
        filepath: str,
        existing: beancount.Directives,
    ) -> beancount.Directives:
        """从文件中提取 Beancount 条目。

        参数：
            filepath: 文件路径
            existing: 现有的 Beancount 指令（用于去重）

        返回：
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
        """对条目进行去重处理。

        参数：
            entries: 待去重的条目列表
            existing: 现有的 Beancount 条目
        """
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
    def sort(self, entries: beancount.Directives, reverse: bool = False) -> None:
        """对条目进行排序。

        参数：
            entries: 待排序的条目列表
            reverse: 是否反向排序
        """
        def sort_key(entry: beancount.Directive) -> tuple[int, int]:
            lineno = entry.meta["lineno"]  # pyright: ignore[reportAny]
            return (
                self._lineno_key(lineno),  # pyright: ignore[reportAny]
                0 if isinstance(entry, beancount.Transaction) else 1,
            )

        entries.sort(key=sort_key, reverse=reverse)

    def _lineno_key(self, lineno: int) -> int:
        """生成行号排序键。

        参数：
            lineno: 行号

        返回：
            根据解析器的 reversed 属性调整后的排序键
        """
        return -lineno if self.__parser.reversed else lineno

    @lru_cache(maxsize=1)  # noqa: B019
    def _cached_metadata(self, filepath: str) -> Metadata:
        """缓存文件的元数据。

        参数：
            filepath: 文件路径

        返回：
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
        """提取单条记录并转换为 Beancount 指令。

        参数：
            filepath: 文件路径
            lineno: 行号
            metadata: 文件元数据
            record: 原始记录数据

        返回：
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
        """构建 Beancount 条目的元数据字典。

        参数：
            filepath: 文件路径
            lineno: 行号
            record: 原始记录
            **meta: 额外的元数据

        返回：
            元数据字典
        """
        return beancount.new_metadata(
            self.filename(filepath),
            lineno,
            kvlist={
                key: str(value)
                for key, value in {
                    "__source__": str(record),
                    **meta,
                }.items()
                if value is not None
            },
        )

    def _analyse_account(
        self,
        metadata: Metadata,
        posting: Posting | None = None,
    ) -> beancount.Account:
        """分析并映射账户名称。

        参数：
            metadata: 文件元数据
            posting: 记账分录（可选）

        返回：
            映射后的 Beancount 账户

        异常：
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
        """分析并转换金额和货币。

        参数：
            metadata: 文件元数据
            posting: 记账分录

        返回：
            Beancount 金额对象

        异常：
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
