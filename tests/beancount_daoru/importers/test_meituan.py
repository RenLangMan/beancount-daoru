import datetime
from decimal import Decimal

import pytest

from beancount_daoru.importer import Extra, Metadata, ParserError, Posting, Transaction
from beancount_daoru.importers.meituan import Importer, Parser, _validate_str


@pytest.fixture(scope="module")
def parser() -> Parser:
    """创建美团解析器实例."""
    return Parser()


class TestExtractMetadata:
    """测试美团元数据提取."""

    def test_extract_metadata(self, parser: Parser) -> None:
        """测试正常提取美团用户名和终止时间."""
        caption = (
            "美团账单\n"
            "美团用户名：[测试用户]\n"
            "起始时间:[2024-01-01] 终止时间:[2024-01-31]\n"
        )
        metadata = parser.extract_metadata(iter([caption]))
        assert metadata == Metadata(
            account="测试用户",
            date=datetime.date(2024, 1, 31),
        )

    def test_extract_metadata_with_colon(self, parser: Parser) -> None:
        """测试中文冒号格式."""
        lines = [
            "美团用户名:[我的账号]",
            "起始时间:[2024-06-01] 终止时间:[2024-06-30]",
        ]
        metadata = parser.extract_metadata(iter(lines))
        assert metadata == Metadata(
            account="我的账号",
            date=datetime.date(2024, 6, 30),
        )

    def test_extract_metadata_missing_account(self, parser: Parser) -> None:
        """测试缺少账户信息时抛出 ValueError."""
        caption = "终止时间:[2024-01-31]"
        with pytest.raises(ValueError, match="无法从文件中提取账户信息"):
            _ = parser.extract_metadata(iter([caption]))

    def test_extract_metadata_missing_date(self, parser: Parser) -> None:
        """测试缺少日期信息时抛出 ValueError."""
        caption = "美团用户名:[测试用户]"
        with pytest.raises(ValueError, match="无法从文件中提取日期信息"):
            _ = parser.extract_metadata(iter([caption]))


class TestReversed:
    """测试美团解析器 reversed 属性."""

    def test_reversed(self, parser: Parser) -> None:
        """美团记录为倒序,应返回 True."""
        assert parser.reversed is True


