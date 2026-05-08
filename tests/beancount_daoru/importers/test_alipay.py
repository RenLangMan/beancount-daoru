"""测试支付宝导入器模块."""

from datetime import date, datetime
from pathlib import Path

import pytest

from beancount_daoru.importer import Metadata
from beancount_daoru.importers.alipay import Parser as AlipayParser
from beancount_daoru.utils import TZ_UTC8


class TestAlipayParser:
    """测试支付宝解析器."""

    @pytest.fixture
    def parser(self) -> AlipayParser:
        """创建支付宝解析器实例."""
        return AlipayParser()

    @pytest.fixture
    def sample_metadata(self) -> Metadata:
        """创建示例元数据."""
        return Metadata(
            account="test@example.com",
            date=date(2024, 1, 31),
        )

    def test_reversed_property(self, parser: AlipayParser) -> None:
        """测试 reversed 属性返回 True."""
        assert parser.reversed is True

    def test_file_patterns_property(self, parser: AlipayParser) -> None:
        """测试 file_patterns 属性."""
        patterns = parser.file_patterns
        assert "支付宝交易明细*.csv" in patterns
        assert "alipay*.csv" in patterns

    def test_extract_metadata(self, parser: AlipayParser) -> None:
        """测试 extract_metadata 方法."""
        texts = iter(
            [
                "导出信息:",
                "姓名:xx",
                "支付宝账户:test@example.com",
                "起始时间:[2024-01-01 00:00:00]",
                "终止时间:[2024-01-31 23:59:59]",
            ]
        )
        metadata = parser.extract_metadata(texts)

        assert metadata.account == "test@example.com"
        assert metadata.date == date(2024, 1, 31)

    def test_extract_metadata_missing_account(self, parser: AlipayParser) -> None:
        """测试缺少账户信息时抛出异常."""
        texts = iter(
            [
                "导出信息:",
                "终止时间:[2024-01-31 23:59:59]",
            ]
        )
        with pytest.raises(ValueError, match="无法从文件中提取账户信息"):
            parser.extract_metadata(texts)

    def test_extract_metadata_missing_date(self, parser: AlipayParser) -> None:
        """测试缺少日期信息时抛出异常."""
        texts = iter(
            [
                "支付宝账户:test@example.com",
            ]
        )
        with pytest.raises(ValueError, match="无法从文件中提取日期信息"):
            parser.extract_metadata(texts)


class TestAlipayParserValidateFile:
    """测试支付宝文件验证功能."""

    @pytest.fixture
    def parser(self) -> AlipayParser:
        """创建支付宝解析器实例."""
        return AlipayParser()

    def test_validate_csv_file(
        self,
        parser: AlipayParser,
        tmp_path: Path,
    ) -> None:
        """测试验证有效的 CSV 文件."""
        csv_file = tmp_path / "支付宝交易明细(20240101-20240131).csv"
        csv_file.write_text(
            "交易时间,交易对方,金额,收/支\n2024-01-15 12:00:00,Test,100.00,支出\n",
            encoding="gbk",
        )

        assert parser.validate_file(str(csv_file)) is True

    def test_validate_xlsx_file(
        self,
        parser: AlipayParser,
        tmp_path: Path,
    ) -> None:
        """测试验证有效的 Excel 文件扩展名."""
        # 注意: 完整测试需要 pyexcel-xlsx 插件
        # 这里只测试文件名验证逻辑
        xlsx_file = tmp_path / "alipay_2024.xlsx"
        xlsx_file.write_bytes(b"")  # 创建空文件

        # 基础扩展名和文件名检查应该通过
        assert parser.validate_file(str(xlsx_file)) is False  # 空文件无法读取表头

    def test_validate_invalid_extension(
        self,
        parser: AlipayParser,
        tmp_path: Path,
    ) -> None:
        """测试无效文件扩展名返回 False."""
        txt_file = tmp_path / "支付宝交易明细.txt"
        txt_file.write_text("content")

        assert parser.validate_file(str(txt_file)) is False

    def test_validate_invalid_filename(
        self,
        parser: AlipayParser,
        tmp_path: Path,
    ) -> None:
        """测试无效文件名返回 False."""
        csv_file = tmp_path / "other_file.csv"
        csv_file.write_text("content", encoding="utf-8")

        assert parser.validate_file(str(csv_file)) is False

    def test_validate_missing_headers(
        self,
        parser: AlipayParser,
        tmp_path: Path,
    ) -> None:
        """测试缺少必需表头返回 False."""
        csv_file = tmp_path / "支付宝交易明细.csv"
        csv_file.write_text(
            "交易时间,交易对方,备注\n2024-01-15,Test,test\n",
            encoding="utf-8",
        )

        assert parser.validate_file(str(csv_file)) is False


