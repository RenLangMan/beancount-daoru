import datetime
from decimal import Decimal

import pytest

from beancount_daoru.importer import Extra, Metadata, ParserError, Posting, Transaction
from beancount_daoru.importers.jd import Parser


@pytest.fixture(scope="module")
def parser() -> Parser:
    """创建京东解析器实例."""
    return Parser()


class TestExtractMetadata:
    """测试京东元数据提取."""

    def test_extract_metadata(self, parser: Parser) -> None:
        """测试正常提取京东账号名和日期区间."""
        caption = (
            "京东交易流水\n京东账号名:jduser123\n日期区间:2024-01-01 至 2024-01-31\n"
        )
        metadata = parser.extract_metadata(iter([caption]))
        assert metadata == Metadata(
            account="jduser123",
            date=datetime.date(2024, 1, 31),
        )

    def test_extract_metadata_with_colon(self, parser: Parser) -> None:
        """测试中文冒号格式."""
        lines = [
            "京东账号名：jduser456",
            "日期区间：2024-06-01 至 2024-06-30",
        ]
        metadata = parser.extract_metadata(iter(lines))
        assert metadata == Metadata(
            account="jduser456",
            date=datetime.date(2024, 6, 30),
        )

    def test_extract_metadata_missing_account(self, parser: Parser) -> None:
        """测试缺少账号名时抛出 ValueError."""
        caption = "日期区间:2024-01-01 至 2024-01-31"
        with pytest.raises(ValueError, match="无法从文件中提取账户信息"):
            _ = parser.extract_metadata(iter([caption]))

    def test_extract_metadata_missing_date(self, parser: Parser) -> None:
        """测试缺少日期区间时抛出 ValueError."""
        caption = "京东账号名:jduser123"
        with pytest.raises(ValueError, match="无法从文件中提取日期信息"):
            _ = parser.extract_metadata(iter([caption]))


class TestReversed:
    """测试京东解析器 reversed 属性."""

    def test_reversed(self, parser: Parser) -> None:
        """京东记录为倒序,应返回 True."""
        assert parser.reversed is True


PARSE_PARAMS_LIST = [
    (
        # 支出 + 交易成功
        {
            "交易时间": "2024-01-15 10:30:00",
            "商户名称": "京东商城",
            "交易说明": "购买商品",
            "金额": "199.00",
            "收/付款方式": "京东白条",
            "交易状态": "交易成功",
            "收/支": "支出",
            "交易分类": "商品",
            "备注": "/",
        },
        Transaction(
            date=datetime.date(2024, 1, 15),
            extra=Extra(
                time=datetime.time(10, 30, 0),
                dc="支出",
                status="交易成功",
                type="商品",
                remarks="/",  # JD 的 _empty_to_none 只转换空字符串, 不转换 "/"
            ),
            payee="京东商城",
            narration="购买商品",
            postings=(Posting(account="京东白条", amount=Decimal("-199.00")),),
        ),
    ),
    (
        # 不计收支 + 交易成功
        {
            "交易时间": "2024-02-01 09:00:00",
            "商户名称": "京东金融",
            "交易说明": "转入小金库",
            "金额": "5000.00",
            "收/付款方式": "银行卡",
            "交易状态": "交易成功",
            "收/支": "不计收支",
            "交易分类": "理财",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 1),
            extra=Extra(
                time=datetime.time(9, 0, 0),
                dc="不计收支",
                status="交易成功",
                type="理财",
                remarks=None,  # 空字符串被 _empty_to_none 转为 None
            ),
            payee="京东金融",
            narration="转入小金库",
            postings=(Posting(account="银行卡", amount=Decimal("-5000.00")),),
        ),
    ),
    (
        # 不计收支 + 退款成功
        {
            "交易时间": "2024-02-10 14:00:00",
            "商户名称": "京东商城",
            "交易说明": "退货退款",
            "金额": "88.88",
            "收/付款方式": "京东白条",
            "交易状态": "退款成功",
            "收/支": "不计收支",
            "交易分类": "退款",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 10),
            extra=Extra(
                time=datetime.time(14, 0, 0),
                dc="不计收支",
                status="退款成功",
                type="退款",
                remarks=None,
            ),
            payee="京东商城",
            narration="退货退款",
            postings=(Posting(account="京东白条", amount=Decimal("88.88")),),
        ),
    ),
    (
        # 支出 + 金额含状态标记(应被移除)
        {
            "交易时间": "2024-03-01 11:00:00",
            "商户名称": "京东超市",
            "交易说明": "购买日用品",
            "金额": "56.50(已出账)",
            "收/付款方式": "银行卡",
            "交易状态": "交易成功",
            "收/支": "支出",
            "交易分类": "商品",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 3, 1),
            extra=Extra(
                time=datetime.time(11, 0, 0),
                dc="支出",
                status="交易成功",
                type="商品",
                remarks=None,
            ),
            payee="京东超市",
            narration="购买日用品",
            postings=(Posting(account="银行卡", amount=Decimal("-56.50")),),
        ),
    ),
    (
        # 支出 + 商户名称为空
        {
            "交易时间": "2024-04-01 08:00:00",
            "商户名称": "",
            "交易说明": "自动扣款",
            "金额": "10.00",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "收/支": "支出",
            "交易分类": "服务",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 4, 1),
            extra=Extra(
                time=datetime.time(8, 0, 0),
                dc="支出",
                status="交易成功",
                type="服务",
                remarks=None,
            ),
            payee=None,  # 空字符串被 _empty_to_none 转为 None
            narration="自动扣款",
            postings=(Posting(account="余额", amount=Decimal("-10.00")),),
        ),
    ),
]


@pytest.mark.parametrize(("record", "transaction"), PARSE_PARAMS_LIST)
def test_parse(
    parser: Parser, record: dict[str, str], transaction: Transaction
) -> None:
    """测试解析京东交易记录.

    参数化测试各种场景:
        - 支出 + 交易成功
        - 不计收支 + 交易成功
        - 不计收支 + 退款成功
        - 金额含状态标记
        - 商户名称为空
    """
    assert parser.parse(record) == transaction


class TestParseError:
    """测试解析错误."""

    def test_parse_error_unknown_dc_status(self, parser: Parser) -> None:
        """测试未知的收支+状态组合抛出 ParserError."""
        record = {
            "交易时间": "2024-01-01 00:00:00",
            "商户名称": "/",
            "交易说明": "/",
            "金额": "1.00",
            "收/付款方式": "银行卡",
            "交易状态": "处理中",
            "收/支": "收入",
            "交易分类": "/",
            "备注": "",
        }
        with pytest.raises(ParserError):
            _ = parser.parse(record)

    def test_parse_error_expenditure_refund_success(self, parser: Parser) -> None:
        """测试支出+退款成功的组合抛出 ParserError."""
        record = {
            "交易时间": "2024-01-01 00:00:00",
            "商户名称": "/",
            "交易说明": "/",
            "金额": "1.00",
            "收/付款方式": "银行卡",
            "交易状态": "退款成功",
            "收/支": "支出",
            "交易分类": "/",
            "备注": "",
        }
        with pytest.raises(ParserError):
            _ = parser.parse(record)
