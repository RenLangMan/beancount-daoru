"""按时间戳排序的导入钩子.

在导入时按日期+时间戳排序交易记录,
确保同一日期内的多笔交易按精确时间顺序排列.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from beancount_daoru.hook import Hook as BaseHook
from beancount_daoru.hook import Imported
from beancount_daoru.rebuilder.sorter import EntrySorter

if TYPE_CHECKING:
    from beancount import Directives


class SortByTimestamp(BaseHook):
    """按时间戳排序的钩子.

    对每个导入的文件, 按日期+时间戳对条目进行排序.
    """

    def __call__(
        self, imported: list[Imported], _existing: Directives
    ) -> list[Imported]:
        """按时间戳排序导入的条目(每个文件独立排序)."""
        result: list[Imported] = []
        for filename, entries, account, importer in imported:
            sorted_entries = EntrySorter.sort_entries(entries)
            result.append((filename, sorted_entries, account, importer))

        return result
