import datetime
from decimal import Decimal

import pytest

from beancount_daoru.importer import Extra, Metadata, ParserError, Posting, Transaction
from beancount_daoru.importers.alipay import Parser


@pytest.fixture(scope="module")
def parser() -> Parser:
    """创建支付宝解析器实例."""
    return Parser()


class TestExtractMetadata:
    """测试支付宝元数据提取."""

    def test_extract_metadata(self, parser: Parser) -> None:
        """测试正常提取支付宝账户和终止时间."""
        caption = (
            "支付宝交易明细\n"
            "账号:[test@example.com]\n"
            "支付宝账户:test@example.com\n"
            "起始时间:[2024-01-01 00:00:00] 终止时间:[2024-01-31 23:59:59]\n"
        )
        metadata = parser.extract_metadata(iter([caption]))
        assert metadata == Metadata(
            account="test@example.com",
            date=datetime.date(2024, 1, 31),
        )

    def test_extract_metadata_multiple_lines(self, parser: Parser) -> None:
        """测试多行文本中提取元数据."""
        lines = [
            "支付宝交易明细",
            "支付宝账户:user123@163.com",
            "起始时间:[2024-06-01 00:00:00] 终止时间:[2024-06-30 23:59:59]",
        ]
        metadata = parser.extract_metadata(iter(lines))
        assert metadata == Metadata(
            account="user123@163.com",
            date=datetime.date(2024, 6, 30),
        )

    def test_extract_metadata_missing_account(self, parser: Parser) -> None:
        """测试缺少账户信息时抛出 ValueError."""
        caption = "起始时间:[2024-01-01 00:00:00] 终止时间:[2024-01-31 23:59:59]"
        with pytest.raises(ValueError, match="无法从文件中提取账户信息"):
            _ = parser.extract_metadata(iter([caption]))

    def test_extract_metadata_missing_date(self, parser: Parser) -> None:
        """测试缺少日期信息时抛出 ValueError."""
        caption = "支付宝账户:test@example.com"
        with pytest.raises(ValueError, match="无法从文件中提取日期信息"):
            _ = parser.extract_metadata(iter([caption]))


def test_extract_metadata_empty_input(parser: Parser) -> None:
    """测试空输入时抛出 ValueError."""
    with pytest.raises(ValueError, match="无法从文件中提取账户信息"):
        _ = parser.extract_metadata(iter([]))


class TestReversed:
    """测试支付宝解析器 reversed 属性."""

    def test_reversed(self, parser: Parser) -> None:
        """支付宝记录为倒序,应返回 True."""
        assert parser.reversed is True


