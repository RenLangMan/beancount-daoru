import datetime
from decimal import Decimal

import pytest

from beancount_daoru.importer import Extra, Metadata, ParserError, Posting, Transaction
from beancount_daoru.importers.bocom import Importer, Parser, _validate_str


@pytest.fixture(scope="module")
def parser() -> Parser:
    """创建交通银行解析器实例.

    返回:
        交通银行解析器实例
    """
    return Parser()


def test_extract_metadata(parser: Parser) -> None:
    """测试从交通银行账单中提取元数据.

    验证解析器能够正确从账单文本中提取:
        - 账号/卡号(账户)
        - 查询截止日期
        - 币种信息
    """
    caption = (
        "交通银行个人客户交易清单\n"
        "Bocom Personal Account Details\n"
        "  支持交通银行手机银行扫码验真\n"
        "部门Department: 01120123456 柜员Search Teller: EBB0001 "
        "打印日期Printing Date: 2020-12-31 12:00:00 "
        "打印时间Printing Time: 2020-12-31 12:00:00\n"
        "账号/卡号Account/Card No: 6222612345678901234 "
        "户名Account Name: 李四\n"
        "查询起日Query Starting Date: 2020-01-01 "
        "查询止日Query Ending Date: 2020-01-31\n"
        "查询时间Query Time: 2020年12月31日  12:00:00 "
        "查询柜员Search Teller: EBB0001 "
        "币种Currency: 人民币 CNY\n"
        "证件种类 ID Type: 第二代居民身份证 "
        "证件号码 ID Number: 110101199003071234\n"
        "第 1 / 13 页"
    )
    metadata = parser.extract_metadata(iter([caption]))
    assert metadata == Metadata(
        account="6222612345678901234",
        date=datetime.date(2020, 1, 31),
        currency="人民币",
    )


TEST_PARAMS_LIST = [
    (
        # 测试场景1:存款利息收入(贷方交易)
        {
            "Serial\nNum\n序号": "1",
            "Trans Date\n交易日期": "2020-01-01",
            "Trans Time\n交易时间": "10:00:00",
            "Trading Type\n交易类型": "存款利息",
            "Dc Flg\n借贷": "贷 Cr",
            "Trans Amt\n交易金额": "1.00",
            "Balance\n余额": "1,000.00",
            "Payment Receipt\nAccount\n对方账号": "123456789012345\n123",
            "Payment Receipt\nAccount Name\n对方户名": "应付个人活期储蓄存款\n利息",
            "Trading Place\n交易地点": "批处理",
            "Abstract\n摘要": "",
        },
        Transaction(
            date=datetime.date(2020, 1, 1),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                dc="贷 Cr",
                type="存款利息",
                payee_account="123456789012345123",  # 注意:换行符已被清理
                place="批处理",
            ),
            payee="应付个人活期储蓄存款利息",  # 注意:换行符已被清理
            postings=(
                Posting(
                    amount=Decimal("1.00"),
                ),
            ),
            balance=Posting(
                amount=Decimal("1000.00"),
            ),
        ),
    ),
    (
        # 测试场景2:网上支付消费(借方交易)
        {
            "Serial\nNum\n序号": "2",
            "Trans Date\n交易日期": "2020-01-02",
            "Trans Time\n交易时间": "11:00:00",
            "Trading Type\n交易类型": "网上支付",
            "Dc Flg\n借贷": "借 Dr",
            "Trans Amt\n交易金额": "10.00",
            "Balance\n余额": "990.00",
            "Payment Receipt\nAccount\n对方账号": "123456789",
            "Payment Receipt\nAccount Name\n对方户名": (
                "支付宝(中国)网络技\n术有限公司"
            ),
            "Trading Place\n交易地点": "支付宝(中国)网络技\n术有限公司",
            "Abstract\n摘要": (
                "网上支付 其他商家\n消费 订单编号\n20200102110123456\n"
                "123456789012345\n柒一拾壹(天津\n)商业有限公 交易\n流水号\n"
                "20200102123456789\n12345678901234"
            ),
        },
        Transaction(
            date=datetime.date(2020, 1, 2),
            payee="支付宝(中国)网络技术有限公司",  # 注意:换行符已被清理
            narration=(
                "网上支付 其他商家消费 订单编号20200102110123456123456789012345"
                "柒一拾壹(天津)商业有限公 交易流水号2020010212345678912345678901234"
            ),
            extra=Extra(
                time=datetime.time(11, 0, 0),
                dc="借 Dr",
                type="网上支付",
                payee_account="123456789",
                place="支付宝(中国)网络技术有限公司",
            ),
            postings=(
                Posting(
                    amount=Decimal("-10.00"),
                ),
            ),
            balance=Posting(
                amount=Decimal("990.00"),
            ),
        ),
    ),
]


@pytest.mark.parametrize(("record", "transaction"), TEST_PARAMS_LIST)
def test_build(
    parser: Parser, record: dict[str, str], transaction: Transaction
) -> None:
    """测试解析交通银行交易记录.

    使用参数化测试验证解析器能够正确处理各种交易类型:
        - 存款利息收入(贷方交易,正金额)
        - 网上支付消费(借方交易,负金额)

    参数:
        parser: 交通银行解析器实例
        record: 原始交易记录数据
        transaction: 期望的解析结果
    """
    assert parser.parse(record) == transaction


