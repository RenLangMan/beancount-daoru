"""测试 beancount_daoru.importer 模块."""

import datetime
import re
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import beancount
import pytest
from beangulp.extract import DUPLICATE

from beancount_daoru.importer import (
    Extra,
    Importer,
    Metadata,
    Parser,
    ParserError,
    Posting,
    Transaction,
)


class MockReader:
    """模拟读取器用于测试."""

    def __init__(self, captions: list[str], records: list[dict[str, str]]) -> None:
        self._captions = captions
        self._records = records

    def read_captions(self, _: Path) -> Iterator[str]:
        return iter(self._captions)

    def read_records(self, _: Path) -> Iterator[dict[str, str]]:
        return iter(self._records)


class MockParser(Parser):
    """模拟解析器用于测试."""

    def __init__(
        self,
        metadata: Metadata,
        transactions: list[Transaction],
        *,
        is_reversed: bool = False,
    ) -> None:
        self._metadata = metadata
        self._transactions = transactions
        self._is_reversed = is_reversed
        self._call_index = 0

    @property
    def reversed(self) -> bool:
        return self._is_reversed

    def extract_metadata(self, _: Iterator[str]) -> Metadata:
        return self._metadata

    def parse(self, _: dict[str, str]) -> Transaction:
        if self._call_index < len(self._transactions):
            tx = self._transactions[self._call_index]
            self._call_index += 1
            return tx
        msg = "no transaction available"
        raise ValueError(msg)


@pytest.fixture
def mock_reader() -> MockReader:
    """创建模拟读取器."""
    captions = ["账户:TestAccount", "日期:2024-01-31"]
    records = [
        {"date": "2024-01-15", "amount": "100.00", "desc": "Test transaction"},
        {"date": "2024-01-20", "amount": "200.00", "desc": "Another transaction"},
    ]
    return MockReader(captions, records)


@pytest.fixture
def mock_parser() -> MockParser:
    """创建模拟解析器."""
    metadata = Metadata(
        account="test@example.com",
        date=datetime.date(2024, 1, 31),
        currency="CNY",
    )
    transactions = [
        Transaction(
            date=datetime.date(2024, 1, 15),
            extra=Extra(dc="支出", status="交易成功"),
            payee="Test Merchant",
            narration="Test transaction",
            postings=(
                Posting(account="余额", amount=Decimal("-100.00")),
                Posting(account="Expenses:Test", amount=Decimal("100.00")),
            ),
            balance=Posting(account="余额", amount=Decimal("1000.00")),
        ),
        Transaction(
            date=datetime.date(2024, 1, 20),
            extra=Extra(dc="收入", status="交易成功"),
            payee="Income Source",
            narration="Another transaction",
            postings=(Posting(account="余额", amount=Decimal("200.00")),),
        ),
    ]
    return MockParser(metadata, transactions)


@pytest.fixture
def importer(mock_reader: MockReader, mock_parser: MockParser) -> Importer:
    """创建导入器实例."""
    return Importer(
        re.compile(r"test_\d{8}.csv"),
        mock_reader,
        mock_parser,
        account_mapping={
            "test@example.com": {
                None: "Assets:Test",
                "余额": "Assets:Test:Balance",
                "Expenses:Test": "Expenses:Test",
            },
        },
        currency_mapping={
            None: "CNY",
            "CNY": "CNY",
        },
    )


class TestImporterIdentify:
    """测试 identify 方法."""

    def test_identify_match(self, importer: Importer) -> None:
        """测试文件名匹配时返回 True."""
        assert importer.identify("/path/to/test_20240115.csv") is True

    def test_identify_no_match(self, importer: Importer) -> None:
        """测试文件名不匹配时返回 False."""
        assert importer.identify("/path/to/other_file.csv") is False
        assert importer.identify("/path/to/test_file.txt") is False