PARSE_PARAMS_LIST = [
    (
        # 支出 + 交易成功
        {
            "交易时间": "2024-01-15 10:30:00",
            "交易分类": "商品",
            "交易对方": "某商家",
            "对方账号": "account123",
            "商品说明": "购买商品",
            "收/支": "支出",
            "金额": "100.00",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "备注": "/",
        },
        Transaction(
            date=datetime.date(2024, 1, 15),
            extra=Extra(
                time=datetime.time(10, 30, 0),
                dc="支出",
                status="交易成功",
                payee_account="account123",
                type="商品",
                remarks=None,
            ),
            payee="某商家",
            narration="购买商品",
            postings=(Posting(account="余额", amount=Decimal("-100.00")),),
        ),
    ),
    (
        # 支出 + 等待确认收货
        {
            "交易时间": "2024-01-16 14:00:00",
            "交易分类": "商品",
            "交易对方": "另一商家",
            "对方账号": "",
            "商品说明": "预售商品",
            "收/支": "支出",
            "金额": "50.50",
            "收/付款方式": "花呗",
            "交易状态": "等待确认收货",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 1, 16),
            extra=Extra(
                time=datetime.time(14, 0, 0),
                dc="支出",
                status="等待确认收货",
                payee_account=None,
                type="商品",
                remarks=None,
            ),
            payee="另一商家",
            narration="预售商品",
            postings=(Posting(account="花呗", amount=Decimal("-50.50")),),
        ),
    ),
    (
        # 支出 + 交易关闭
        {
            "交易时间": "2024-02-01 09:00:00",
            "交易分类": "商品",
            "交易对方": "某商家",
            "对方账号": "/",
            "商品说明": "取消订单",
            "收/支": "支出",
            "金额": "200.00",
            "收/付款方式": "余额宝",
            "交易状态": "交易关闭",
            "备注": "/",
        },
        Transaction(
            date=datetime.date(2024, 2, 1),
            extra=Extra(
                time=datetime.time(9, 0, 0),
                dc="支出",
                status="交易关闭",
                payee_account=None,
                type="商品",
                remarks=None,
            ),
            payee="某商家",
            narration="取消订单",
            postings=(Posting(account="余额宝", amount=Decimal("-200.00")),),
        ),
    ),
    (
        # 收入 + 交易关闭
        {
            "交易时间": "2024-02-05 11:00:00",
            "交易分类": "转账",
            "交易对方": "张三",
            "对方账号": "acc456",
            "商品说明": "转账收款-已关闭",
            "收/支": "收入",
            "金额": "300.00",
            "收/付款方式": "余额",
            "交易状态": "交易关闭",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 5),
            extra=Extra(
                time=datetime.time(11, 0, 0),
                dc="收入",
                status="交易关闭",
                payee_account="acc456",
                type="转账",
                remarks=None,
            ),
            payee="张三",
            narration="转账收款-已关闭",
            postings=(),
        ),
    ),
    (
        # 收入 + 交易成功
        {
            "交易时间": "2024-03-01 12:00:00",
            "交易分类": "转账",
            "交易对方": "李四",
            "对方账号": "",
            "商品说明": "转账收款",
            "收/支": "收入",
            "金额": "500.00",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "备注": "/",
        },
        Transaction(
            date=datetime.date(2024, 3, 1),
            extra=Extra(
                time=datetime.time(12, 0, 0),
                dc="收入",
                status="交易成功",
                payee_account=None,
                type="转账",
                remarks=None,
            ),
            payee="李四",
            narration="转账收款",
            postings=(Posting(account="余额", amount=Decimal("500.00")),),
        ),
    ),
    (
        # 不计收支 + 退款成功
        {
            "交易时间": "2024-03-10 15:30:00",
            "交易分类": "商品",
            "交易对方": "某商家",
            "对方账号": "",
            "商品说明": "退款到余额",
            "收/支": "不计收支",
            "金额": "88.88",
            "收/付款方式": "余额",
            "交易状态": "退款成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 3, 10),
            extra=Extra(
                time=datetime.time(15, 30, 0),
                dc="不计收支",
                status="退款成功",
                payee_account=None,
                type="商品",
                remarks=None,
            ),
            payee="某商家",
            narration="退款到余额",
            postings=(Posting(account="余额", amount=Decimal("88.88")),),
        ),
    ),
    (
        # 不计收支 + 交易成功 + 提现-实时提现
        {
            "交易时间": "2024-03-15 08:00:00",
            "交易分类": "提现",
            "交易对方": None,
            "对方账号": None,
            "商品说明": "提现-实时提现",
            "收/支": "不计收支",
            "金额": "1000.00",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "备注": None,
        },
        Transaction(
            date=datetime.date(2024, 3, 15),
            extra=Extra(
                time=datetime.time(8, 0, 0),
                dc="不计收支",
                status="交易成功",
                payee_account=None,
                type="提现",
                remarks=None,
            ),
            payee=None,
            narration="提现-实时提现",
            postings=(Posting(account="余额", amount=Decimal("1000.00")),),
        ),
    ),
    (
        # 不计收支 + 交易成功 + 余额宝-更换货基转入
        {
            "交易时间": "2024-03-20 09:00:00",
            "交易分类": "理财",
            "交易对方": None,
            "对方账号": None,
            "商品说明": "余额宝-更换货基转入",
            "收/支": "不计收支",
            "金额": "2000.00",
            "收/付款方式": "余额宝",
            "交易状态": "交易成功",
            "备注": None,
        },
        Transaction(
            date=datetime.date(2024, 3, 20),
            extra=Extra(
                time=datetime.time(9, 0, 0),
                dc="不计收支",
                status="交易成功",
                payee_account=None,
                type="理财",
                remarks=None,
            ),
            payee=None,
            narration="余额宝-更换货基转入",
            postings=(Posting(account="余额宝", amount=Decimal("2000.00")),),
        ),
    ),
    (
        # 不计收支 + 交易成功 + 余额宝-单次转入 (有对手方)
        {
            "交易时间": "2024-04-01 10:00:00",
            "交易分类": "理财",
            "交易对方": None,
            "对方账号": None,
            "商品说明": "余额宝-单次转入",
            "收/支": "不计收支",
            "金额": "5000.00",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "备注": None,
        },
        Transaction(
            date=datetime.date(2024, 4, 1),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc="不计收支",
                status="交易成功",
                payee_account=None,
                type="理财",
                remarks=None,
            ),
            payee=None,
            narration="余额宝-单次转入",
            postings=(
                Posting(account="余额", amount=Decimal("-5000.00")),
                Posting(account="余额宝", amount=Decimal("5000.00")),
            ),
        ),
    ),
    (
        # 不计收支 + 交易成功 + 余额宝-自动转入 (有对手方)
        {
            "交易时间": "2024-04-02 00:30:00",
            "交易分类": "理财",
            "交易对方": None,
            "对方账号": None,
            "商品说明": "余额宝-自动转入",
            "收/支": "不计收支",
            "金额": "0.01",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "备注": None,
        },
        Transaction(
            date=datetime.date(2024, 4, 2),
            extra=Extra(
                time=datetime.time(0, 30, 0),
                dc="不计收支",
                status="交易成功",
                payee_account=None,
                type="理财",
                remarks=None,
            ),
            payee=None,
            narration="余额宝-自动转入",
            postings=(
                Posting(account="余额", amount=Decimal("-0.01")),
                Posting(account="余额宝", amount=Decimal("0.01")),
            ),
        ),
    ),
    (
        # 不计收支 + 交易成功 + 余额宝-安心自动充-自动攒入 (有对手方)
        {
            "交易时间": "2024-04-03 08:00:00",
            "交易分类": "理财",
            "交易对方": None,
            "对方账号": None,
            "商品说明": "余额宝-安心自动充-自动攒入",
            "收/支": "不计收支",
            "金额": "100.00",
            "收/付款方式": "余额",
            "交易状态": "交易成功",
            "备注": None,
        },
        Transaction(
            date=datetime.date(2024, 4, 3),
            extra=Extra(
                time=datetime.time(8, 0, 0),
                dc="不计收支",
                status="交易成功",
                payee_account=None,
                type="理财",
                remarks=None,
            ),
            payee=None,
            narration="余额宝-安心自动充-自动攒入",
            postings=(
                Posting(account="余额", amount=Decimal("-100.00")),
                Posting(account="余额宝", amount=Decimal("100.00")),
            ),
        ),
    ),
    (
        # 不计收支 + 交易成功 + 余额宝-xxx-收益发放
        {
            "交易时间": "2024-04-05 00:00:00",
            "交易分类": "理财",
            "交易对方": None,
            "对方账号": None,
            "商品说明": "余额宝-日收益-收益发放",
            "收/支": "不计收支",
            "金额": "0.56",
            "收/付款方式": "余额宝",
            "交易状态": "交易成功",
            "备注": None,
        },
        Transaction(
            date=datetime.date(2024, 4, 5),
            extra=Extra(
                time=datetime.time(0, 0, 0),
                dc="不计收支",
                status="交易成功",
                payee_account=None,
                type="理财",
                remarks=None,
            ),
            payee=None,
            narration="余额宝-日收益-收益发放",
            postings=(Posting(account="余额宝", amount=Decimal("0.56")),),
        ),
    ),
    (
        # 不计收支 + 交易关闭
        {
            "交易时间": "2024-05-01 10:00:00",
            "交易分类": "商品",
            "交易对方": "某商家",
            "对方账号": "",
            "商品说明": "已关闭的退款",
            "收/支": "不计收支",
            "金额": "10.00",
            "收/付款方式": "余额",
            "交易状态": "交易关闭",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 5, 1),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc="不计收支",
                status="交易关闭",
                payee_account=None,
                type="商品",
                remarks=None,
            ),
            payee="某商家",
            narration="已关闭的退款",
            postings=(),
        ),
    ),
]


