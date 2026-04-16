"""测试按时间戳排序的导入钩子."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from beancount.core import data

from beancount_daoru.hooks.sort_by_timestamp import SortByTimestamp

if TYPE_CHECKING:
    from beancount_daoru.hook import Imported


def create_transaction(
    txn_date: date,
    timestamp: int | None = None,
    narration: str = "Test",
) -> data.Transaction:
    """创建测试交易."""
    meta = {"filename": "test.bean", "lineno": 1}
    if timestamp is not None:
        meta["timestamp"] = timestamp

    return data.Transaction(
        meta=meta,
        date=txn_date,
        flag="*",
        payee="",
        narration=narration,
        tags=data.EMPTY_SET,
        links=data.EMPTY_SET,
        postings=[
            data.Posting(
                account="Assets:Cash",
                units=data.Amount(Decimal(100), "CNY"),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ],
    )


class TestSortByTimestamp:
    """测试 SortByTimestamp 钩子."""

    def test_call_sorts_by_date(self) -> None:
        """测试按日期排序交易."""
        hook = SortByTimestamp()

        txn1 = create_transaction(date(2024, 1, 15), narration="Jan 15")
        txn2 = create_transaction(date(2024, 1, 10), narration="Jan 10")
        txn3 = create_transaction(date(2024, 1, 20), narration="Jan 20")

        imported: list[Imported] = [
            ("/path/file.bean", [txn1, txn2, txn3], "Assets:Test", MagicMock()),
        ]

        result = hook(imported, [])

        entries = result[0][1]
        assert len(entries) == 3
        assert entries[0].date == date(2024, 1, 10)
        assert entries[1].date == date(2024, 1, 15)
        assert entries[2].date == date(2024, 1, 20)

    def test_call_sorts_by_timestamp_within_same_date(self) -> None:
        """测试同一日期内按时间戳排序."""
        hook = SortByTimestamp()

        txn1 = create_transaction(
            date(2024, 1, 15), timestamp=120000, narration="12:00"
        )
        txn2 = create_transaction(date(2024, 1, 15), timestamp=90000, narration="09:00")
        txn3 = create_transaction(
            date(2024, 1, 15), timestamp=150000, narration="15:00"
        )

        imported: list[Imported] = [
            ("/path/file.bean", [txn1, txn2, txn3], "Assets:Test", MagicMock()),
        ]

        result = hook(imported, [])

        entries = result[0][1]
        assert len(entries) == 3
        assert entries[0].meta.get("timestamp") == 90000
        assert entries[1].meta.get("timestamp") == 120000
        assert entries[2].meta.get("timestamp") == 150000

    def test_call_sorts_mixed_dates_and_timestamps(self) -> None:
        """测试混合日期和时间戳的排序."""
        hook = SortByTimestamp()

        # 创建跨日期、跨时间的交易
        txn1 = create_transaction(
            date(2024, 1, 15), timestamp=150000, narration="Jan 15 15:00"
        )
        txn2 = create_transaction(
            date(2024, 1, 10), timestamp=120000, narration="Jan 10 12:00"
        )
        txn3 = create_transaction(
            date(2024, 1, 15), timestamp=90000, narration="Jan 15 09:00"
        )
        txn4 = create_transaction(
            date(2024, 1, 10), timestamp=180000, narration="Jan 10 18:00"
        )

        imported: list[Imported] = [
            ("/path/file.bean", [txn1, txn2, txn3, txn4], "Assets:Test", MagicMock()),
        ]

        result = hook(imported, [])

        entries = result[0][1]
        assert len(entries) == 4
        # 先按日期排序, 再按时间戳排序
        assert entries[0].narration == "Jan 10 12:00"
        assert entries[1].narration == "Jan 10 18:00"
        assert entries[2].narration == "Jan 15 09:00"
        assert entries[3].narration == "Jan 15 15:00"

    def test_call_handles_missing_timestamp(self) -> None:
        """测试处理缺失时间戳的情况."""
        hook = SortByTimestamp()

        txn1 = create_transaction(date(2024, 1, 15), timestamp=120000)
        txn2 = create_transaction(date(2024, 1, 15), timestamp=None)  # 无时间戳
        txn3 = create_transaction(date(2024, 1, 15), timestamp=90000)

        imported: list[Imported] = [
            ("/path/file.bean", [txn1, txn2, txn3], "Assets:Test", MagicMock()),
        ]

        result = hook(imported, [])

        entries = result[0][1]
        assert len(entries) == 3
        # 有时间戳的排在前面, 无时间戳的按原始顺序排后面
        assert entries[0].meta.get("timestamp") == 90000
        assert entries[1].meta.get("timestamp") == 120000
        assert entries[2].meta.get("timestamp") is None

    def test_call_handles_invalid_timestamp(self) -> None:
        """测试处理无效时间戳的情况."""
        hook = SortByTimestamp()

        txn1 = create_transaction(date(2024, 1, 15), timestamp=120000)
        txn2 = create_transaction(date(2024, 1, 15), timestamp="invalid")  # 无效时间戳
        txn3 = create_transaction(date(2024, 1, 15), timestamp=90000)

        imported: list[Imported] = [
            ("/path/file.bean", [txn1, txn2, txn3], "Assets:Test", MagicMock()),
        ]

        result = hook(imported, [])

        entries = result[0][1]
        assert len(entries) == 3
        # 有效时间戳的排在前面, 无效时间戳的按原始顺序排后面
        assert entries[0].meta.get("timestamp") == 90000
        assert entries[1].meta.get("timestamp") == 120000
        assert entries[2].meta.get("timestamp") == "invalid"

    def test_call_handles_non_transaction_entries(self) -> None:
        """测试处理非交易条目(如 Open、Balance 等)."""
        hook = SortByTimestamp()

        txn = create_transaction(date(2024, 1, 15), timestamp=120000)
        open_entry = data.Open(
            meta={"filename": "test.bean", "lineno": 1},
            date=date(2024, 1, 1),
            account="Assets:Cash",
            currencies=["CNY"],
            booking=None,
        )

        imported: list[Imported] = [
            ("/path/file.bean", [txn, open_entry], "Assets:Test", MagicMock()),
        ]

        result = hook(imported, [])

        entries = result[0][1]
        assert len(entries) == 2
        # 非交易条目排在最前面(key=(0, 0))
        assert isinstance(entries[0], data.Open)
        assert isinstance(entries[1], data.Transaction)

    def test_call_preserves_imported_structure(self) -> None:
        """测试保留导入结构(文件名、账户、导入器)."""
        hook = SortByTimestamp()

        txn = create_transaction(date(2024, 1, 15), timestamp=120000)
        importer = MagicMock()
        importer.name = "TestImporter"

        imported: list[Imported] = [
            ("/path/file.bean", [txn], "Assets:Test", importer),
        ]

        result = hook(imported, [])

        assert len(result) == 1
        assert result[0][0] == "/path/file.bean"
        assert result[0][2] == "Assets:Test"
        assert result[0][3] is importer

    def test_call_multiple_files(self) -> None:
        """测试处理多个文件的情况(每个文件独立排序)."""
        hook = SortByTimestamp()

        txn1 = create_transaction(date(2024, 1, 15), timestamp=120000)
        txn2 = create_transaction(date(2024, 1, 10), timestamp=90000)
        txn3 = create_transaction(date(2024, 1, 20), timestamp=60000)
        txn4 = create_transaction(date(2024, 1, 5), timestamp=180000)

        importer1 = MagicMock()
        importer2 = MagicMock()

        imported: list[Imported] = [
            ("/path/file1.bean", [txn1, txn2], "Assets:Test1", importer1),
            ("/path/file2.bean", [txn3, txn4], "Assets:Test2", importer2),
        ]

        result = hook(imported, [])

        # 每个文件独立排序, 只包含自己的条目
        assert len(result) == 2
        # file1: [txn2(Jan 10), txn1(Jan 15)]
        assert len(result[0][1]) == 2
        assert result[0][1][0].date == date(2024, 1, 10)
        assert result[0][1][1].date == date(2024, 1, 15)
        # file2: [txn4(Jan 5), txn3(Jan 20)]
        assert len(result[1][1]) == 2
        assert result[1][1][0].date == date(2024, 1, 5)
        assert result[1][1][1].date == date(2024, 1, 20)

    def test_call_empty_entries(self) -> None:
        """测试空条目列表."""
        hook = SortByTimestamp()

        imported: list[Imported] = [
            ("/path/file.bean", [], "Assets:Test", MagicMock()),
        ]

        result = hook(imported, [])

        assert len(result) == 1
        assert result[0][1] == []

    def test_call_empty_imported(self) -> None:
        """测试空导入列表."""
        hook = SortByTimestamp()

        result = hook([], [])

        assert result == []
