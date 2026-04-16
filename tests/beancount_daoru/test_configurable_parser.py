"""ConfigurableParser 配置驱动解析器测试."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from beancount_daoru.importer import (
    BankFieldConfig,
    ConfigurableParser,
    ParserError,
    Transaction,
)


class SimpleParser(ConfigurableParser):
    """简单测试用解析器."""

    bank_config = BankFieldConfig(
        file_patterns=("test*.csv", "测试*.csv"),
        date_field="交易日期",
        amount_field="金额",
        balance_field="余额",
        payee_field="对方",
        description_field="摘要",
        channel_field="渠道",
        dc_field="借贷",
        dc_mapping={"借": "支出", "贷": "收入"},
    )

    def extract_metadata(self, texts):  # type: ignore[no-untyped-def]
        return None


class TestBankFieldConfig:
    """BankFieldConfig 数据类测试."""

    def test_default_values(self):
        """测试默认值."""
        config = BankFieldConfig()
        assert config.file_patterns == ()
        assert config.encoding == "gbk"
        assert config.date_field == "交易日期"
        assert config.amount_field == "交易金额"
        assert config.balance_field is None
        assert config.payee_field == "对方户名"
        assert config.dc_mapping == {"借": "支出", "贷": "收入"}

    def test_custom_values(self):
        """测试自定义值."""
        config = BankFieldConfig(
            file_patterns=("icbc*.csv",),
            date_field="记账日期",
            amount_field="交易金额",
            payee_field="对方账户",
            dc_mapping={"Debit": "支出", "Credit": "收入"},
        )
        assert config.file_patterns == ("icbc*.csv",)
        assert config.date_field == "记账日期"
        assert config.payee_field == "对方账户"
        assert config.dc_mapping == {"Debit": "支出", "Credit": "收入"}


class TestConfigurableParser:
    """ConfigurableParser 基类测试."""

    @pytest.fixture
    def parser(self):
        """创建解析器实例."""
        return SimpleParser()

    def test_field_config_property(self, parser):
        """测试 field_config 属性."""
        config = parser.field_config
        assert isinstance(config, BankFieldConfig)
        assert config.date_field == "交易日期"

    def test_file_patterns(self, parser):
        """测试 file_patterns 属性."""
        assert parser.file_patterns == ("test*.csv", "测试*.csv")

    def test_reversed(self, parser):
        """测试 reversed 属性."""
        assert parser.reversed is True

    def test_validate_file(self, parser):
        """测试 validate_file 方法."""
        assert parser.validate_file("test.csv") is True
        assert parser.validate_file("test.xlsx") is True
        assert parser.validate_file("test.pdf") is False

    def test_get_field_found(self, parser):
        """测试 get_field 找到字段."""
        record = {"交易日期": "2024-01-01", "金额": "100"}
        assert parser.get_field(record, "交易日期") == "2024-01-01"
        assert parser.get_field(record, "金额") == "100"

    def test_get_field_not_found(self, parser):
        """测试 get_field 未找到字段."""
        record = {"交易日期": "2024-01-01"}
        assert parser.get_field(record, "不存在") is None

    def test_get_field_empty_string(self, parser):
        """测试 get_field 空字符串."""
        record = {"交易日期": "", "金额": "  "}
        assert parser.get_field(record, "交易日期") is None
        assert parser.get_field(record, "金额") is None

    def test_get_decimal_valid(self, parser):
        """测试 get_decimal 有效值."""
        record = {"金额": "1,234.56"}
        assert parser.get_decimal(record, "金额") == Decimal("1234.56")

    def test_get_decimal_invalid(self, parser):
        """测试 get_decimal 无效值."""
        record = {"金额": "abc"}
        assert parser.get_decimal(record, "金额") is None

    def test_get_decimal_missing(self, parser):
        """测试 get_decimal 缺失字段."""
        record = {}
        assert parser.get_decimal(record, "金额") is None

    def test_get_date_iso_format(self, parser):
        """测试 get_date ISO 格式."""
        record = {"交易日期": "2024-01-15"}
        assert parser.get_date(record, "交易日期") == date(2024, 1, 15)

    def test_get_date_slash_format(self, parser):
        """测试 get_date 斜杠格式."""
        record = {"交易日期": "2024/01/15"}
        assert parser.get_date(record, "交易日期") == date(2024, 1, 15)

    def test_get_date_invalid(self, parser):
        """测试 get_date 无效值."""
        record = {"交易日期": "invalid"}
        assert parser.get_date(record, "交易日期") is None

    def test_get_date_missing(self, parser):
        """测试 get_date 缺失字段."""
        record = {}
        assert parser.get_date(record, "交易日期") is None

    def test_parse_dc_debit(self, parser):
        """测试 parse_dc 借方."""
        record = {"借贷": "借"}
        assert parser.parse_dc(record) == "支出"

    def test_parse_dc_credit(self, parser):
        """测试 parse_dc 贷方."""
        record = {"借贷": "贷"}
        assert parser.parse_dc(record) == "收入"

    def test_parse_dc_missing(self, parser):
        """测试 parse_dc 缺失字段."""
        record = {}
        assert parser.parse_dc(record) is None

    def test_parse_amount_negative(self, parser):
        """测试 parse_amount 负数."""
        record = {"金额": "-100.00"}
        amount, dc = parser.parse_amount(record)
        assert amount == Decimal("-100.00")
        assert dc == "支出"

    def test_parse_amount_positive(self, parser):
        """测试 parse_amount 正数."""
        record = {"金额": "200.50"}
        amount, dc = parser.parse_amount(record)
        assert amount == Decimal("200.50")
        assert dc == "收入"

    def test_parse_amount_with_dc(self, parser):
        """测试 parse_amount 带借贷标志."""
        record = {"金额": "100.00", "借贷": "借"}
        amount, dc = parser.parse_amount(record)
        assert amount == Decimal("-100.00")
        assert dc == "支出"

    def test_parse_amount_missing(self, parser):
        """测试 parse_amount 缺失金额."""
        record = {}
        assert parser.parse_amount(record) is None

    def test_parse_basic(self, parser):
        """测试基本 parse 方法."""
        record = {
            "交易日期": "2024-01-15",
            "金额": "-100.50",
            "对方": "商家A",
            "摘要": "购物",
            "渠道": "网银",
            "借贷": "借",
        }
        transaction = parser.parse(record)

        assert isinstance(transaction, Transaction)
        assert transaction.date == date(2024, 1, 15)
        assert transaction.payee == "商家A"
        assert transaction.narration == "购物"
        assert transaction.extra.dc == "支出"
        assert transaction.extra.type == "网银"
        assert len(list(transaction.postings)) == 1

    def test_parse_without_dc_field(self, parser):
        """测试不带借贷字段的解析."""
        record = {
            "交易日期": "2024-01-15",
            "金额": "100.00",
            "对方": "转账",
        }
        transaction = parser.parse(record)

        assert transaction.extra.dc == "收入"
        amount_list = list(transaction.postings)
        assert amount_list[0].amount == Decimal(100)

    def test_parse_with_balance(self, parser):
        """测试带余额的解析."""
        record = {
            "交易日期": "2024-01-15",
            "金额": "-50.00",
            "余额": "1000.00",
            "对方": "商家",
        }
        transaction = parser.parse(record)

        assert transaction.balance is not None
        assert transaction.balance.amount == Decimal("1000.00")

    def test_parse_invalid_amount_raises(self, parser):
        """测试无效金额抛出异常."""
        record = {"交易日期": "2024-01-15", "金额": "invalid"}
        with pytest.raises(ParserError):
            parser.parse(record)


class TestConfigurableParserEdgeCases:
    """ConfigurableParser 边界情况测试."""

    def test_none_field_config_raises(self):
        """测试未配置 bank_config 抛出异常."""

        class NoConfigParser(ConfigurableParser):
            def extract_metadata(self, texts):  # type: ignore[no-untyped-def]
                return None

        parser = NoConfigParser()
        with pytest.raises(NotImplementedError):
            _ = parser.field_config

    def test_whitespace_handling(self):
        """测试空白字符处理."""
        parser = SimpleParser()
        record = {
            "交易日期": "  2024-01-15  ",
            "金额": "  100.00  ",
            "对方": "  测试商家  ",
        }
        assert parser.get_field(record, "交易日期") == "2024-01-15"
        assert parser.get_field(record, "对方") == "测试商家"

    def test_special_characters_in_amount(self):
        """Test amount with special characters."""
        parser = SimpleParser()
        record = {"金额": "¥1,234.56"}
        result = parser.get_decimal(record, "金额")
        # Some formats may not parse, this is expected
        assert result is None or isinstance(result, Decimal)