PARSE_PARAMS_LIST = [
    (
        # 支出 + 支付类型 + 无对方账户
        {
            "交易成功时间": "2024-01-15 12:30:00",
            "交易类型": "支付",
            "订单标题": "外卖订单",
            "收/支": "支出",
            "实付金额": "¥35.50",
            "支付方式": "微信支付",
            "备注": "/",
        },
        Transaction(
            date=datetime.date(2024, 1, 15),
            extra=Extra(
                time=datetime.time(12, 30, 0),
                dc="支出",
                type="支付",
                remarks=None,
            ),
            payee="美团",
            narration="外卖订单",
            postings=(
                Posting(account="微信支付", amount=Decimal("-35.50"), currency="¥"),
            ),
        ),
    ),
    (
        # 收入 + 退款类型 + 无对方账户
        {
            "交易成功时间": "2024-01-20 09:00:00",
            "交易类型": "退款",
            "订单标题": "退款订单",
            "收/支": "收入",
            "实付金额": "¥25.00",
            "支付方式": "微信支付",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 1, 20),
            extra=Extra(
                time=datetime.time(9, 0, 0),
                dc="收入",
                type="退款",
                remarks=None,
            ),
            payee="美团",
            narration="退款订单",
            postings=(
                Posting(account="微信支付", amount=Decimal("25.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 还款 + 美团月付还款 + 有对方账户
        {
            "交易成功时间": "2024-02-01 10:00:00",
            "交易类型": "还款",
            "订单标题": "【美团月付】主动还款-本期账单",
            "收/支": "支出",
            "实付金额": "¥500.00",
            "支付方式": "银行卡",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 1),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc="支出",
                type="还款",
                remarks=None,
            ),
            payee="美团",
            narration="【美团月付】主动还款-本期账单",
            postings=(
                Posting(account="银行卡", amount=Decimal("-500.00"), currency="¥"),
                Posting(account="美团月付", amount=Decimal("500.00"), currency="¥"),
            ),
        ),
    ),
]


@pytest.mark.parametrize(("record", "transaction"), PARSE_PARAMS_LIST)
def test_parse(
    parser: Parser, record: dict[str, str], transaction: Transaction
) -> None:
    """测试解析美团交易记录.

    参数化测试各种场景:
        - 支出 + 支付
        - 收入 + 退款
        - 还款 + 美团月付
    """
    assert parser.parse(record) == transaction


class TestParseAmount:
    """测试金额解析."""

    def test_parse_amount_expenditure(self, parser: Parser) -> None:
        """测试支出金额为负数."""
        record = {
            "交易成功时间": "2024-01-01 00:00:00",
            "交易类型": "支付",
            "订单标题": "测试",
            "收/支": "支出",
            "实付金额": "¥100.00",
            "支付方式": "微信支付",
            "备注": "/",
        }
        txn = parser.parse(record)
        postings = tuple(txn.postings)
        assert postings[0].amount == Decimal("-100.00")

    def test_parse_amount_income(self, parser: Parser) -> None:
        """测试收入金额为正数."""
        record = {
            "交易成功时间": "2024-01-01 00:00:00",
            "交易类型": "退款",
            "订单标题": "测试",
            "收/支": "收入",
            "实付金额": "¥50.00",
            "支付方式": "微信支付",
            "备注": "/",
        }
        txn = parser.parse(record)
        postings = tuple(txn.postings)
        assert postings[0].amount == Decimal("50.00")


class TestParseCounterParty:
    """测试对方账户解析."""

    def test_parse_counter_party_payment(self, parser: Parser) -> None:
        """测试支付类型无对方账户."""
        record = {
            "交易成功时间": "2024-01-01 00:00:00",
            "交易类型": "支付",
            "订单标题": "外卖",
            "收/支": "支出",
            "实付金额": "¥30.00",
            "支付方式": "微信支付",
            "备注": "/",
        }
        txn = parser.parse(record)
        postings = tuple(txn.postings)
        assert len(postings) == 1

    def test_parse_counter_party_refund(self, parser: Parser) -> None:
        """测试退款类型无对方账户."""
        record = {
            "交易成功时间": "2024-01-01 00:00:00",
            "交易类型": "退款",
            "订单标题": "退款",
            "收/支": "收入",
            "实付金额": "¥20.00",
            "支付方式": "微信支付",
            "备注": "/",
        }
        txn = parser.parse(record)
        postings = tuple(txn.postings)
        assert len(postings) == 1

    def test_parse_counter_party_meituan_monthly_pay(self, parser: Parser) -> None:
        """测试美团月付还款有对方账户."""
        record = {
            "交易成功时间": "2024-01-01 00:00:00",
            "交易类型": "还款",
            "订单标题": "【美团月付】主动还款-本期账单",
            "收/支": "支出",
            "实付金额": "¥200.00",
            "支付方式": "银行卡",
            "备注": "",
        }
        txn = parser.parse(record)
        postings = tuple(txn.postings)
        assert len(postings) == 2
        assert postings[1].account == "美团月付"


class TestParseError:
    """测试解析错误."""

    def test_parse_error_unknown_dc(self, parser: Parser) -> None:
        """测试未知的收/支类型抛出 ParserError."""
        record = {
            "交易成功时间": "2024-01-01 00:00:00",
            "交易类型": "支付",
            "订单标题": "测试",
            "收/支": "其他",
            "实付金额": "¥1.00",
            "支付方式": "微信支付",
            "备注": "",
        }
        with pytest.raises(ParserError):
            _ = parser.parse(record)

    def test_parse_error_unknown_type_and_narration(self, parser: Parser) -> None:
        """测试未知的交易类型+订单标题组合抛出 ParserError."""
        record = {
            "交易成功时间": "2024-01-01 00:00:00",
            "交易类型": "其他类型",
            "订单标题": "未知标题",
            "收/支": "支出",
            "实付金额": "¥1.00",
            "支付方式": "微信支付",
            "备注": "",
        }
        with pytest.raises(ParserError):
            _ = parser.parse(record)


def test_importer_init() -> None:
    """测试 Importer 初始化."""
    importer = Importer(account_mapping={}, currency_mapping={})
    assert importer._Importer__filename_pattern is not None
    assert importer._Importer__reader is not None
    assert importer._Importer__parser is not None


def test_validate_str_with_none() -> None:
    """Test _validate_str handles None value."""
    result = _validate_str(None)
    assert result is None


def test_validate_str_with_empty() -> None:
    """Test _validate_str handles empty string."""
    result = _validate_str("")
    assert result is None


def test_validate_str_with_slash() -> None:
    """Test _validate_str handles slash."""
    result = _validate_str("/")
    assert result is None


def test_validate_str_with_normal_value() -> None:
    """Test _validate_str handles normal value."""
    result = _validate_str("正常内容")
    assert result == "正常内容"
