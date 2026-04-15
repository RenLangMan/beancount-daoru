"""测试将文件路径转换为文件名的钩子."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from beancount.core.data import Transaction

from beancount_daoru.hooks.path_to_name import Hook

if TYPE_CHECKING:
    from beancount_daoru.hook import Imported


def create_transaction(payee: str = "Test Payee") -> Transaction:
    """创建真实的 Transaction 对象."""
    return Transaction(
        meta=MagicMock(),
        date=datetime.date(2024, 1, 1),
        flag="*",
        payee=payee,
        narration="Test Narration",
        tags=frozenset(),
        links=frozenset(),
        postings=[],
    )


class TestHook:
    """测试 PathToName 钩子."""

    def test_call_with_full_path(self) -> None:
        """测试处理完整路径的文件名转换."""
        hook = Hook()
        importer = MagicMock()
        importer.name = "TestImporter"
        directives = [create_transaction("Payee 1")]

        imported: list[Imported] = [
            ("/path/to/transactions.beancount", directives, "Assets:Test", importer),
            ("/another/path/data.bean", directives, "Assets:Another", importer),
        ]

        result = hook(imported, [])

        assert result[0][0] == "transactions.beancount"
        assert result[1][0] == "data.bean"

    def test_call_with_relative_path(self) -> None:
        """测试处理相对路径的文件名转换."""
        hook = Hook()
        importer = MagicMock()
        importer.name = "TestImporter"
        directives = [create_transaction()]

        imported: list[Imported] = [
            ("relative/path/to/file.csv", directives, "Assets:Test", importer),
        ]

        result = hook(imported, [])

        assert result[0][0] == "file.csv"

    def test_call_with_filename_only(self) -> None:
        """测试只包含文件名的路径."""
        hook = Hook()
        importer = MagicMock()
        importer.name = "TestImporter"
        directives = [create_transaction()]

        imported: list[Imported] = [
            ("file.csv", directives, "Assets:Test", importer),
        ]

        result = hook(imported, [])

        assert result[0][0] == "file.csv"

    def test_call_preserves_other_elements(self) -> None:
        """测试转换后保留其他元素不变."""
        hook = Hook()
        importer = MagicMock()
        importer.name = "TestImporter"
        directives = [create_transaction()]

        imported: list[Imported] = [
            ("/path/to/file.bean", directives, "Assets:Checking", importer),
        ]

        result = hook(imported, [])

        assert result[0][1] is directives
        assert result[0][2] == "Assets:Checking"
        assert result[0][3] is importer