@pytest.mark.parametrize(("record", "transaction"), PARSE_PARAMS_LIST)
def test_parse(
    parser: Parser, record: dict[str, str], transaction: Transaction
) -> None:
    """测试解析支付宝交易记录.

    参数化测试各种场景:
        - 支出 + 交易成功
        - 支出 + 等待确认收货
        - 支出 + 交易关闭
        - 收入 + 交易关闭 (不生成记账)
        - 收入 + 交易成功
        - 不计收支 + 退款成功
        - 不计收支 + 交易成功 + 提现
        - 不计收支 + 交易成功 + 余额宝转入/收益
    """
    assert parser.parse(record) == transaction


PARSE_ERROR_PARAMS_LIST: list[dict[str, str]] = [
    # 不支持: 收/支=其他值, 交易状态=其他值
    {
        "交易时间": "2024-01-01 00:00:00",
        "交易分类": "其他",
        "交易对方": "/",
        "对方账号": "/",
        "商品说明": "/",
        "收/支": "其他",
        "金额": "1.00",
        "收/付款方式": "余额",
        "交易状态": "其他状态",
        "备注": "/",
    },
    # 不支持: 不计收支 + 交易成功 + 不认识的商品说明
    {
        "交易时间": "2024-01-01 00:00:00",
        "交易分类": "其他",
        "交易对方": "/",
        "对方账号": "/",
        "商品说明": "未知类型",
        "收/支": "不计收支",
        "金额": "1.00",
        "收/付款方式": "余额",
        "交易状态": "交易成功",
        "备注": "/",
    },
]


@pytest.mark.parametrize("record", PARSE_ERROR_PARAMS_LIST)
def test_parse_error(parser: Parser, record: dict[str, str]) -> None:
    """测试无法识别的交易类型抛出 ParserError."""
    with pytest.raises(ParserError):
        _ = parser.parse(record)
