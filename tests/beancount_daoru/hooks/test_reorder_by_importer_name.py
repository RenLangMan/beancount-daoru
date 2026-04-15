"""测试按导入器名称重排序条目的钩子."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from beancount_daoru.hooks.reorder_by_importer_name import Hook

if TYPE_CHECKING:
    from beancount import Directives


class TestHook:
    """测试 ReorderByImporterName 钩子."""

    def test_call_sorted_by_importer_name(self) -> None:
        """测试按导入器名称排序."""
        hook = Hook()

        importer_z = MagicMock()
        importer_z.name = "ZImporter"

        importer_a = MagicMock()
        importer_a.name = "AImporter"

        importer_m = MagicMock()
        importer_m.name = "MImporter"

        imported: Directives = [
            ("/path/z.bean", [], "Assets:Z", importer_z),
            ("/path/a.bean", [], "Assets:A", importer_a),
            ("/path/m.bean", [], "Assets:M", importer_m),
        ]

        result = hook(imported, [])

        assert result[0][0] == "/path/a.bean"
        assert result[0][3].name == "AImporter"
        assert result[1][0] == "/path/m.bean"
        assert result[1][3].name == "MImporter"
        assert result[2][0] == "/path/z.bean"
        assert result[2][3].name == "ZImporter"

    def test_call_preserves_all_elements(self) -> None:
        """测试排序后保留所有元素."""
        hook = Hook()

        importer = MagicMock()
        importer.name = "TestImporter"

        directives = MagicMock()
        imported: Directives = [
            ("/path/file.bean", directives, "Assets:Test", importer),
        ]

        result = hook(imported, [])

        assert len(result) == 1
        assert result[0][0] == "/path/file.bean"
        assert result[0][1] is directives
        assert result[0][2] == "Assets:Test"
        assert result[0][3] is importer

    def test_call_empty_list(self) -> None:
        """测试空列表输入."""
        hook = Hook()

        result = hook([], [])

        assert result == []