ERROR_PARAMS_LIST = [
    (
        # 错误场景:未识别的借贷标志
        {
            "Serial\nNum\n序号": "3",
            "Trans Date\n交易日期": "2020-01-03",
            "Trans Time\n交易时间": "12:00:00",
            "Trading Type\n交易类型": "其他交易",
            "Dc Flg\n借贷": "",  # 空的借贷标志,无法识别
            "Trans Amt\n交易金额": "5.00",
            "Balance\n余额": "985.00",
            "Payment Receipt\nAccount\n对方账号": "123456789012345",
            "Payment Receipt\nAccount Name\n对方户名": "支付宝-消费",
            "Trading Place\n交易地点": "支付宝-消费",
            "Abstract\n摘要": (
                "网上支付 生活服务\n消费 订单编号\n1234567890123456\n"
                "支付宝-消费 交易\n流水号\n1234567890123456"
            ),
        },
        r"unsupported value combination of fields: ('Dc Flg\n借贷',)",
    ),
]


@pytest.mark.parametrize(("record", "message"), ERROR_PARAMS_LIST)
def test_parse_error(parser: Parser, record: dict[str, str], message: str) -> None:
    """测试解析器对错误交易记录的处理.

    验证当遇到无法识别的交易数据时,解析器能够正确抛出 ParserError 异常。

    参数:
        parser: 交通银行解析器实例
        record: 包含错误数据的交易记录
        message: 期望的异常消息
    """
    with pytest.raises(ParserError) as excinfo:
        _ = parser.parse(record)
    assert str(excinfo.value) == message


def test_reversed_property(parser: Parser) -> None:
    """测试 reversed 属性返回 True.

    交通银行需要反转记账方向。
    """
    assert parser.reversed is True


def test_extract_metadata_missing_account(parser: Parser) -> None:
    """测试提取元数据时缺少账户信息抛出异常."""
    caption = (
        "交通银行个人客户交易清单\n"
        "Bocom Personal Account Details\n"
        "  支持交通银行手机银行扫码验真\n"
        "部门Department: 01120123456 柜员Search Teller: EBB0001\n"
        "打印日期Printing Date: 2020-12-31 12:00:00\n"
        "户名Account Name: 李四\n"
        "查询起日Query Starting Date: 2020-01-01 "
        "查询止日Query Ending Date: 2020-01-31\n"
        "查询时间Query Time: 2020年12月31日  12:00:00 "
        "币种Currency: 人民币 CNY\n"
        "第 1 / 13 页"
    )
    with pytest.raises(ValueError, match="无法从文件中提取账户信息"):
        parser.extract_metadata(iter([caption]))


def test_extract_metadata_missing_date(parser: Parser) -> None:
    """测试提取元数据时缺少日期信息抛出异常."""
    caption = (
        "交通银行个人客户交易清单\n"
        "Bocom Personal Account Details\n"
        "  支持交通银行手机银行扫码验真\n"
        "部门Department: 01120123456 柜员Search Teller: EBB0001\n"
        "打印日期Printing Date: 2020-12-31 12:00:00\n"
        "账号/卡号Account/Card No: 6222612345678901234 "
        "户名Account Name: 李四\n"
        "查询起日Query Starting Date: 2020-01-01\n"
        "查询时间Query Time: 2020年12月31日  12:00:00 "
        "币种Currency: 人民币 CNY\n"
        "第 1 / 13 页"
    )
    with pytest.raises(ValueError, match="无法从文件中提取日期信息"):
        parser.extract_metadata(iter([caption]))


def test_extract_metadata_missing_currency(parser: Parser) -> None:
    """测试提取元数据时缺少币种信息抛出异常."""
    caption = (
        "交通银行个人客户交易清单\n"
        "Bocom Personal Account Details\n"
        "  支持交通银行手机银行扫码验真\n"
        "部门Department: 01120123456 柜员Search Teller: EBB0001\n"
        "打印日期Printing Date: 2020-12-31 12:00:00\n"
        "账号/卡号Account/Card No: 6222612345678901234 "
        "户名Account Name: 李四\n"
        "查询起日Query Starting Date: 2020-01-01 "
        "查询止日Query Ending Date: 2020-01-31\n"
        "查询时间Query Time: 2020年12月31日  12:00:00\n"
        "第 1 / 13 页"
    )
    with pytest.raises(ValueError, match="无法从文件中提取币种信息"):
        parser.extract_metadata(iter([caption]))


def test_validate_str_with_none() -> None:
    """测试 _validate_str 处理 None 值."""
    result = _validate_str(None)
    assert result is None


def test_validate_str_with_newline_only() -> None:
    """测试 _validate_str 处理只有换行符的值."""
    result = _validate_str("\n")
    assert result is None


def test_validate_str_with_newline() -> None:
    """测试 _validate_str 处理带换行符的值."""
    result = _validate_str("Hello\nWorld")
    assert result == "HelloWorld"


def test_validate_str_with_normal_value() -> None:
    """测试 _validate_str 处理普通值."""
    result = _validate_str("正常内容")
    assert result == "正常内容"


def test_importer_init() -> None:
    """测试 Importer 初始化."""
    importer = Importer(account_mapping={}, currency_mapping={})
    assert importer._Importer__filename_pattern is not None
    assert importer._Importer__reader is not None
    assert importer._Importer__parser is not None