class TestImporterAccount:
    """测试 account 方法."""

    def test_account_returns_mapped_account(self, importer: Importer) -> None:
        """测试返回映射后的账户."""
        account = importer.account("/path/to/test_20240115.csv")
        assert account == "Assets:Test"

    def test_account_unmapped_raises_key_error(
        self,
        mock_reader: MockReader,
    ) -> None:
        """测试未映射的账户抛出 KeyError."""
        parser = MockParser(
            Metadata(account="unknown@example.com", date=None),
            [],
        )
        imp = Importer(
            re.compile(r"test.csv"),
            mock_reader,
            parser,
            account_mapping={
                "test@example.com": {
                    None: "Assets:Test",
                },
            },
            currency_mapping={
                None: "CNY",
            },
        )
        with pytest.raises(KeyError, match="account is not mapped"):
            _ = imp.account("/path/to/test_20240115.csv")


class TestImporterDate:
    """测试 date 方法."""

    def test_date_returns_metadata_date(self, importer: Importer) -> None:
        """测试返回元数据中的日期."""
        date = importer.date("/path/to/test_20240115.csv")
        assert date == datetime.date(2024, 1, 31)


class TestImporterFilename:
    """测试 filename 方法."""

    def test_filename_returns_basename(self, importer: Importer) -> None:
        """测试返回文件基名."""
        filename = importer.filename("/path/to/test_20240115.csv")
        assert filename == "test_20240115.csv"


class TestImporterExtract:
    """测试 extract 方法."""

    def test_extract_returns_transactions(
        self,
        tmp_path: Path,
    ) -> None:
        """测试 extract 返回交易列表."""
        # 创建专用的 reader 和 parser
        reader = MockReader(
            ["账户:Test", "日期:2024-01-31"],
            [
                {"date": "2024-01-15", "amount": "100.00"},
                {"date": "2024-01-20", "amount": "200.00"},
            ],
        )
        parser = MockParser(
            Metadata(
                account="test@example.com",
                date=datetime.date(2024, 1, 31),
                currency="CNY",
            ),
            [
                Transaction(
                    date=datetime.date(2024, 1, 15),
                    extra=Extra(dc="支出", status="交易成功"),
                    payee="Test Merchant",
                    narration="Test 1",
                    postings=(Posting(account="余额", amount=Decimal("-100.00")),),
                    balance=Posting(account="余额", amount=Decimal("1000.00")),
                ),
                Transaction(
                    date=datetime.date(2024, 1, 20),
                    extra=Extra(dc="收入", status="交易成功"),
                    payee="Income Source",
                    narration="Test 2",
                    postings=(Posting(account="余额", amount=Decimal("200.00")),),
                ),
            ],
        )
        imp = Importer(
            re.compile(r"test_\d{8}.csv"),
            reader,
            parser,
            account_mapping={
                "test@example.com": {
                    None: "Assets:Test",
                    "余额": "Assets:Test:Balance",
                },
            },
            currency_mapping={
                None: "CNY",
                "CNY": "CNY",
            },
        )

        test_file = tmp_path / "test_20240115.csv"
        test_file.touch()

        entries = imp.extract(str(test_file), [])

        # 应该返回 3 个条目: 2 个 Transaction + 1 个 Balance
        # 顺序: Transaction(lineno=0), Balance(lineno=0), Transaction(lineno=1)
        assert len(entries) == 3

        # 检查第一个 Transaction
        tx1 = entries[0]
        assert isinstance(tx1, beancount.Transaction)
        assert tx1.date == datetime.date(2024, 1, 15)
        assert tx1.payee == "Test Merchant"
        assert len(tx1.postings) == 1

        # 检查 Balance (第一个 transaction 有 balance)
        balance = entries[1]
        assert isinstance(balance, beancount.Balance)
        assert balance.date == datetime.date(2024, 1, 16)  # +1 day
        assert balance.account == "Assets:Test:Balance"

        # 检查第二个 Transaction (没有 balance)
        tx2 = entries[2]
        assert isinstance(tx2, beancount.Transaction)
        assert tx2.date == datetime.date(2024, 1, 20)
        assert len(tx2.postings) == 1

    def test_extract_with_parser_error(
        self,
        tmp_path: Path,
    ) -> None:
        """测试 ParserError 时返回警告 Transaction."""
        # 创建一个只返回一条记录的 reader
        error_reader = MockReader(
            ["账户:Test", "日期:2024-01-31"],
            [{"date": "2024-01-15", "amount": "100.00", "desc": "Test"}],
        )
        error_parser = MockParser(
            Metadata(account="test@example.com", date=datetime.date(2024, 1, 31)),
            [],
        )

        # 让解析器抛出 ParserError
        def failing_parse(_: dict[str, str]) -> Transaction:
            err_msg = "test_error"
            raise ParserError(err_msg)

        error_parser.parse = failing_parse  # type: ignore[method-assign]

        imp = Importer(
            re.compile(r"test.csv"),
            error_reader,
            error_parser,
            account_mapping={
                "test@example.com": {
                    None: "Assets:Test",
                },
            },
            currency_mapping={
                None: "CNY",
            },
        )

        test_file = tmp_path / "test.csv"
        test_file.touch()

        entries = imp.extract(str(test_file), [])

        # 应该返回一个警告 Transaction
        assert len(entries) == 1
        assert isinstance(entries[0], beancount.Transaction)
        assert entries[0].flag == beancount.FLAG_WARNING
        assert entries[0].date == datetime.date(1970, 1, 1)


