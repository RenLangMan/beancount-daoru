import datetime
from decimal import Decimal

import pytest

from beancount_daoru.importer import Extra, Metadata, ParserError, Posting, Transaction
from beancount_daoru.importers.wechat import Importer, Parser, _validate_str


@pytest.fixture(scope="module")
def parser() -> Parser:
    """创建微信支付解析器实例."""
    return Parser()


class TestExtractMetadata:
    """测试微信支付元数据提取."""

    def test_extract_metadata(self, parser: Parser) -> None:
        """测试正常提取微信昵称和终止时间."""
        caption = (
            "微信支付账单流水文件\n"
            "微信昵称：[测试用户]\n"
            "起始时间:[2024-01-01 00:00:00] 终止时间:[2024-01-31 23:59:59]\n"
        )
        metadata = parser.extract_metadata(iter([caption]))
        assert metadata == Metadata(
            account="测试用户",
            date=datetime.date(2024, 1, 31),
        )

    def test_extract_metadata_with_colon(self, parser: Parser) -> None:
        """测试中文冒号格式."""
        lines = [
            "微信昵称:[我的昵称]",
            "起始时间:[2024-06-01 00:00:00] 终止时间:[2024-06-30 23:59:59]",
        ]
        metadata = parser.extract_metadata(iter(lines))
        assert metadata == Metadata(
            account="我的昵称",
            date=datetime.date(2024, 6, 30),
        )

    def test_extract_metadata_missing_account(self, parser: Parser) -> None:
        """测试缺少账户信息时抛出 ValueError."""
        caption = "终止时间:[2024-01-31 23:59:59]"
        with pytest.raises(ValueError, match="无法从文件中提取账户信息"):
            _ = parser.extract_metadata(iter([caption]))

    def test_extract_metadata_missing_date(self, parser: Parser) -> None:
        """测试缺少日期信息时抛出 ValueError."""
        caption = "微信昵称：[测试用户]"
        with pytest.raises(ValueError, match="无法从文件中提取日期信息"):
            _ = parser.extract_metadata(iter([caption]))


class TestReversed:
    """测试微信支付解析器 reversed 属性."""

    def test_reversed(self, parser: Parser) -> None:
        """微信支付记录为倒序,应返回 True."""
        assert parser.reversed is True


