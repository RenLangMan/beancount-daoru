"""测试条目排序模块."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from beancount.core import data

from beancount_daoru.rebuilder.sorter import EntrySorter, SortKey


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


def create_balance(
    balance_date: date,
    account: str = "Assets:Cash",
) -> data.Balance:
    """创建测试余额条目."""
    return data.Balance(
        meta={"filename": "test.bean", "lineno": 1},
        date=balance_date,
        account=account,
        amount=data.Amount(Decimal(1000), "CNY"),
        tolerance=None,
        diff_amount=None,
    )


class TestSortKey:
    """测试 SortKey."""

    def test_from_entry_with_timestamp(self) -> None:
        """测试从带时间戳的条目创建排序键."""
        txn = create_transaction(date(2024, 1, 15), timestamp=120000)
        key = SortKey.from_entry(txn, original_index=5)

        assert key.date_ordinal == date(2024, 1, 15).toordinal()
        assert key.has_timestamp == 0
        assert key.timestamp == 120000
        assert key.original_index == 5

    def test_from_entry_without_timestamp(self) -> None:
        """测试从无时间戳的条目创建排序键."""
        txn = create_transaction(date(2024, 1, 15), timestamp=None)
        key = SortKey.from_entry(txn)

        assert key.has_timestamp == 1
        assert key.timestamp == 0

    def test_type_priority_transaction(self) -> None:
        """测试交易类型优先级."""
        txn = create_transaction(date(2024, 1, 15))
        key = SortKey.from_entry(txn)

        assert key.type_priority == 20  # Transaction

    def test_type_priority_balance(self) -> None:
        """测试余额类型优先级."""
        bal = create_balance(date(2024, 1, 15))
        key = SortKey.from_entry(bal)

        assert key.type_priority == 30  # Balance


class TestEntrySorter:
    """测试 EntrySorter."""

    def test_sort_by_date(self) -> None:
        """测试按日期排序."""
        txn1 = create_transaction(date(2024, 1, 15), narration="Jan 15")
        txn2 = create_transaction(date(2024, 1, 10), narration="Jan 10")
        txn3 = create_transaction(date(2024, 1, 20), narration="Jan 20")

        entries = [txn1, txn2, txn3]
        sorted_entries = EntrySorter.sort_entries(entries)

        assert sorted_entries[0].narration == "Jan 10"
        assert sorted_entries[1].narration == "Jan 15"
        assert sorted_entries[2].narration == "Jan 20"

    def test_sort_by_timestamp_same_date(self) -> None:
        """测试同一日期内按时间戳排序."""
        txn1 = create_transaction(
            date(2024, 1, 15), timestamp=150000, narration="15:00"
        )
        txn2 = create_transaction(date(2024, 1, 15), timestamp=90000, narration="09:00")
        txn3 = create_transaction(
            date(2024, 1, 15), timestamp=120000, narration="12:00"
        )

        entries = [txn1, txn2, txn3]
        sorted_entries = EntrySorter.sort_entries(entries)

        assert sorted_entries[0].narration == "09:00"
        assert sorted_entries[1].narration == "12:00"
        assert sorted_entries[2].narration == "15:00"

    def test_sort_by_type_priority(self) -> None:
        """测试按类型优先级排序."""
        bal = create_balance(date(2024, 1, 15))
        txn = create_transaction(date(2024, 1, 15), timestamp=120000)

        entries = [bal, txn]
        sorted_entries = EntrySorter.sort_entries(entries)

        # Transaction (20) 在 Balance (30) 之前
        assert isinstance(sorted_entries[0], data.Transaction)
        assert isinstance(sorted_entries[1], data.Balance)

    def test_group_by_date(self) -> None:
        """测试按日期分组."""
        txn1 = create_transaction(date(2024, 1, 15), narration="Jan 15")
        txn2 = create_transaction(date(2024, 1, 10), narration="Jan 10")
        txn3 = create_transaction(date(2024, 1, 15), narration="Jan 15 #2")

        entries = [txn1, txn2, txn3]
        grouped = EntrySorter.group_by_date(entries)

        assert len(grouped) == 2
        assert len(grouped[date(2024, 1, 10)]) == 1
        assert len(grouped[date(2024, 1, 15)]) == 2

    def test_sort_and_group_by_date(self) -> None:
        """测试排序并分组."""
        txn1 = create_transaction(
            date(2024, 1, 15), timestamp=150000, narration="15:00"
        )
        txn2 = create_transaction(date(2024, 1, 10), timestamp=90000, narration="09:00")
        txn3 = create_transaction(
            date(2024, 1, 15), timestamp=120000, narration="12:00"
        )

        entries = [txn1, txn2, txn3]
        grouped = EntrySorter.sort_and_group_by_date(entries)

        # 检查日期顺序
        dates = list(grouped.keys())
        assert dates[0] == date(2024, 1, 10)
        assert dates[1] == date(2024, 1, 15)

        # 检查1月15日内的顺序
        jan15_entries = grouped[date(2024, 1, 15)]
        assert jan15_entries[0].narration == "12:00"
        assert jan15_entries[1].narration == "15:00"

    def test_empty_list(self) -> None:
        """测试空列表."""
        assert EntrySorter.sort_entries([]) == []
        assert EntrySorter.group_by_date([]) == {}
        assert EntrySorter.sort_and_group_by_date([]) == {}