class TestImporterDeduplicate:
    """测试 deduplicate 方法."""

    def test_deduplicate_keeps_latest(self, importer: Importer) -> None:
        """测试去重保留最新的 Balance."""
        date1 = datetime.date(2024, 1, 15)
        meta1 = beancount.new_metadata("test.csv", 10)
        meta2 = beancount.new_metadata("test.csv", 20)

        balance1 = beancount.Balance(
            meta=meta1,
            date=date1,
            account="Assets:Test:Balance",
            amount=beancount.Amount(Decimal("100.00"), "CNY"),
            tolerance=None,
            diff_amount=None,
        )
        balance2 = beancount.Balance(
            meta=meta2,
            date=date1,
            account="Assets:Test:Balance",
            amount=beancount.Amount(Decimal("200.00"), "CNY"),
            tolerance=None,
            diff_amount=None,
        )

        entries = [balance1, balance2]

        importer.deduplicate(entries, [])

        # 第二个 balance 应该标记为 DUPLICATE
        assert DUPLICATE in balance1.meta
        assert balance1.meta[DUPLICATE] == balance2


class TestImporterSort:
    """测试 sort 方法."""

    def test_sort_by_lineno(
        self,
        importer: Importer,
        tmp_path: Path,
    ) -> None:
        """测试按行号排序."""
        test_file = tmp_path / "test.csv"
        test_file.touch()

        entries = importer.extract(str(test_file), [])
        original_dates = [e.date for e in entries]

        importer.sort(entries)

        # 排序后日期应该保持不变
        assert [e.date for e in entries] == original_dates

    def test_sort_reverse(
        self,
        importer: Importer,
        tmp_path: Path,
    ) -> None:
        """测试反向排序."""
        test_file = tmp_path / "test.csv"
        test_file.touch()

        entries = importer.extract(str(test_file), [])

        importer.sort(entries, reverse=True)

        # 反向排序后顺序应该颠倒
        for i in range(len(entries) - 1):
            assert entries[i].meta["lineno"] >= entries[i + 1].meta["lineno"]


