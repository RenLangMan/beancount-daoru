"""条目排序模块.

提供基于时间戳、日期、类型优先级的条目排序功能.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from beancount.core.data import Directive


@dataclass(frozen=True, order=True)
class SortKey:
    """排序键, 用于条目排序.

    排序优先级:
    1. 类型优先级 (type_priority) - Open/Close/Pad 必须在交易前
    2. 日期 (date)
    3. 时间戳 (timestamp) - 同一天内的精确排序
    4. 原始索引 (original_index) - 保证稳定性
    """

    type_priority: int
    date_ordinal: int
    has_timestamp: int  # 0=有, 1=无
    timestamp: int
    original_index: int

    @classmethod
    def from_entry(
        cls,
        entry: Directive,
        original_index: int = 0,
    ) -> SortKey:
        """从条目创建排序键."""
        entry_date = entry.date if hasattr(entry, "date") else date.min
        timestamp = cls._extract_timestamp(entry)
        type_priority = cls._get_type_priority(type(entry).__name__)

        return cls(
            date_ordinal=entry_date.toordinal(),
            has_timestamp=0 if timestamp is not None else 1,
            timestamp=timestamp or 0,
            type_priority=type_priority,
            original_index=original_index,
        )

    @staticmethod
    def _extract_timestamp(entry: Directive) -> int | None:
        """从条目元数据中提取时间戳."""
        if not hasattr(entry, "meta") or not entry.meta:
            return None

        ts_fields = ["timestamp", "trade_time", "time"]
        for field in ts_fields:
            if field in entry.meta:
                value = entry.meta[field]
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
                if isinstance(value, str):
                    try:
                        return int(float(value))
                    except (ValueError, TypeError):
                        pass
        return None

    @staticmethod
    def _get_type_priority(entry_type: str) -> int:
        """获取条目类型优先级.

        优先级顺序:
        - Open: 5 (定义账户, 必须最前)
        - Close: 6 (关闭账户)
        - Pad: 10 (填充指令, 应在交易前)
        - Transaction: 20 (交易)
        - Balance: 30 (余额对账, 应在交易后)
        - Note: 40 (备注)
        - Event: 50 (事件)
        - Price: 60 (价格)
        """
        priority_map = {
            "Open": 5,
            "Close": 6,
            "Pad": 10,
            "Transaction": 20,
            "Balance": 30,
            "Note": 40,
            "Event": 50,
            "Price": 60,
        }
        return priority_map.get(entry_type, 999)


class EntrySorter:
    """条目排序器."""

    # 元数据排序排除的字段（保持原位置或特定顺序）
    META_EXCLUDE_SORT: frozenset[str] = frozenset({"lineno", "filename", "kvlist"})

    @staticmethod
    def sort_entries(
        entries: list[Directive],
        *,
        preserve_order: bool = True,
    ) -> list[Directive]:
        """排序条目列表.

        Args:
            entries: 条目列表
            preserve_order: 是否保留原始顺序作为最后排序依据

        Returns:
            排序后的条目列表
        """
        if preserve_order:
            # 添加原始索引保证稳定性
            indexed_entries = enumerate(entries)
            sortable = [
                (SortKey.from_entry(entry, idx), entry)
                for idx, entry in indexed_entries
            ]
        else:
            sortable = [(SortKey.from_entry(entry), entry) for entry in entries]

        sortable.sort(key=lambda x: x[0])
        return [entry for _, entry in sortable]

    @staticmethod
    def sort_entry_metadata(entry: Directive) -> Directive:
        """对条目的元数据字段进行排序.

        按键名字母顺序排序元数据（排除系统字段）.

        Args:
            entry: 条目

        Returns:
            排序后的条目（in-place修改）
        """
        meta = getattr(entry, "meta", None)
        if not meta:
            return entry

        # 分离系统字段和需要排序的字段
        system_keys = EntrySorter.META_EXCLUDE_SORT & set(meta.keys())
        sort_keys = [k for k in meta if k not in EntrySorter.META_EXCLUDE_SORT]

        # 按字母顺序排序
        sort_keys.sort()

        # 重建排序后的元数据（保留原始meta类型）
        new_meta = type(meta)(meta)  # 复制原始meta
        # 重新排列顺序：系统字段保持原位，用户字段排序
        for key in list(new_meta.keys()):
            if key not in system_keys:
                del new_meta[key]
        for key in sort_keys:
            new_meta[key] = meta[key]

        # 直接更新meta（运行时实际可修改）
        object.__setattr__(entry, "meta", new_meta)  # type: ignore[reportAttributeAccessIssue]
        return entry

    @staticmethod
    def sort_entries_metadata(entries: list[Directive]) -> list[Directive]:
        """对所有条目的元数据进行排序.

        Args:
            entries: 条目列表

        Returns:
            元数据排序后的条目列表
        """
        for entry in entries:
            EntrySorter.sort_entry_metadata(entry)
        return entries

    @staticmethod
    def group_by_date(
        entries: list[Directive],
    ) -> dict[date, list[Directive]]:
        """按日期分组条目.

        Args:
            entries: 条目列表

        Returns:
            按日期分组的字典
        """
        groups: dict[date, list[Directive]] = defaultdict(list)
        for entry in entries:
            entry_date = entry.date if hasattr(entry, "date") else date.min
            groups[entry_date].append(entry)

        return dict(groups)

    @staticmethod
    def sort_and_group_by_date(
        entries: list[Directive],
    ) -> dict[date, list[Directive]]:
        """先排序, 再按日期分组.

        这是主要的便捷方法, 确保同一天内的条目按正确顺序排列.

        Args:
            entries: 条目列表

        Returns:
            按日期分组的字典, 每组内已排序
        """
        sorted_entries = EntrySorter.sort_entries(entries)
        return EntrySorter.group_by_date(sorted_entries)