class TestAlipayParserPaymentSplits:
    """测试支付拆分功能."""

    @pytest.fixture
    def parser(self) -> AlipayParser:
        """创建支付宝解析器实例."""
        return AlipayParser()

    def test_single_payment_returns_none(self, parser: AlipayParser) -> None:
        """测试单一支付方式返回 None."""
        record = {"收/付款方式": "农业银行储蓄卡(6773)"}
        result = parser._extract_payment_splits(record)
        assert result is None

    def test_combined_payment_with_discount(self, parser: AlipayParser) -> None:
        """测试带优惠的组合支付."""
        record = {"收/付款方式": "农业银行储蓄卡(6773)&碰一下立减"}
        result = parser._extract_payment_splits(record)

        assert result is not None
        assert len(result) == 2

        # 第一个是主要支付方式
        assert result[0]["payment_method"] == "农业银行储蓄卡(6773)"
        assert result[0]["is_discount"] is False

        # 第二个是优惠
        assert result[1]["payment_method"] == "碰一下立减"
        assert result[1]["is_discount"] is True

    def test_combined_payment_multiple(self, parser: AlipayParser) -> None:
        """测试多方式组合支付."""
        record = {"收/付款方式": "农业银行储蓄卡(6773)&余额&优惠券"}
        result = parser._extract_payment_splits(record)

        assert result is not None
        assert len(result) == 3

    def test_empty_payment_method(self, parser: AlipayParser) -> None:
        """测试空支付方式返回 None."""
        record = {"收/付款方式": ""}
        result = parser._extract_payment_splits(record)
        assert result is None

    def test_discount_keywords(self, parser: AlipayParser) -> None:
        """测试各种优惠关键词识别."""
        keywords = ["立减", "红包", "优惠券", "减免", "折扣"]
        for keyword in keywords:
            record = {"收/付款方式": f"银行卡&{keyword}"}
            result = parser._extract_payment_splits(record)
            assert result is not None
            assert result[1]["is_discount"] is True


class TestAlipayParserParse:
    """测试支付宝解析器 parse 方法."""

    @pytest.fixture
    def parser(self) -> AlipayParser:
        """创建支付宝解析器实例."""
        return AlipayParser()

    def test_parse_basic_transaction(self, parser: AlipayParser) -> None:
        """测试解析基本交易."""
        record = {
            "交易时间": "2024-01-15 12:30:45",
            "交易对方": "测试商家",
            "商品说明": "商品购买",
            "金额": "100.00",
            "收/支": "支出",
            "收/付款方式": "余额宝",
            "交易状态": "交易成功",
            "交易分类": "日用百货",
            "对方账号": "test@alipay.com",
            "备注": "测试备注",
        }

        tx = parser.parse(record)

        assert tx.date == date(2024, 1, 15)
        assert tx.payee == "测试商家"
        assert tx.narration == "商品购买"
        assert tx.extra.time.hour == 12
        assert tx.extra.datetime_str == "2024-01-15 12:30:45"
        assert tx.extra.dc == "支出"
        assert tx.extra.type == "日用百货"
        assert tx.extra.status == "交易成功"

    def test_parse_with_source_info(self, parser: AlipayParser) -> None:
        """测试解析带源文件信息的记录."""
        record = {
            "交易时间": "2024-01-15 12:00:00",
            "交易对方": "Test",
            "商品说明": "Test",
            "金额": "50.00",
            "收/支": "支出",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "交易分类": "日用百货",
            "对方账号": "/",
            "备注": "",
            "source_file": "test.csv",
            "row_number": "26",
        }

        tx = parser.parse(record)

        assert tx.extra.source_file == "test.csv"
        assert tx.extra.row_number == 26

    def test_parse_with_payment_splits(self, parser: AlipayParser) -> None:
        """测试解析带支付拆分的交易."""
        record = {
            "交易时间": "2024-01-15 12:00:00",
            "交易对方": "Test",
            "商品说明": "Test",
            "金额": "100.00",
            "收/支": "支出",
            "收/付款方式": "银行卡&红包",
            "交易状态": "交易成功",
            "交易分类": "日用百货",
            "对方账号": "/",
            "备注": "",
        }

        tx = parser.parse(record)

        assert tx.extra.payment_splits is not None
        assert len(tx.extra.payment_splits) == 2

    def test_parse_timestamp_generated(self, parser: AlipayParser) -> None:
        """测试时间戳生成."""
        # from beancount_daoru.utils import TZ_UTC8

        record = {
            "交易时间": "2024-01-15 12:00:00",
            "交易对方": "Test",
            "商品说明": "Test",
            "金额": "50.00",
            "收/支": "支出",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "交易分类": "日用百货",
            "对方账号": "/",
            "备注": "",
        }

        tx = parser.parse(record)

        # 2024-01-15 12:00:00 的 Unix 时间戳(使用 UTC+8 时区)
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=TZ_UTC8)
        expected_timestamp = int(dt.timestamp())
        assert tx.extra.timestamp == expected_timestamp


class TestAlipayParserEdgeCases:
    """测试支付宝解析器边界情况."""

    @pytest.fixture
    def parser(self) -> AlipayParser:
        """创建支付宝解析器实例."""
        return AlipayParser()

    def test_parse_empty_record(self, parser: AlipayParser) -> None:
        """测试解析空记录."""
        record: dict[str, str] = {}

        # 应该抛出验证错误
        with pytest.raises((ValueError, Exception)):
            parser.parse(record)

    def test_parse_invalid_amount(self, parser: AlipayParser) -> None:
        """测试解析无效金额."""
        record = {
            "交易时间": "2024-01-15 12:00:00",
            "交易对方": "Test",
            "商品说明": "Test",
            "金额": "invalid",
            "收/支": "支出",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "交易分类": "日用百货",
            "对方账号": "/",
            "备注": "",
        }

        with pytest.raises((ValueError, Exception)):
            parser.parse(record)

    def test_parse_special_characters_in_payee(self, parser: AlipayParser) -> None:
        """测试解析带特殊字符的收款方."""
        record = {
            "交易时间": "2024-01-15 12:00:00",
            "交易对方": "测试&商家(有限公司)",
            "商品说明": "商品&服务",
            "金额": "100.00",
            "收/支": "支出",
            "收/付款方式": "余额宝",
            "交易状态": "交易成功",
            "交易分类": "日用百货",
            "对方账号": "/",
            "备注": "",
        }

        tx = parser.parse(record)
        assert tx.payee == "测试&商家(有限公司)"