class TestImporterLinenoKey:
    """测试 _lineno_key 方法."""

    def test_lineno_key_normal(self, importer: Importer) -> None:
        """测试正常解析器的行号键."""
        key = importer._lineno_key(100)
        assert key == 100

    def test_lineno_key_reversed(self, mock_reader: MockReader) -> None:
        """测试反向解析器的行号键."""
        parser = MockParser(
            Metadata(account="test@example.com", date=None),
            [],
            is_reversed=True,
        )
        imp = Importer(
            re.compile(r"test.csv"),
            mock_reader,
            parser,
            account_mapping={
                "test@example.com": {
                    None: "Assets:Test",
                },
            },
            currency_mapping={
                None: "CNY",
            },
        )
        key = imp._lineno_key(100)
        assert key == -100


class TestImporterCachedMetadata:
    """测试 _cached_metadata 方法."""

    def test_cached_metadata(
        self,
        importer: Importer,
        tmp_path: Path,
    ) -> None:
        """测试元数据缓存."""
        test_file = tmp_path / "test.csv"
        test_file.touch()

        # 多次调用应返回相同结果
        meta1 = importer._cached_metadata(str(test_file))
        meta2 = importer._cached_metadata(str(test_file))

        assert meta1 == meta2
        assert meta1.account == "test@example.com"
        assert meta1.date == datetime.date(2024, 1, 31)


class TestImporterExtractRecord:
    """测试 _extract_record 方法."""

    def test_extract_record_with_balance(
        self,
        mock_reader: MockReader,
    ) -> None:
        """测试带余额的记录提取."""
        tx_with_balance = Transaction(
            date=datetime.date(2024, 2, 1),
            extra=Extra(dc="支出", status="交易成功"),
            payee="Test",
            narration="Test",
            postings=(Posting(account="余额", amount=Decimal("-50.00")),),
            balance=Posting(account="余额", amount=Decimal("500.00"), currency="CNY"),
        )
        parser = MockParser(
            Metadata(
                account="test@example.com",
                date=datetime.date(2024, 2, 1),
                currency="CNY",
            ),
            [tx_with_balance],
        )
        imp = Importer(
            re.compile(r"test.csv"),
            mock_reader,
            parser,
            account_mapping={
                "test@example.com": {
                    None: "Assets:Test",
                    "余额": "Assets:Test:Balance",
                },
            },
            currency_mapping={
                None: "CNY",
                "CNY": "CNY",
            },
        )

        records = list(
            imp._extract_record(
                "test.csv",
                1,
                Metadata(
                    account="test@example.com",
                    date=datetime.date(2024, 2, 1),
                    currency="CNY",
                ),
                {},
            )
        )

        # 应该返回 Transaction 和 Balance
        assert len(records) == 2
        assert isinstance(records[0], beancount.Transaction)
        assert isinstance(records[1], beancount.Balance)

    def test_extract_record_without_balance(
        self,
        mock_reader: MockReader,
    ) -> None:
        """测试不带余额的记录提取."""
        tx_no_balance = Transaction(
            date=datetime.date(2024, 2, 1),
            extra=Extra(dc="收入", status="交易成功"),
            payee="Test",
            narration="Test",
            postings=(Posting(account="余额", amount=Decimal("100.00")),),
        )
        parser = MockParser(
            Metadata(
                account="test@example.com",
                date=datetime.date(2024, 2, 1),
                currency="CNY",
            ),
            [tx_no_balance],
        )
        imp = Importer(
            re.compile(r"test.csv"),
            mock_reader,
            parser,
            account_mapping={
                "test@example.com": {
                    None: "Assets:Test",
                    "余额": "Assets:Test:Balance",
                },
            },
            currency_mapping={
                None: "CNY",
                "CNY": "CNY",
            },
        )

        records = list(
            imp._extract_record(
                "test.csv",
                1,
                Metadata(
                    account="test@example.com",
                    date=datetime.date(2024, 2, 1),
                    currency="CNY",
                ),
                {},
            )
        )

        # 应该只返回 Transaction
        assert len(records) == 1
        assert isinstance(records[0], beancount.Transaction)


