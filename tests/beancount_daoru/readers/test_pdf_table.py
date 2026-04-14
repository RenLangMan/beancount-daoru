"""PDF 表格读取器单元测试."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

from beancount_daoru.readers.pdf_table import Reader


class TestPdfTableReader:
    """PDF Table Reader 类的测试."""

    def test_init(self) -> None:
        """测试初始化."""
        reader = Reader(table_bbox=(0, 0, 100, 200))
        assert reader is not None

    def test_init_with_float_bbox(self) -> None:
        """测试使用浮点边界框初始化."""
        reader = Reader(table_bbox=(0.5, 0.5, 100.5, 200.5))
        assert reader is not None


class MockPage:
    """模拟 PDF 页面对象."""

    def __init__(
        self,
        outside_text: str = "",
        table: list[list[Any]] | None = None,
    ) -> None:
        self._outside_text = outside_text
        self._table = table

    def outside_bbox(self, _bbox: tuple) -> MockBBox:
        return MockBBox(self._outside_text)

    def within_bbox(self, _bbox: tuple) -> MockBBoxForTable:
        return MockBBoxForTable(self._table)


class MockBBox:
    """模拟边界框提取结果."""

    def __init__(self, text: str = "") -> None:
        self._text = text

    def extract_text_simple(self) -> str:
        return self._text


class MockBBoxForTable:
    """模拟表格提取结果."""

    def __init__(self, table: list[list[Any]] | None) -> None:
        self._table = table

    def extract_table(self) -> list[list[Any]] | None:
        return self._table


class MockPDF:
    """模拟 PDF 文档对象(上下文管理器)."""

    def __init__(self, pages: list[MockPage]) -> None:
        self._pages = pages
        # pdfplumber.open 返回的对象有 pages 属性
        self.pages = pages

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def make_mock_pdf(pages_data: list[dict]) -> MockPDF:
    """Create mock PDF with given page data.

    Args:
        pages_data: Data for each page, each item contains:
            - outside_text: Text returned by outside_bbox
            - table: Table data returned by within_bbox, None means no table
    """
    pages = [
        MockPage(
            outside_text=page_data.get("outside_text", ""),
            table=page_data.get("table", None),
        )
        for page_data in pages_data
    ]
    return MockPDF(pages)


class TestPdfTableReaderMocked:
    """使用 Mock 的 PDF Table Reader 测试."""

    def test_read_captions_single_page(self, tmp_path: Path) -> None:
        """测试读取单页 PDF 的标题."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf([{"outside_text": "Page title"}])

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            captions = list(reader.read_captions(pdf_file))

        assert len(captions) == 1
        assert captions[0] == "Page title"

    def test_read_captions_multi_page(self, tmp_path: Path) -> None:
        """测试读取多页 PDF 的标题."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [{"outside_text": "Page 1"}, {"outside_text": "Page 2"}]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            captions = list(reader.read_captions(pdf_file))

        assert len(captions) == 2
        assert captions[0] == "Page 1"
        assert captions[1] == "Page 2"

    def test_read_captions_empty_text(self, tmp_path: Path) -> None:
        """测试读取空文本的标题."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf([{"outside_text": ""}])

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            captions = list(reader.read_captions(pdf_file))

        assert len(captions) == 1
        assert captions[0] == ""

    def test_read_records_single_page(self, tmp_path: Path) -> None:
        """测试读取单页 PDF 的表格数据."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [
                {
                    "table": [
                        ["Name", "Amount", "Date"],
                        ["Alice", "100", "2024-01-01"],
                        ["Bob", "200", "2024-01-02"],
                    ]
                }
            ]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert len(records) == 2

        assert records[0]["Name"] == "Alice"
        assert records[0]["Amount"] == "100"
        assert records[0]["Date"] == "2024-01-01"

        assert records[1]["Name"] == "Bob"
        assert records[1]["Amount"] == "200"
        assert records[1]["Date"] == "2024-01-02"

    def test_read_records_multi_page(self, tmp_path: Path) -> None:
        """测试读取多页 PDF 的表格数据."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [
                {"table": [["Name", "Amount"], ["Alice", "100"]]},
                {"table": [["Name", "Amount"], ["Bob", "200"], ["Carol", "300"]]},
            ]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert len(records) == 3
        assert records[0]["Name"] == "Alice"
        assert records[1]["Name"] == "Bob"
        assert records[2]["Name"] == "Carol"

    def test_read_records_no_table(self, tmp_path: Path) -> None:
        """测试读取没有表格的页面."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf([{"table": None}])

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert len(records) == 0

    def test_read_records_empty_table(self, tmp_path: Path) -> None:
        """测试读取空表格(无数据行)."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf([{"table": [["Name", "Amount"]]}])

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert len(records) == 0

    def test_read_records_strips_whitespace(self, tmp_path: Path) -> None:
        """测试读取时去除空白字符."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [{"table": [["Name", "Amount"], ["  Alice  ", "  100  "]]}]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert records[0]["Name"] == "Alice"
        assert records[0]["Amount"] == "100"

    def test_read_records_handles_none_values(self, tmp_path: Path) -> None:
        """测试处理 None 值."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [{"table": [["Name", "Amount", "Note"], ["Alice", None, "Normal"]]}]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert records[0]["Name"] == "Alice"
        assert records[0]["Amount"] == ""  # None 转为空字符串
        assert records[0]["Note"] == "Normal"

    def test_read_records_header_with_none(self, tmp_path: Path) -> None:
        """测试表头包含 None 值."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [{"table": [["Name", None, "Date"], ["Alice", "100", "2024-01-01"]]}]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert records[0]["Name"] == "Alice"
        assert records[0][""] == "100"  # None 表头转为空字符串键
        assert records[0]["Date"] == "2024-01-01"

    def test_read_records_mixed_pages(self, tmp_path: Path) -> None:
        """测试混合有表格和无表格的页面."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [
                {"table": [["Name"], ["Alice"]]},
                {"table": None},
                {"table": [["Name"], ["Bob"]]},
            ]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            records = list(reader.read_records(pdf_file))

        assert len(records) == 2
        assert records[0]["Name"] == "Alice"
        assert records[1]["Name"] == "Bob"

    def test_read_captions_and_records_together(self, tmp_path: Path) -> None:
        """测试同时读取标题和记录."""
        pdf_file = tmp_path / "test.pdf"

        mock_pdf = make_mock_pdf(
            [
                {
                    "outside_text": "Header",
                    "table": [["Name"], ["Alice"]],
                }
            ]
        )

        with patch(
            "beancount_daoru.readers.pdf_table.pdfplumber.open",
            return_value=mock_pdf,
        ):
            reader = Reader(table_bbox=(0, 0, 100, 200))
            captions = list(reader.read_captions(pdf_file))
            records = list(reader.read_records(pdf_file))

        assert captions == ["Header"]
        assert records[0]["Name"] == "Alice"
