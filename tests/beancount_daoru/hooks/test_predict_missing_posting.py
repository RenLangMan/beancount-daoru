"""测试 predict_missing_posting 钩子模块."""

import asyncio
import datetime
from collections.abc import Awaitable
from decimal import Decimal
from pathlib import Path
from typing import TypeVar, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beancount import (
    FLAG_OKAY,
    FLAG_WARNING,
    Amount,
    Balance,
    Close,
    Open,
    Posting,
    Transaction,
)

from beancount_daoru.hooks.predict_missing_posting import (
    ChatModelSettings,
    EmbeddingModelSettings,
    Hook,
    _AccountPredictor,  # pyright: ignore[reportPrivateUsage]
    _ChatBot,  # pyright: ignore[reportPrivateUsage]
    _Encoder,  # pyright: ignore[reportPrivateUsage]
    _HistoryIndex,  # pyright: ignore[reportPrivateUsage]
    _TransactionIndex,  # pyright: ignore[reportPrivateUsage]
)

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """同步运行异步协程的辅助函数."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture
def mock_encoder() -> AsyncMock:
    """创建 mock 编码器."""
    encoder = AsyncMock(spec=_Encoder)
    encoder.encode = AsyncMock(return_value=[0.1] * 128)
    return encoder


@pytest.fixture
def mock_chat_bot() -> AsyncMock:
    """创建 mock 聊天机器人."""
    chat_bot = AsyncMock(spec=_ChatBot)
    chat_bot.complete = AsyncMock(return_value='"Expenses:Food"')
    return chat_bot


class TestTransactionIndex:
    """测试 _TransactionIndex 类."""

    def test_add_and_hash(self, mock_encoder: AsyncMock) -> None:
        """测试添加交易到索引并生成哈希."""
        index = _TransactionIndex(encoder=mock_encoder, ndim=128)
        txn = _make_transaction("2024-01-01", "Expenses:Food", Decimal("50.00"))
        run_async(index.add(txn))
        mock_encoder.encode.assert_called_once()  # pyright: ignore[reportAny]

    def test_add_duplicate_ignored(self, mock_encoder: AsyncMock) -> None:
        """测试添加重复交易不会重复编码."""
        index = _TransactionIndex(encoder=mock_encoder, ndim=128)
        txn = _make_transaction("2024-01-01", "Expenses:Food", Decimal("50.00"))
        run_async(index.add(txn))
        run_async(index.add(txn))
        assert mock_encoder.encode.call_count == 1  # pyright: ignore[reportAny]

    def test_create_description(self, mock_encoder: AsyncMock) -> None:
        """测试创建交易描述."""
        index = _TransactionIndex(encoder=mock_encoder, ndim=128)
        txn = _make_transaction("2024-01-01", "Expenses:Food", Decimal("50.00"))
        desc = index._create_description(txn)  # pyright: ignore[reportPrivateUsage]
        assert "Expenses:Food" in desc
        assert "50.00" in desc

    def test_hash_deterministic(self, mock_encoder: AsyncMock) -> None:
        """测试哈希值确定性."""
        index = _TransactionIndex(encoder=mock_encoder, ndim=128)
        hash1 = index._hash("test text")  # pyright: ignore[reportPrivateUsage]
        hash2 = index._hash("test text")  # pyright: ignore[reportPrivateUsage]
        assert hash1 == hash2

    def test_hash_different_text(self, mock_encoder: AsyncMock) -> None:
        """测试不同文本产生不同哈希值."""
        index = _TransactionIndex(encoder=mock_encoder, ndim=128)
        hash1 = index._hash("text a")  # pyright: ignore[reportPrivateUsage]
        hash2 = index._hash("text b")  # pyright: ignore[reportPrivateUsage]
        assert hash1 != hash2


class TestHistoryIndex:
    """测试 _HistoryIndex 类."""

    def test_add_open_directive(self, mock_encoder: AsyncMock) -> None:
        """测试添加 Open 指令."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        open_dir = _make_open("Assets:Bank")
        run_async(index.add(open_dir))
        assert "Assets:Bank" in index.accounts

    def test_add_close_directive(self, mock_encoder: AsyncMock) -> None:
        """测试添加 Close 指令删除账户."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Assets:Bank")))
        assert "Assets:Bank" in index.accounts
        run_async(index.add(_make_close("Assets:Bank")))
        assert "Assets:Bank" not in index.accounts

    def test_add_open_duplicate_raises(self, mock_encoder: AsyncMock) -> None:
        """测试重复开户抛出 ValueError."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Assets:Bank")))
        with pytest.raises(ValueError, match="open existing account"):
            run_async(index.add(_make_open("Assets:Bank")))

    def test_add_close_non_existing_raises(self, mock_encoder: AsyncMock) -> None:
        """测试关闭不存在的账户抛出 ValueError."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        with pytest.raises(ValueError, match="close non-existing account"):
            run_async(index.add(_make_close("Assets:Bank")))

    def test_add_transaction_with_non_existing_account_raises(
        self, mock_encoder: AsyncMock
    ) -> None:
        """测试交易使用不存在的账户抛出 ValueError."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        txn = _make_transaction("2024-01-01", "Expenses:Food", Decimal("50.00"))
        with pytest.raises(ValueError, match="transaction with non-existing account"):
            run_async(index.add(txn))

    def test_add_ignored_directive(self, mock_encoder: AsyncMock) -> None:
        """测试非 Open/Close/Transaction 指令被忽略."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        balance = _make_balance("Assets:Bank")
        run_async(index.add(balance))  # Should not raise

    def test_check_transaction_flag_warning(self, mock_encoder: AsyncMock) -> None:
        """测试带有 FLAG_WARNING 的交易不被索引."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        txn = Transaction(
            meta={"filename": "test.beancount", "lineno": 1},
            date=datetime.date(2024, 1, 1),
            flag=FLAG_WARNING,
            payee=None,
            narration="test",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                Posting(
                    account="Expenses:Food",
                    units=Amount(Decimal("50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                Posting(
                    account="Assets:Bank",
                    units=Amount(Decimal("-50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )
        assert index._check_transaction(txn) is False  # pyright: ignore[reportPrivateUsage]

    def test_check_transaction_fewer_than_two_postings(
        self, mock_encoder: AsyncMock
    ) -> None:
        """测试少于 2 个 posting 的交易不被索引."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        txn = Transaction(
            meta={"filename": "test.beancount", "lineno": 1},
            date=datetime.date(2024, 1, 1),
            flag=FLAG_OKAY,
            payee=None,
            narration="test",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                Posting(
                    account="Assets:Bank",
                    units=Amount(Decimal("-50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )
        assert index._check_transaction(txn) is False  # pyright: ignore[reportPrivateUsage]

    def test_accounts_property(self, mock_encoder: AsyncMock) -> None:
        """测试 accounts 属性返回正确的账户映射."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        open_dir = _make_open("Assets:Bank", meta={"desc": "银行账户"})
        run_async(index.add(open_dir))
        accounts = index.accounts
        assert "Assets:Bank" in accounts
        assert accounts["Assets:Bank"]["desc"] == "银行账户"


class TestAccountPredictor:
    """测试 _AccountPredictor 类."""

    def test_check_transaction_single_posting(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试只有 1 个 posting 的交易适合预测."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        txn = Transaction(
            meta={"filename": "test.beancount", "lineno": 1},
            date=datetime.date(2024, 1, 1),
            flag=FLAG_OKAY,
            payee=None,
            narration="午餐",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                Posting(
                    account="Assets:Bank",
                    units=Amount(Decimal("-50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )
        assert predictor._check_transaction(txn) is True  # pyright: ignore[reportPrivateUsage]

    def test_check_transaction_two_postings(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试有 2 个 posting 的交易不适合预测."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        txn = _make_transaction("2024-01-01", "Expenses:Food", Decimal("50.00"))
        assert predictor._check_transaction(txn) is False  # pyright: ignore[reportPrivateUsage]

    def test_check_transaction_warning_flag(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试带 FLAG_WARNING 的交易不适合预测."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        txn = Transaction(
            meta={"filename": "test.beancount", "lineno": 1},
            date=datetime.date(2024, 1, 1),
            flag=FLAG_WARNING,
            payee=None,
            narration="test",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                Posting(
                    account="Assets:Bank",
                    units=Amount(Decimal("-50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )
        assert predictor._check_transaction(txn) is False  # pyright: ignore[reportPrivateUsage]

    def test_system_prompt_contains_accounts(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试系统提示包含可用账户信息."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food", meta={"desc": "餐饮"})))
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        prompt = predictor.system_prompt
        assert "Expenses:Food" in prompt
        assert "餐饮" in prompt
        assert "BEANCOUNT SYNTAX" in prompt

    def test_system_prompt_extra_instructions(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试系统提示包含额外指令."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="请使用中文",
        )
        prompt = predictor.system_prompt
        assert "ADDITIONAL INSTRUCTIONS" in prompt
        assert "请使用中文" in prompt

    def test_system_prompt_no_extra_instructions(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试无额外指令时不包含 ADDITIONAL INSTRUCTIONS."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        prompt = predictor.system_prompt
        assert "ADDITIONAL INSTRUCTIONS" not in prompt

    def test_predict_returns_none_for_multi_posting(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试对多 posting 交易预测返回 None."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        txn = _make_transaction("2024-01-01", "Expenses:Food", Decimal("50.00"))
        result = run_async(predictor.predict(txn))
        assert result is None
        mock_chat_bot.complete.assert_not_called()  # pyright: ignore[reportAny]

    def test_predict_calls_chat_bot(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试预测单 posting 交易会调用聊天机器人."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        run_async(index.add(_make_open("Assets:Bank")))

        mock_chat_bot.complete.return_value = '"Expenses:Food"'  # pyright: ignore[reportAny]

        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        txn = Transaction(
            meta={"filename": "test.beancount", "lineno": 1},
            date=datetime.date(2024, 1, 1),
            flag=FLAG_OKAY,
            payee="餐厅",
            narration="午餐",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                Posting(
                    account="Assets:Bank",
                    units=Amount(Decimal("-50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )
        result = run_async(predictor.predict(txn))
        mock_chat_bot.complete.assert_called_once()  # pyright: ignore[reportAny]
        assert result == "Expenses:Food"

    def test_predict_returns_none_for_null_response(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试 LLM 返回 null 时预测结果为 None."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        run_async(index.add(_make_open("Assets:Bank")))

        mock_chat_bot.complete.return_value = "null"  # pyright: ignore[reportAny]

        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        txn = Transaction(
            meta={"filename": "test.beancount", "lineno": 1},
            date=datetime.date(2024, 1, 1),
            flag=FLAG_OKAY,
            payee="餐厅",
            narration="午餐",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                Posting(
                    account="Assets:Bank",
                    units=Amount(Decimal("-50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )
        result = run_async(predictor.predict(txn))
        assert result is None

    def test_response_format(
        self, mock_chat_bot: AsyncMock, mock_encoder: AsyncMock
    ) -> None:
        """测试响应格式包含可用账户."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        run_async(index.add(_make_open("Assets:Bank")))
        predictor = _AccountPredictor(
            chat_bot=mock_chat_bot,
            index=index,
            extra_system_prompt="",
        )
        fmt = predictor.response_format

        # 使用 cast 告诉类型检查器期望的类型结构
        schema = fmt.get("schema", {})
        enum_values = cast("list[str | None]", schema.get("enum", []))

        assert "Expenses:Food" in enum_values
        assert "Assets:Bank" in enum_values
        assert None in enum_values


class TestHookInit:
    """测试 Hook 初始化."""

    @patch("beancount_daoru.hooks.predict_missing_posting._Encoder")
    @patch("beancount_daoru.hooks.predict_missing_posting._ChatBot")
    def test_hook_init_default_cache_dir(
        self, mock_chat_bot_cls: MagicMock, mock_encoder_cls: MagicMock
    ) -> None:
        """测试 Hook 使用默认缓存目录."""
        _ = mock_chat_bot_cls  # 标记参数为已使用
        _ = mock_encoder_cls
        hook = Hook(
            chat_model_settings=ChatModelSettings(
                name="test-model",
                base_url="http://localhost:8000",
                api_key="test-key",
            ),
            embed_model_settings=EmbeddingModelSettings(
                name="test-embed",
                base_url="http://localhost:8001",
                api_key="test-key",
            ),
        )
        assert hook is not None

    @patch("beancount_daoru.hooks.predict_missing_posting._Encoder")
    @patch("beancount_daoru.hooks.predict_missing_posting._ChatBot")
    def test_hook_init_custom_cache_dir(
        self,
        mock_chat_bot_cls: MagicMock,
        mock_encoder_cls: MagicMock,
        tmp_path: Path,
    ) -> None:
        """测试 Hook 使用自定义缓存目录."""
        _ = mock_chat_bot_cls  # 标记参数为已使用
        _ = mock_encoder_cls
        cache_dir = tmp_path / "test_cache"
        hook = Hook(
            chat_model_settings=ChatModelSettings(
                name="test-model",
                base_url="http://localhost:8000",
                api_key="test-key",
            ),
            embed_model_settings=EmbeddingModelSettings(
                name="test-embed",
                base_url="http://localhost:8001",
                api_key="test-key",
            ),
            cache_dir=cache_dir,
        )
        assert hook is not None


class TestHistoryIndexIntegration:
    """测试 _HistoryIndex 集成场景."""

    def test_add_transaction_after_open(self, mock_encoder: AsyncMock) -> None:
        """测试开户后添加交易."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        run_async(index.add(_make_open("Assets:Bank")))
        txn = _make_transaction("2024-01-01", "Expenses:Food", Decimal("50.00"))
        run_async(index.add(txn))
        # 交易成功添加, 编码器被调用
        mock_encoder.encode.assert_called()  # pyright: ignore[reportAny]

    def test_add_transaction_with_posting_flag_warning(
        self, mock_encoder: AsyncMock
    ) -> None:
        """测试带有 FLAG_WARNING posting 的交易不被索引."""
        index = _HistoryIndex(encoder=mock_encoder, ndim=128)
        run_async(index.add(_make_open("Expenses:Food")))
        run_async(index.add(_make_open("Assets:Bank")))
        txn = Transaction(
            meta={"filename": "test.beancount", "lineno": 1},
            date=datetime.date(2024, 1, 1),
            flag=FLAG_OKAY,
            payee=None,
            narration="test",
            tags=frozenset(),
            links=frozenset(),
            postings=[
                Posting(
                    account="Expenses:Food",
                    units=Amount(Decimal("50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=FLAG_WARNING,
                    meta=None,
                ),
                Posting(
                    account="Assets:Bank",
                    units=Amount(Decimal("-50.00"), "CNY"),
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )
        assert index._check_transaction(txn) is False  # pyright: ignore[reportPrivateUsage]


# ===== Helpers =====


def _make_transaction(date_str: str, account: str, amount: Decimal) -> Transaction:
    """创建一个双 posting 交易."""
    return Transaction(
        meta={"filename": "test.beancount", "lineno": 1},
        date=datetime.date.fromisoformat(date_str),
        flag=FLAG_OKAY,
        payee=None,
        narration="test transaction",
        tags=frozenset(),
        links=frozenset(),
        postings=[
            Posting(
                account=account,
                units=Amount(amount, "CNY"),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
            Posting(
                account="Assets:Bank",
                units=Amount(-amount, "CNY"),
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ],
    )


def _make_open(account: str, meta: dict[str, str | int] | None = None) -> Open:
    """创建一个 Open 指令."""
    if meta is None:
        meta = {"filename": "test.beancount", "lineno": 1}
    return Open(
        meta=meta,
        date=datetime.date(2020, 1, 1),
        account=account,
        currencies=[],
        booking=None,
    )


def _make_close(account: str) -> Close:
    """创建一个 Close 指令."""
    return Close(
        meta={"filename": "test.beancount", "lineno": 1},
        date=datetime.date(2024, 12, 31),
        account=account,
    )


def _make_balance(account: str) -> Balance:
    """创建一个 Balance 指令."""
    return Balance(
        meta={"filename": "test.beancount", "lineno": 1},
        date=datetime.date(2024, 1, 1),
        account=account,
        amount=Amount(Decimal("1000.00"), "CNY"),
        tolerance=None,
        diff_amount=None,
    )
