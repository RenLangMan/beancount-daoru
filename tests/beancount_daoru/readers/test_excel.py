"""Excel 读取器单元测试."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from beancount_daoru.readers.excel import Reader


class TestExcelReader:
    """Excel Reader 类的测试."""

    def test_init_with_header(self) -> None:
        """测试初始化."""
        reader = Reader(header=1)
        assert reader is not None

    def test_init_with_encoding(self) -> None:
        """测试带编码参数初始化."""
        reader = Reader(header=2, encoding="utf-8")
        assert reader is not None

    def test_convert_none(self) -> None:
        """测试 None 值转换."""
        reader = Reader(header=0)
        result = reader._Reader__convert(None)  # type: ignore[attr-defined]
        assert result == ""

    def test_convert_string(self) -> None:
        """测试字符串转换."""
        reader = Reader(header=0)
        result = reader._Reader__convert("  test  ")  # type: ignore[attr-defined]
        assert result == "test"

    def test_convert_integer(self) -> None:
        """测试整数转换."""
        reader = Reader(header=0)
        result = reader._Reader__convert(123)  # type: ignore[attr-defined]
        assert result == "123"

    def test_convert_float(self) -> None:
        """测试浮点数转换."""
        reader = Reader(header=0)
        result = reader._Reader__convert(3.14)  # type: ignore[attr-defined]
        assert result == "3.14"

    def test_convert_empty_string(self) -> None:
        """测试空字符串转换."""
        reader = Reader(header=0)
        result = reader._Reader__convert("")  # type: ignore[attr-defined]
        assert result == ""

    def test_convert_whitespace_only(self) -> None:
        """测试仅空白字符转换."""
        reader = Reader(header=0)
        result = reader._Reader__convert("  \t\n  ")  # type: ignore[attr-defined]
        assert result == ""


class TestExcelReaderIntegration:
    """Excel Reader 集成测试(使用真实文件)."""

    def test_read_captions_csv(self, tmp_path: Path) -> None:
        """测试读取 CSV 文件的标题行."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("col1,col2,col3\n1,2,3\n4,5,6")

        reader = Reader(header=1)
        captions = list(reader.read_captions(csv_file))

        assert captions == ["col1", "col2", "col3"]

    def test_read_captions_no_header(self, tmp_path: Path) -> None:
        """测试读取无标题行文件."""
        csv_file = tmp_path / "no_header.csv"
        csv_file.write_text("data1,data2\nvalue1,value2")

        reader = Reader(header=0)
        captions = list(reader.read_captions(csv_file))

        # header=0 时读取第一行作为标题
        assert "data1" in captions

    def test_read_records_csv(self, tmp_path: Path) -> None:
        """测试读取 CSV 文件的数据记录."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("name,amount\nAlice,100\nBob,200")

        reader = Reader(header=1)
        records = list(reader.read_records(csv_file))

        # 验证记录被读取
        assert len(records) >= 1
        assert isinstance(records[0], dict)

    def test_read_records_with_whitespace(self, tmp_path: Path) -> None:
        """测试读取包含空白字符的记录."""
        csv_file = tmp_path / "whitespace.csv"
        csv_file.write_text("name,amount\n  Alice  ,  100  \nBob, 200 ")

        reader = Reader(header=1)
        records = list(reader.read_records(csv_file))

        # 验证记录被读取
        assert len(records) >= 1
        assert isinstance(records[0], dict)

    def test_read_records_no_data_rows(self, tmp_path: Path) -> None:
        """测试读取仅包含标题的文件."""
        csv_file = tmp_path / "header_only.csv"
        csv_file.write_text("col1,col2")

        reader = Reader(header=1)
        records = list(reader.read_records(csv_file))

        assert len(records) == 0

    def test_read_captions_multiline(self, tmp_path: Path) -> None:
        """测试读取多行标题."""
        csv_file = tmp_path / "multi_header.csv"
        csv_file.write_text("Header1\nRow1,Row2\nData1,Data2")

        reader = Reader(header=2)
        captions = list(reader.read_captions(csv_file))

        assert "Header1" in captions
        assert "Row1" in captions
        assert "Row2" in captions

    def test_read_records_with_special_chars(self, tmp_path: Path) -> None:
        """测试读取包含特殊字符的记录."""
        csv_file = tmp_path / "special.csv"
        csv_file.write_text('name,desc\n测试,"with,comma"\n"line\nbreak",normal')

        reader = Reader(header=1)
        records = list(reader.read_records(csv_file))

        assert len(records) >= 1