PARSE_PARAMS_LIST = [
    (
        # 普通消费支出: 商户消费 + 支付成功
        {
            "交易时间": "2024-01-15 12:30:00",
            "交易类型": "商户消费",
            "交易对方": "某餐厅",
            "商品": "午餐",
            "收/支": "支出",
            "金额(元)": "¥50.00",
            "支付方式": "零钱",
            "当前状态": "支付成功",
            "备注": "/",
        },
        Transaction(
            date=datetime.date(2024, 1, 15),
            extra=Extra(
                time=datetime.time(12, 30, 0),
                dc="支出",
                status="支付成功",
                type="商户消费",
                remarks=None,
            ),
            payee="某餐厅",
            narration="午餐",
            postings=(Posting(account="零钱", amount=Decimal("-50.00"), currency="¥"),),
        ),
    ),
    (
        # 商户消费 + 已退款
        {
            "交易时间": "2024-01-16 09:00:00",
            "交易类型": "商户消费",
            "交易对方": "某商店",
            "商品": "商品退款",
            "收/支": "支出",
            "金额(元)": "¥30.00",
            "支付方式": "零钱",
            "当前状态": "已退款",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 1, 16),
            extra=Extra(
                time=datetime.time(9, 0, 0),
                dc="支出",
                status="已退款",
                type="商户消费",
                remarks=None,
            ),
            payee="某商店",
            narration="商品退款",
            postings=(Posting(account="零钱", amount=Decimal("-30.00"), currency="¥"),),
        ),
    ),
    (
        # 商户消费 + 已全额退款
        {
            "交易时间": "2024-01-17 10:00:00",
            "交易类型": "商户消费",
            "交易对方": "某商店",
            "商品": "全额退款",
            "收/支": "支出",
            "金额(元)": "¥100.00",
            "支付方式": "银行卡",
            "当前状态": "已全额退款",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 1, 17),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc="支出",
                status="已全额退款",
                type="商户消费",
                remarks=None,
            ),
            payee="某商店",
            narration="全额退款",
            postings=(
                Posting(account="银行卡", amount=Decimal("-100.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 分分捐 + 支付成功
        {
            "交易时间": "2024-02-01 08:00:00",
            "交易类型": "分分捐",
            "交易对方": "公益项目",
            "商品": "公益捐款",
            "收/支": "支出",
            "金额(元)": "¥1.00",
            "支付方式": "零钱",
            "当前状态": "支付成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 1),
            extra=Extra(
                time=datetime.time(8, 0, 0),
                dc="支出",
                status="支付成功",
                type="分分捐",
                remarks=None,
            ),
            payee="公益项目",
            narration="公益捐款",
            postings=(Posting(account="零钱", amount=Decimal("-1.00"), currency="¥"),),
        ),
    ),
    (
        # 亲属卡交易 + 支付成功
        {
            "交易时间": "2024-02-05 14:00:00",
            "交易类型": "亲属卡交易",
            "交易对方": "某超市",
            "商品": "日用品",
            "收/支": "支出",
            "金额(元)": "¥25.50",
            "支付方式": "零钱",
            "当前状态": "支付成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 5),
            extra=Extra(
                time=datetime.time(14, 0, 0),
                dc="支出",
                status="支付成功",
                type="亲属卡交易",
                remarks=None,
            ),
            payee="某超市",
            narration="日用品",
            postings=(Posting(account="零钱", amount=Decimal("-25.50"), currency="¥"),),
        ),
    ),
    (
        # 支出 + 赞赏码 + 朋友已收钱
        {
            "交易时间": "2024-02-10 16:00:00",
            "交易类型": "赞赏码",
            "交易对方": "作者",
            "商品": "赞赏",
            "收/支": "支出",
            "金额(元)": "¥5.00",
            "支付方式": "零钱",
            "当前状态": "朋友已收钱",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 10),
            extra=Extra(
                time=datetime.time(16, 0, 0),
                dc="支出",
                status="朋友已收钱",
                type="赞赏码",
                remarks=None,
            ),
            payee="作者",
            narration="赞赏",
            postings=(Posting(account="零钱", amount=Decimal("-5.00"), currency="¥"),),
        ),
    ),
    (
        # 支出 + 转账 + 朋友已收钱
        {
            "交易时间": "2024-02-15 18:00:00",
            "交易类型": "转账",
            "交易对方": "张三",
            "商品": "/",
            "收/支": "支出",
            "金额(元)": "¥200.00",
            "支付方式": "零钱",
            "当前状态": "朋友已收钱",
            "备注": "/",
        },
        Transaction(
            date=datetime.date(2024, 2, 15),
            extra=Extra(
                time=datetime.time(18, 0, 0),
                dc="支出",
                status="朋友已收钱",
                type="转账",
                remarks=None,
            ),
            payee="张三",
            narration=None,
            postings=(
                Posting(account="零钱", amount=Decimal("-200.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 支出 + 扫二维码付款 + 已转账
        {
            "交易时间": "2024-02-20 11:00:00",
            "交易类型": "扫二维码付款",
            "交易对方": "小贩",
            "商品": "水果",
            "收/支": "支出",
            "金额(元)": "¥15.00",
            "支付方式": "零钱",
            "当前状态": "已转账",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 2, 20),
            extra=Extra(
                time=datetime.time(11, 0, 0),
                dc="支出",
                status="已转账",
                type="扫二维码付款",
                remarks=None,
            ),
            payee="小贩",
            narration="水果",
            postings=(Posting(account="零钱", amount=Decimal("-15.00"), currency="¥"),),
        ),
    ),
    (
        # 支出 + 转账 + 对方已收钱
        {
            "交易时间": "2024-03-01 09:30:00",
            "交易类型": "转账",
            "交易对方": "李四",
            "商品": "/",
            "收/支": "支出",
            "金额(元)": "¥500.00",
            "支付方式": "零钱通",
            "当前状态": "对方已收钱",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 3, 1),
            extra=Extra(
                time=datetime.time(9, 30, 0),
                dc="支出",
                status="对方已收钱",
                type="转账",
                remarks=None,
            ),
            payee="李四",
            narration=None,
            postings=(
                Posting(account="零钱通", amount=Decimal("-500.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 收入 + 其他 + 已到账
        {
            "交易时间": "2024-03-05 10:00:00",
            "交易类型": "其他",
            "交易对方": "系统",
            "商品": "红包退款",
            "收/支": "收入",
            "金额(元)": "¥8.88",
            "支付方式": "零钱",
            "当前状态": "已到账",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 3, 5),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc="收入",
                status="已到账",
                type="其他",
                remarks=None,
            ),
            payee="系统",
            narration="红包退款",
            postings=(Posting(account="零钱", amount=Decimal("8.88"), currency="¥"),),
        ),
    ),
    (
        # 收入 + 商户消费 + 充值成功
        {
            "交易时间": "2024-03-10 14:00:00",
            "交易类型": "商户消费",
            "交易对方": "充值中心",
            "商品": "话费充值",
            "收/支": "收入",
            "金额(元)": "¥100.00",
            "支付方式": "银行卡",
            "当前状态": "充值成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 3, 10),
            extra=Extra(
                time=datetime.time(14, 0, 0),
                dc="收入",
                status="充值成功",
                type="商户消费",
                remarks=None,
            ),
            payee="充值中心",
            narration="话费充值",
            postings=(
                Posting(account="银行卡", amount=Decimal("100.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 收入 + 二维码收款 + 已收钱
        {
            "交易时间": "2024-03-15 16:00:00",
            "交易类型": "二维码收款",
            "交易对方": "客户",
            "商品": "收款",
            "收/支": "收入",
            "金额(元)": "¥66.66",
            "支付方式": "零钱",
            "当前状态": "已收钱",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 3, 15),
            extra=Extra(
                time=datetime.time(16, 0, 0),
                dc="收入",
                status="已收钱",
                type="二维码收款",
                remarks=None,
            ),
            payee="客户",
            narration="收款",
            postings=(Posting(account="零钱", amount=Decimal("66.66"), currency="¥"),),
        ),
    ),
    (
        # 收入 + 微信红包 + 已存入零钱
        {
            "交易时间": "2024-03-20 12:00:00",
            "交易类型": "微信红包",
            "交易对方": "王五",
            "商品": "红包",
            "收/支": "收入",
            "金额(元)": "¥9.99",
            "支付方式": "零钱",
            "当前状态": "已存入零钱",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 3, 20),
            extra=Extra(
                time=datetime.time(12, 0, 0),
                dc="收入",
                status="已存入零钱",
                type="微信红包",
                remarks=None,
            ),
            payee="王五",
            narration="红包",
            postings=(Posting(account="零钱", amount=Decimal("9.99"), currency="¥"),),
        ),
    ),
    (
        # None收/支 + 购买理财通 + 支付成功
        {
            "交易时间": "2024-04-01 10:00:00",
            "交易类型": "购买理财通",
            "交易对方": "理财通",
            "商品": "买入理财",
            "收/支": "/",
            "金额(元)": "¥10000.00",
            "支付方式": "银行卡",
            "当前状态": "支付成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 4, 1),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc=None,
                status="支付成功",
                type="购买理财通",
                remarks=None,
            ),
            payee="理财通",
            narration="买入理财",
            postings=(
                Posting(account="银行卡", amount=Decimal("10000.00"), currency="¥"),
            ),
        ),
    ),
    (
        # None收/支 + 信用卡还款 + 支付成功
        {
            "交易时间": "2024-04-05 15:00:00",
            "交易类型": "信用卡还款",
            "交易对方": "信用卡",
            "商品": "还款",
            "收/支": "/",
            "金额(元)": "¥3000.00",
            "支付方式": "零钱",
            "当前状态": "支付成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 4, 5),
            extra=Extra(
                time=datetime.time(15, 0, 0),
                dc=None,
                status="支付成功",
                type="信用卡还款",
                remarks=None,
            ),
            payee="信用卡",
            narration="还款",
            postings=(
                Posting(account="零钱", amount=Decimal("3000.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 收入 + 退款 + 已退款
        {
            "交易时间": "2024-04-10 11:00:00",
            "交易类型": "退款",
            "交易对方": "某商家",
            "商品": "商品退款",
            "收/支": "收入",
            "金额(元)": "¥25.50",
            "支付方式": "零钱",
            "当前状态": "已退款",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 4, 10),
            extra=Extra(
                time=datetime.time(11, 0, 0),
                dc="收入",
                status="已退款",
                type="退款",
                remarks=None,
            ),
            payee="某商家",
            narration="商品退款",
            postings=(Posting(account="零钱", amount=Decimal("25.50"), currency="¥"),),
        ),
    ),
    (
        # 收入 + 退款 + 已全额退款
        {
            "交易时间": "2024-04-11 11:00:00",
            "交易类型": "退款",
            "交易对方": "某商家",
            "商品": "全额退款",
            "收/支": "收入",
            "金额(元)": "¥99.99",
            "支付方式": "零钱",
            "当前状态": "已全额退款",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 4, 11),
            extra=Extra(
                time=datetime.time(11, 0, 0),
                dc="收入",
                status="已全额退款",
                type="退款",
                remarks=None,
            ),
            payee="某商家",
            narration="全额退款",
            postings=(Posting(account="零钱", amount=Decimal("99.99"), currency="¥"),),
        ),
    ),
    (
        # 转入零钱通: None收/支 + 转入零钱通-来自xxx + 支付成功
        {
            "交易时间": "2024-04-15 08:00:00",
            "交易类型": "转入零钱通-来自银行卡",
            "交易对方": "零钱通",
            "商品": "转入零钱通",
            "收/支": "/",
            "金额(元)": "¥2000.00",
            "支付方式": "银行卡",
            "当前状态": "支付成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 4, 15),
            extra=Extra(
                time=datetime.time(8, 0, 0),
                dc=None,
                status="支付成功",
                type="转入零钱通-来自银行卡",
                remarks=None,
            ),
            payee="零钱通",
            narration="转入零钱通",
            postings=(
                Posting(account="银行卡", amount=Decimal("-2000.00"), currency="¥"),
                Posting(account="零钱通", amount=Decimal("2000.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 零钱通转出: None收/支 + 零钱通转出-到xxx + 支付成功
        {
            "交易时间": "2024-04-20 09:00:00",
            "交易类型": "零钱通转出-到银行卡",
            "交易对方": "零钱通",
            "商品": "零钱通转出",
            "收/支": "/",
            "金额(元)": "¥1500.00",
            "支付方式": "零钱通",
            "当前状态": "支付成功",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 4, 20),
            extra=Extra(
                time=datetime.time(9, 0, 0),
                dc=None,
                status="支付成功",
                type="零钱通转出-到银行卡",
                remarks=None,
            ),
            payee="零钱通",
            narration="零钱通转出",
            postings=(
                Posting(account="零钱通", amount=Decimal("-1500.00"), currency="¥"),
                Posting(account="银行卡", amount=Decimal("1500.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 零钱充值: None收/支 + 零钱充值 + 充值完成
        {
            "交易时间": "2024-05-01 10:00:00",
            "交易类型": "零钱充值",
            "交易对方": "零钱",
            "商品": "充值",
            "收/支": "/",
            "金额(元)": "¥500.00",
            "支付方式": "银行卡",
            "当前状态": "充值完成",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 5, 1),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc=None,
                status="充值完成",
                type="零钱充值",
                remarks=None,
            ),
            payee="零钱",
            narration="充值",
            postings=(
                Posting(account="银行卡", amount=Decimal("-500.00"), currency="¥"),
                Posting(account="零钱", amount=Decimal("500.00"), currency="¥"),
            ),
        ),
    ),
    (
        # 零钱提现(含服务费): None收/支 + 零钱提现 + 提现已到账
        {
            "交易时间": "2024-05-05 14:00:00",
            "交易类型": "零钱提现",
            "交易对方": "银行卡",
            "商品": "提现",
            "收/支": "/",
            "金额(元)": "¥1000.00",
            "支付方式": "银行卡",
            "当前状态": "提现已到账",
            "备注": "服务费¥1.00",
        },
        Transaction(
            date=datetime.date(2024, 5, 5),
            extra=Extra(
                time=datetime.time(14, 0, 0),
                dc=None,
                status="提现已到账",
                type="零钱提现",
                remarks="服务费¥1.00",
            ),
            payee="银行卡",
            narration="提现",
            postings=(
                Posting(account="银行卡", amount=Decimal("-1000.00"), currency="¥"),
                Posting(account="零钱", amount=Decimal("1000.00"), currency="¥"),
                Posting(
                    amount=Decimal("1.00"),
                    account="零钱提现服务费",
                    currency="¥",
                ),
            ),
        ),
    ),
    (
        # 退款类型(以-退款结尾): 收入 + 已退款
        {
            "交易时间": "2024-05-10 16:00:00",
            "交易类型": "商户消费-退款",
            "交易对方": "某商家",
            "商品": "退款商品",
            "收/支": "收入",
            "金额(元)": "¥35.00",
            "支付方式": "零钱",
            "当前状态": "已退款",
            "备注": "",
        },
        Transaction(
            date=datetime.date(2024, 5, 10),
            extra=Extra(
                time=datetime.time(16, 0, 0),
                dc="收入",
                status="已退款",
                type="商户消费-退款",
                remarks=None,
            ),
            payee="某商家",
            narration="退款商品",
            postings=(Posting(account="零钱", amount=Decimal("35.00"), currency="¥"),),
        ),
    ),
]


@pytest.mark.parametrize(("record", "transaction"), PARSE_PARAMS_LIST)
def test_parse(
    parser: Parser, record: dict[str, str], transaction: Transaction
) -> None:
    """测试解析微信支付交易记录.

    参数化测试各种场景:
        - 普通消费支出
        - 退款场景
        - 收入类交易
        - 转入零钱通
        - 零钱通转出
        - 零钱充值
        - 零钱提现(含服务费)
    """
    assert parser.parse(record) == transaction


def test_parse_error(parser: Parser) -> None:
    """测试无法识别的交易类型抛出 ParserError."""
    record = {
        "交易时间": "2024-01-01 00:00:00",
        "交易类型": "未知类型",
        "交易对方": "/",
        "商品": "/",
        "收/支": "其他",
        "金额(元)": "¥1.00",
        "支付方式": "零钱",
        "当前状态": "其他状态",
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
