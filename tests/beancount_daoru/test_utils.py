"""测试 beancount_daoru.utils 模块."""

import zipfile
from datetime import date

import pytest

from beancount_daoru.utils import (
    extract_zip_file,
    parse_date_flexible,
    parse_datetime_flexible,
)


class TestParseDatetimeFlexible:
    """测试 parse_datetime_flexible 函数."""

    def test_parse_full_format(self) -> None:
        """测试完整格式解析."""
        result = parse_datetime_flexible("2023-02-12 21:32:14")
        assert result is not None
        assert result.year == 2023
        assert result.month == 2
        assert result.day == 12
        assert result.hour == 21
        assert result.minute == 32
        assert result.second == 14

    def test_parse_date_only(self) -> None:
        """测试仅日期格式解析."""
        result = parse_datetime_flexible("2023-02-12")
        assert result is not None
        assert result.year == 2023
        assert result.month == 2
        assert result.day == 12

    def test_parse_slash_format(self) -> None:
        """测试斜杠分隔格式解析."""
        result = parse_datetime_flexible("2023/02/12 21:32:14")
        assert result is not None
        assert result.year == 2023
        assert result.month == 2
        assert result.day == 12
        assert result.hour == 21
        assert result.minute == 32
        assert result.second == 14

    def test_parse_short_format(self) -> None:
        """测试短格式解析(无年份,使用当前年份)."""
        result = parse_datetime_flexible("02/12 21:32:14")
        assert result is not None
        assert result.month == 2
        assert result.day == 12
        assert result.hour == 21
        assert result.minute == 32
        assert result.second == 14

    def test_parse_empty_string(self) -> None:
        """测试空字符串返回 None."""
        assert parse_datetime_flexible("") is None

    def test_parse_none(self) -> None:
        """测试 None 输入返回 None."""
        assert parse_datetime_flexible(None) is None  # type: ignore[arg-type]

    def test_parse_invalid_format(self) -> None:
        """测试无效格式返回 None."""
        assert parse_datetime_flexible("invalid-date") is None


class TestParseDateFlexible:
    """测试 parse_date_flexible 函数."""

    def test_parse_full_format(self) -> None:
        """测试完整格式解析."""
        result = parse_date_flexible("2023-02-12")
        assert result == date(2023, 2, 12)

    def test_parse_with_time(self) -> None:
        """测试带时间的日期解析."""
        result = parse_date_flexible("2023-02-12 21:32:14")
        assert result == date(2023, 2, 12)

    def test_parse_empty_string(self) -> None:
        """测试空字符串返回 None."""
        assert parse_date_flexible("") is None

    def test_parse_invalid(self) -> None:
        """测试无效格式返回 None."""
        assert parse_date_flexible("invalid") is None


class TestExtractZipFile:
    """测试 extract_zip_file 函数."""

    def test_extract_simple_zip(self, tmp_path: "pytest.TempdirFactory") -> None:
        """测试简单 ZIP 文件解压."""
        # 创建测试 ZIP 文件
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file1.txt", "content1")
            zf.writestr("file2.txt", "content2")

        # 解压
        extract_dir = tmp_path / "extracted"
        extracted = extract_zip_file(zip_path, extract_dir)

        assert len(extracted) == 2
        assert (extract_dir / "file1.txt").exists()
        assert (extract_dir / "file2.txt").exists()

    def test_extract_with_subdirectory(self, tmp_path: "pytest.TempdirFactory") -> None:
        """测试带子目录的 ZIP 文件解压."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("subdir/file.txt", "content")

        extract_dir = tmp_path / "extracted"
        extracted = extract_zip_file(zip_path, extract_dir)

        assert len(extracted) == 1
        assert (extract_dir / "subdir" / "file.txt").exists()

    def test_extract_nonexistent_file(self, tmp_path: "pytest.TempdirFactory") -> None:
        """测试解压不存在的文件抛出异常."""
        with pytest.raises(FileNotFoundError, match="ZIP 文件不存在"):
            extract_zip_file(tmp_path / "nonexistent.zip", tmp_path / "extracted")

    def test_extract_invalid_zip(self, tmp_path: "pytest.TempdirFactory") -> None:
        """测试解压无效文件抛出异常."""
        invalid_file = tmp_path / "invalid.zip"
        invalid_file.write_text("not a zip file")

        with pytest.raises(zipfile.BadZipFile, match="不是有效的 ZIP 格式"):
            extract_zip_file(invalid_file, tmp_path / "extracted")

    def test_extract_skips_directories(self, tmp_path: "pytest.TempdirFactory") -> None:
        """测试跳过目录条目."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            # 添加目录条目
            zf.writestr("subdir/", "")
            zf.writestr("subdir/file.txt", "content")

        extract_dir = tmp_path / "extracted"
        extracted = extract_zip_file(zip_path, extract_dir)

        # 应该只包含文件,不包含目录
        assert len(extracted) == 1
        assert (extract_dir / "subdir" / "file.txt").exists()
