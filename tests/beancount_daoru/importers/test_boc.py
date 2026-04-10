import datetime
from decimal import Decimal

import pytest

from beancount_daoru.importer import Extra, Metadata, Posting, Transaction
from beancount_daoru.importers.boc import Parser


@pytest.fixture(scope="module")
def parser() -> Parser:
    """创建中国银行解析器实例。

    返回：
        中国银行解析器实例
    """
    return Parser()


def test_extract_metadata(parser: Parser) -> None:
    """测试从中国银行账单中提取元数据。

    验证解析器能够正确从账单文本中提取：
        - 借记卡号（账户）
        - 交易截止日期
    """
    caption = (
        "中国银行交易流水明细清单\n"
        "交易区间： 2020-01-01 至2020-12-31 客户姓名： 张三 页数: 1 /1\n"
        "借记卡号： 6216612345678901234 "
        "借方发生数： 1,000.00 贷方发生数： 0.00 行数: 10\n"
        "账号：345671234567 按收支筛选： 全部 按币种筛选： 全部 "
        "打印时间： 2020/12/31 12:00:00\n"
        "温馨提示: 1.记账日期/时间为系统进行记账处理的日期/时间,"
        "可能与实际交易提交时间存在差异。\n"
        "第 1 页/共 1页"
    )
    metadata = parser.extract_metadata(iter([caption]))
    assert metadata == Metadata(
        account="6216612345678901234",
        date=datetime.date(2020, 12, 31),
    )


PARSE_PARAMS_LIST = [
    (
        # 测试场景1：结息交易
        {
            "记账日期": "2020-01-01",
            "记账时间": "10:00:00",
            "币别": "人民币",
            "金额": "1.00",
            "余额": "1,000.00",
            "交易名称": "结息",
            "渠道": "其他",
            "网点名称": "-------------------",
            "附言": "----------",
            "对方账户名": "-------------------",
            "对方卡号/账号": "-------------------",
            "对方开户行": "-------------------",
        },
        Transaction(
            date=datetime.date(2020, 1, 1),
            extra=Extra(
                time=datetime.time(10, 0, 0),
                type="结息",
                place="其他",
            ),
            postings=(
                Posting(
                    amount=Decimal("1.00"),
                    currency="人民币",
                ),
            ),
            balance=Posting(
                amount=Decimal("1000.00"),
                currency="人民币",
            ),
        ),
    ),
    (
        # 测试场景2：网上快捷支付（财付通交易）
        {
            "记账日期": "2020-01-02",
            "记账时间": "11:00:00",
            "币别": "人民币",
            "金额": "-10.00",
            "余额": "990.00",
            "交易名称": "网上快捷支付",
            "渠道": "银企对接",
            "网点名称": "-------------------",
            "附言": "财付通",
            "对方账户名": "财付通",
            "对方卡号/账号": "Z1234567890123N",
            "对方开户行": "-------------------",
        },
        Transaction(
            date=datetime.date(2020, 1, 2),
            payee="财付通",
            narration="财付通",
            extra=Extra(
                time=datetime.time(11, 0, 0),
                type="网上快捷支付",
                payee_account="Z1234567890123N",
                place="银企对接",
            ),
            postings=(
                Posting(
                    amount=Decimal("-10.00"),
                    currency="人民币",
                ),
            ),
            balance=Posting(
                amount=Decimal("990.00"),
                currency="人民币",
            ),
        ),
    ),
]


@pytest.mark.parametrize(("record", "transaction"), PARSE_PARAMS_LIST)
def test_parse(
    parser: Parser, record: dict[str, str], transaction: Transaction
) -> None:
    """测试解析中国银行交易记录。

    使用参数化测试验证解析器能够正确处理各种交易类型：
        - 结息交易（收入）
        - 网上支付交易（支出）

    参数：
        parser: 中国银行解析器实例
        record: 原始交易记录数据
        transaction: 期望的解析结果
    """
    assert parser.parse(record) == transaction