class TestImporterBuildMeta:
    """测试 _build_meta 方法."""

    def test_build_meta_with_extra(
        self,
        importer: Importer,
        tmp_path: Path,
    ) -> None:
        """测试构建带额外信息的元数据."""
        test_file = tmp_path / "test.csv"
        test_file.touch()

        meta = importer._build_meta(
            str(test_file), 10, {"key": "value"}, error="test error"
        )

        assert "lineno" in meta
        assert meta["__source__"] == "{'key': 'value'}"
        assert meta["error"] == "test error"

    def test_build_meta_filters_none(
        self,
        importer: Importer,
        tmp_path: Path,
    ) -> None:
        """测试过滤 None 值."""
        test_file = tmp_path / "test.csv"
        test_file.touch()

        meta = importer._build_meta(str(test_file), 10, {"key": "value"}, error=None)

        assert "error" not in meta


class TestImporterAnalyseAccount:
    """测试 _analyse_account 方法."""

    def test_analyse_account_with_posting(
        self,
        importer: Importer,
    ) -> None:
        """测试带 posting 的账户分析."""
        metadata = Metadata(account="test@example.com", date=None)
        posting = Posting(account="余额", amount=Decimal("100.00"))

        account = importer._analyse_account(metadata, posting)
        assert account == "Assets:Test:Balance"

    def test_analyse_account_without_posting(
        self,
        importer: Importer,
    ) -> None:
        """测试不带 posting 的账户分析."""
        metadata = Metadata(account="test@example.com", date=None)

        account = importer._analyse_account(metadata)
        assert account == "Assets:Test"

    def test_analyse_account_unmapped_posting(
        self,
        importer: Importer,
    ) -> None:
        """测试未映射的 posting 账户."""
        metadata = Metadata(account="test@example.com", date=None)
        posting = Posting(account="未知方式", amount=Decimal("100.00"))

        with pytest.raises(KeyError, match=r"account of .* is not mapped"):
            _ = importer._analyse_account(metadata, posting)


class TestImporterAnalyseAmount:
    """测试 _analyse_amount 方法."""

    def test_analyse_amount_with_posting_currency(
        self,
        importer: Importer,
    ) -> None:
        """测试使用 posting 货币的金额分析."""
        metadata = Metadata(account="test@example.com", date=None, currency="CNY")
        posting = Posting(amount=Decimal("100.00"), currency="CNY")

        amount = importer._analyse_amount(metadata, posting)
        assert amount == beancount.Amount(Decimal("100.00"), "CNY")

    def test_analyse_amount_with_metadata_currency(
        self,
        importer: Importer,
    ) -> None:
        """测试使用 metadata 货币的金额分析."""
        metadata = Metadata(account="test@example.com", date=None, currency="CNY")
        posting = Posting(amount=Decimal("100.00"))

        amount = importer._analyse_amount(metadata, posting)
        assert amount == beancount.Amount(Decimal("100.00"), "CNY")

    def test_analyse_amount_unmapped_currency(
        self,
        importer: Importer,
    ) -> None:
        """测试未映射的货币."""
        metadata = Metadata(account="test@example.com", date=None, currency="USD")
        posting = Posting(amount=Decimal("100.00"), currency="USD")

        with pytest.raises(KeyError, match="currency name 'USD' is not mapped"):
            _ = importer._analyse_amount(metadata, posting)


class TestParserProtocol:
    """测试 Parser 协议."""

    def test_parser_protocol_reversed_default(self) -> None:
        """测试 Parser 协议的 reversed 默认实现."""

        # Protocol 类不能直接实例化,使用子类测试默认 reversed 属性
        class TestParser(Parser):
            def extract_metadata(self, _: Iterator[str]) -> Metadata:
                return Metadata(account=None, date=None)

            def parse(self, _: dict[str, str]) -> Transaction:
                return Transaction(date=datetime.date(2024, 1, 1), extra=Extra())

        parser = TestParser()
        assert parser.reversed is False
