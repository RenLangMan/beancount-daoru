"""预测缺失会计科目钩子的单元测试."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beancount import (
    FLAG_OKAY,
    FLAG_WARNING,
    Close,
    Directive,
    Meta,
    Open,
    Posting,
    Transaction,
)

from beancount_daoru.hooks.predict_missing_posting import (
    AccountPredictor,
    ChatBot,
    ChatModelSettings,
    EmbeddingModelSettings,
    Encoder,
    HistoryIndex,
    Hook,
    TransactionIndex,
)

# ===== 测试固件 =====


@pytest.fixture
def temp_cache_dir() -> Path:
    """创建临时缓存目录."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def embedding_settings() -> EmbeddingModelSettings:
    """嵌入模型设置."""
    return {
        "name": "test-embedding-model",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-api-key",
    }


@pytest.fixture
def chat_settings() -> ChatModelSettings:
    """聊天模型设置."""
    return {
        "name": "test-chat-model",
        "base_url": "https://api.example.com/v1",
        "api_key": "test-api-key",
        "temperature": 0.7,
    }


@pytest.fixture
def sample_account_meta() -> Meta:
    """示例账户元数据."""
    return Meta({"desc": "Test account description"})


@pytest.fixture
def sample_transaction() -> Transaction:
    """创建示例交易."""
    return Transaction(
        date=date(2024, 1, 15),
        flag=FLAG_OKAY,
        narration="Test transaction",
        payee=None,
        links=(),
        tags=(),
        meta=Meta({"source": "test"}),
        postings=[
            Posting(
                account="Assets:Test:Checking",
                units=None,
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ],
    )


@pytest.fixture
def sample_transaction_with_flag() -> Transaction:
    """创建带警告标志的示例交易."""
    return Transaction(
        date=date(2024, 1, 15),
        flag=FLAG_WARNING,
        narration="Test transaction with flag",
        payee=None,
        links=(),
        tags=(),
        meta=Meta({}),
        postings=[
            Posting(
                account="Assets:Test:Checking",
                units=None,
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ],
    )


@pytest.fixture
def multi_posting_transaction() -> Transaction:
    """创建包含多个分录的交易(不适合预测)."""
    return Transaction(
        date=date(2024, 1, 15),
        flag=FLAG_OKAY,
        narration="Multi-posting transaction",
        payee=None,
        links=(),
        tags=(),
        meta=Meta({}),
        postings=[
            Posting(
                account="Assets:Test:Checking",
                units=None,
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
            Posting(
                account="Expenses:Test:Category",
                units=None,
                cost=None,
                price=None,
                flag=None,
                meta=None,
            ),
        ],
    )


@pytest.fixture
def transaction_with_posting_flag() -> Transaction:
    """创建分录带警告标志的交易."""
    return Transaction(
        date=date(2024, 1, 15),
        flag=FLAG_OKAY,
        narration="Transaction with posting flag",
        payee=None,
        links=(),
        tags=(),
        meta=Meta({}),
        postings=[
            Posting(
                account="Assets:Test:Checking",
                units=None,
                cost=None,
                price=None,
                flag=FLAG_WARNING,
                meta=None,
            ),
        ],
    )


@pytest.fixture
def sample_directives(sample_account_meta: Meta) -> list[Directive]:
    """创建示例指令列表."""
    return [
        Open(date(2024, 1, 1), "Assets:Test:Checking", None, sample_account_meta),
        Open(
            date(2024, 1, 1),
            "Expenses:Test:Food",
            None,
            Meta({"desc": "Food expenses"}),
        ),
        Close(date(2024, 12, 31), "Assets:Test:Checking", None),
    ]


# ===== Encoder 测试 =====


class TestEncoder:
    """Encoder 类的测试."""

    @pytest.mark.asyncio
    async def test_encode_cached(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试缓存命中时直接返回缓存结果."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        test_text = "test text for caching"

        with patch.object(
            encoder._Encoder__embeddings_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
            mock_create.return_value = mock_response

            result1 = await encoder.encode(test_text)
            result2 = await encoder.encode(test_text)

            assert result1 == result2
            assert result1 == [0.1, 0.2, 0.3]
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_encode_miss_cache(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试缓存未命中时调用 API 并缓存结果."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        test_text = "test text for API call"

        with patch.object(
            encoder._Encoder__embeddings_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.4, 0.5, 0.6])]
            mock_create.return_value = mock_response

            result = await encoder.encode(test_text)

            assert result == [0.4, 0.5, 0.6]
            mock_create.assert_called_once()
            mock_create.assert_called_with(
                input=test_text, model="test-embedding-model"
            )

    @pytest.mark.asyncio
    async def test_encode_different_texts(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试不同文本产生不同嵌入."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)

        with patch.object(
            encoder._Encoder__embeddings_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
            mock_create.return_value = mock_response

            result1 = await encoder.encode("text1")
            mock_response.data = [MagicMock(embedding=[0.4, 0.5, 0.6])]
            result2 = await encoder.encode("text2")

            assert result1 != result2
            assert mock_create.call_count == 2


# ===== TransactionIndex 测试 =====


class TestTransactionIndex:
    """TransactionIndex 类的测试."""

    @pytest.mark.asyncio
    async def test_add_transaction(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试添加交易到索引."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = TransactionIndex(encoder=encoder, ndim=3)
        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting(
                    account="Assets:Test:Checking",
                    units=None,
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
                Posting(
                    account="Expenses:Test:Food",
                    units=None,
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        with patch.object(encoder, "encode", new_callable=AsyncMock) as mock_encode:
            mock_encode.return_value = [0.1, 0.2, 0.3]
            await index.add(txn)

            results = await index.search(txn, topk=1)
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_search_empty_index(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试在空索引中搜索."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = TransactionIndex(encoder=encoder, ndim=3)
        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting(
                    account="Assets:Test:Checking",
                    units=None,
                    cost=None,
                    price=None,
                    flag=None,
                    meta=None,
                ),
            ],
        )

        with patch.object(encoder, "encode", new_callable=AsyncMock) as mock_encode:
            mock_encode.return_value = [0.1, 0.2, 0.3]
            results = await index.search(txn, topk=1)
            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_hash_consistency(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试哈希值的一致性."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = TransactionIndex(encoder=encoder, ndim=3)
        text = "consistent hash test"

        hash1 = index._hash(text)
        hash2 = index._hash(text)

        assert hash1 == hash2
        assert isinstance(hash1, int)

    @pytest.mark.asyncio
    async def test_hash_different_texts(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试不同文本产生不同哈希值."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = TransactionIndex(encoder=encoder, ndim=3)

        hash1 = index._hash("text1")
        hash2 = index._hash("text2")

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_search_topk(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试搜索返回指定数量的结果."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = TransactionIndex(encoder=encoder, ndim=3)

        txn1 = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Transaction 1",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        with patch.object(encoder, "encode", new_callable=AsyncMock) as mock_encode:
            mock_encode.return_value = [0.1, 0.2, 0.3]
            await index.add(txn1)

            search_txn = Transaction(
                date=date(2024, 1, 16),
                flag=FLAG_OKAY,
                narration="Search transaction",
                payee=None,
                links=(),
                tags=(),
                meta=Meta({}),
                postings=[Posting("Assets:Test", None, None, None, None, None)],
            )
            results = await index.search(search_txn, topk=5)
            assert len(results) == 1


# ===== HistoryIndex 测试 =====


class TestHistoryIndex:
    """HistoryIndex 类的测试."""

    @pytest.mark.asyncio
    async def test_add_open_directive(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试添加 Open 指令."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        directive = Open(
            date(2024, 1, 1),
            "Assets:Test:Checking",
            None,
            Meta({"desc": "Test account"}),
        )

        await index.add(directive)

        assert "Assets:Test:Checking" in index.accounts

    @pytest.mark.asyncio
    async def test_add_open_duplicate_raises(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试重复添加同一账户的 Open 指令抛出异常."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        directive1 = Open(date(2024, 1, 1), "Assets:Test:Checking", None, Meta({}))
        directive2 = Open(date(2024, 1, 2), "Assets:Test:Checking", None, Meta({}))

        await index.add(directive1)

        with pytest.raises(ValueError, match="open existing account"):
            await index.add(directive2)

    @pytest.mark.asyncio
    async def test_add_close_directive(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试添加 Close 指令."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        open_directive = Open(date(2024, 1, 1), "Assets:Test:Checking", None, Meta({}))
        close_directive = Close(date(2024, 12, 31), "Assets:Test:Checking", None)

        await index.add(open_directive)
        assert "Assets:Test:Checking" in index.accounts

        await index.add(close_directive)
        assert "Assets:Test:Checking" not in index.accounts

    @pytest.mark.asyncio
    async def test_add_close_non_existing_raises(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试关闭不存在的账户抛出异常."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        directive = Close(date(2024, 12, 31), "Assets:NonExistent", None)

        with pytest.raises(ValueError, match="close non-existing account"):
            await index.add(directive)

    @pytest.mark.asyncio
    async def test_add_transaction_with_non_existing_account(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试添加使用不存在账户的交易抛出异常."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:NonExistent", None, None, None, None, None)],
        )

        with pytest.raises(ValueError, match="transaction with non-existing account"):
            await index.add(txn)

    def test_check_transaction_valid(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试有效交易的检查."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Valid transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        assert index._check_transaction(txn) is True

    def test_check_transaction_with_warning_flag(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试带警告标志的交易被拒绝."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_WARNING,
            narration="Warning transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        assert index._check_transaction(txn) is False

    def test_check_transaction_single_posting(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试只有一个分录的交易被拒绝."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Single posting",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        assert index._check_transaction(txn) is False

    def test_check_transaction_posting_with_flag(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试分录带警告标志的交易被拒绝."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Posting with flag",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, FLAG_WARNING, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        assert index._check_transaction(txn) is False

    @pytest.mark.asyncio
    async def test_search_returns_similar_transactions(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试搜索返回相似交易."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)

        open_directive = Open(date(2024, 1, 1), "Assets:Test", None, Meta({}))
        await index.add(open_directive)

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        await index.add(txn)

        search_txn = Transaction(
            date=date(2024, 1, 16),
            flag=FLAG_OKAY,
            narration="Search transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        with patch.object(encoder, "encode", new_callable=AsyncMock) as mock_encode:
            mock_encode.return_value = [0.1, 0.2, 0.3]
            results = await index.search(search_txn, n_few_shots=3)

        assert len(results) <= 3


# ===== ChatBot 测试 =====


class TestChatBot:
    """ChatBot 类的测试."""

    @pytest.mark.asyncio
    async def test_complete_success(self, chat_settings: ChatModelSettings) -> None:
        """测试成功完成聊天补全."""
        bot = ChatBot(model_settings=chat_settings)

        with patch.object(
            bot._ChatBot__chat_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [
                MagicMock(message=MagicMock(content='"Expenses:Test"'))
            ]
            mock_create.return_value = mock_response

            result = await bot.complete(
                user_prompt="Test prompt",
                system_prompt="Test system",
                response_format={
                    "name": "test",
                    "strict": True,
                    "schema": {"type": "string"},
                },
            )

            assert result == '"Expenses:Test"'
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_with_temperature(
        self, chat_settings: ChatModelSettings
    ) -> None:
        """测试带温度参数的聊天补全."""
        bot = ChatBot(model_settings=chat_settings)

        with patch.object(
            bot._ChatBot__chat_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content='"Result"'))]
            mock_create.return_value = mock_response

            await bot.complete(
                user_prompt="Test",
                system_prompt="System",
                response_format={
                    "name": "test",
                    "strict": True,
                    "schema": {"type": "string"},
                },
            )

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_complete_content_none_raises(
        self, chat_settings: ChatModelSettings
    ) -> None:
        """测试模型返回 None 时抛出异常."""
        bot = ChatBot(model_settings=chat_settings)

        with patch.object(
            bot._ChatBot__chat_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=MagicMock(content=None))]
            mock_create.return_value = mock_response

            with pytest.raises(ValueError, match="content is None"):
                await bot.complete(
                    user_prompt="Test",
                    system_prompt="System",
                    response_format={
                        "name": "test",
                        "strict": True,
                        "schema": {"type": "string"},
                    },
                )


# ===== AccountPredictor 测试 =====


class TestAccountPredictor:
    """AccountPredictor 类的测试."""

    @pytest.mark.asyncio
    async def test_check_transaction_valid(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试有效交易的检查."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(model_settings=chat_settings)
        predictor = AccountPredictor(
            chat_bot=bot,
            index=index,
            extra_system_prompt="",
        )

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Valid transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        assert predictor._check_transaction(txn) is True

    def test_check_transaction_multi_posting(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试多分录交易被拒绝(预测只需要一个缺失分录)."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(model_settings=chat_settings)
        predictor = AccountPredictor(
            chat_bot=bot,
            index=index,
            extra_system_prompt="",
        )

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Multi posting",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        assert predictor._check_transaction(txn) is False

    def test_system_prompt_contains_role(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试系统提示包含角色定义."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(
            model_settings={"name": "test", "base_url": "url", "api_key": "key"}
        )
        predictor = AccountPredictor(
            chat_bot=bot,
            index=index,
            extra_system_prompt="",
        )

        prompt = predictor.system_prompt

        assert "ROLE:" in prompt
        assert "RULE:" in prompt
        assert "BEANCOUNT SYNTAX:" in prompt
        assert "CLASSIFICATION LOGIC:" in prompt

    def test_system_prompt_with_extra_prompt(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试带额外提示的系统提示."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(
            model_settings={"name": "test", "base_url": "url", "api_key": "key"}
        )
        predictor = AccountPredictor(
            chat_bot=bot,
            index=index,
            extra_system_prompt="Always prefer Expenses:Food",
        )

        prompt = predictor.system_prompt

        assert "ADDITIONAL INSTRUCTIONS:" in prompt
        assert "Always prefer Expenses:Food" in prompt

    @pytest.mark.asyncio
    async def test_user_prompt_format(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
    ) -> None:
        """测试用户提示的格式."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test narration",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        open_directive = Open(
            date(2024, 1, 1), "Assets:Test", None, Meta({"desc": "Test desc"})
        )
        await index.add(open_directive)

        bot = ChatBot(
            model_settings={"name": "test", "base_url": "url", "api_key": "key"}
        )
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        with patch.object(index, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = []
            prompt = await predictor.user_prompt(txn)

        assert "PREDICT MISSING ACCOUNT FOR THIS TRANSACTION:" in prompt
        assert "HISTORICAL MATCHES: not found" in prompt

    @pytest.mark.asyncio
    async def test_user_prompt_with_similar(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
    ) -> None:
        """测试带相似交易的用户提示."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)

        similar_txn = Transaction(
            date=date(2024, 1, 10),
            flag=FLAG_OKAY,
            narration="Similar transaction",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Similar", None, None, None, None, None),
            ],
        )

        open_directive = Open(date(2024, 1, 1), "Assets:Test", None, Meta({}))
        await index.add(open_directive)

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        bot = ChatBot(
            model_settings={"name": "test", "base_url": "url", "api_key": "key"}
        )
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        with patch.object(index, "search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [(similar_txn, "Expenses:Similar", 0.1)]
            prompt = await predictor.user_prompt(txn)

        assert "HISTORICAL MATCHES (1):" in prompt
        assert "match" in prompt
        assert "Expenses:Similar" in prompt

    def test_response_format(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试响应格式的定义."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        index._HistoryIndex__data_per_account = {
            "Assets:Test": (Meta({}), MagicMock()),
            "Expenses:Test": (Meta({}), MagicMock()),
        }

        bot = ChatBot(
            model_settings={"name": "test", "base_url": "url", "api_key": "key"}
        )
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        fmt = predictor.response_format

        assert fmt["name"] == "predictted account or null"
        assert fmt["strict"] is True
        assert "string" in fmt["schema"]["type"]
        assert "null" in fmt["schema"]["type"]
        assert "Assets:Test" in fmt["schema"]["enum"]
        assert "Expenses:Test" in fmt["schema"]["enum"]
        assert None in fmt["schema"]["enum"]

    @pytest.mark.asyncio
    async def test_predict_invalid_transaction_returns_none(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试无效交易返回 None."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(model_settings=chat_settings)
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        multi_posting_txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Multi posting",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[
                Posting("Assets:Test", None, None, None, None, None),
                Posting("Expenses:Test", None, None, None, None, None),
            ],
        )

        result = await predictor.predict(multi_posting_txn)
        assert result is None

    @pytest.mark.asyncio
    async def test_predict_returns_formatted_account(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试预测返回带感叹号的账户名."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(model_settings=chat_settings)
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        with patch.object(bot, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = '"Expenses:Food"'

            with patch.object(index, "search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = []
                result = await predictor.predict(txn)

        assert result == "! Expenses:Food"

    @pytest.mark.asyncio
    async def test_predict_returns_null_for_null_response(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试模型返回 NULL 时返回 None."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(model_settings=chat_settings)
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        with patch.object(bot, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = "null"

            with patch.object(index, "search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = []
                result = await predictor.predict(txn)

        assert result is None

    @pytest.mark.asyncio
    async def test_predict_preserves_exclamation(
        self,
        temp_cache_dir: Path,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试如果账户名已带感叹号则不再添加."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(model_settings=chat_settings)
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        with patch.object(bot, "complete", new_callable=AsyncMock) as mock_complete:
            mock_complete.return_value = '"! Expenses:Food"'

            with patch.object(index, "search", new_callable=AsyncMock) as mock_search:
                mock_search.return_value = []
                result = await predictor.predict(txn)

        assert result == "! Expenses:Food"


# ===== Hook 集成测试 =====


class TestHook:
    """Hook 类的测试."""

    def test_hook_initialization(
        self,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试钩子初始化."""
        hook = Hook(
            chat_model_settings=chat_settings,
            embed_model_settings=embedding_settings,
        )

        assert hook is not None
        assert hasattr(hook, "_Hook__chat_bot")
        assert hasattr(hook, "_Hook__encoder")

    def test_hook_with_cache_dir(
        self,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试带缓存目录的钩子初始化."""
        with TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            hook = Hook(
                chat_model_settings=chat_settings,
                embed_model_settings=embedding_settings,
                cache_dir=cache_dir,
            )

            assert hook is not None

    def test_hook_with_extra_prompt(
        self,
        embedding_settings: EmbeddingModelSettings,
        chat_settings: ChatModelSettings,
    ) -> None:
        """测试带额外提示的钩子初始化."""
        hook = Hook(
            chat_model_settings=chat_settings,
            embed_model_settings=embedding_settings,
            extra_system_prompt="Custom instructions",
        )

        assert hook is not None


# ===== 边界情况测试 =====


class TestEdgeCases:
    """边界情况测试."""

    @pytest.mark.asyncio
    async def test_encoder_empty_text(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试空文本编码."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)

        with patch.object(
            encoder._Encoder__embeddings_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.0, 0.0, 0.0])]
            mock_create.return_value = mock_response

            result = await encoder.encode("")

            assert result == [0.0, 0.0, 0.0]

    @pytest.mark.asyncio
    async def test_encoder_unicode_text(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试 Unicode 文本编码."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        unicode_text = "测试中文文本 テスト 한국어"

        with patch.object(
            encoder._Encoder__embeddings_client, "create", new_callable=AsyncMock
        ) as mock_create:
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1, 0.2, 0.3])]
            mock_create.return_value = mock_response

            result = await encoder.encode(unicode_text)

            assert result == [0.1, 0.2, 0.3]
            mock_create.assert_called_once()

    def test_hash_unicode(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试 Unicode 文本哈希."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = TransactionIndex(encoder=encoder, ndim=3)

        hash1 = index._hash("中文测试")
        hash2 = index._hash("中文测试")

        assert hash1 == hash2
        assert isinstance(hash1, int)

    def test_account_predictor_check_none_flag(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试 flag 为 None 的交易."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(
            model_settings={"name": "test", "base_url": "url", "api_key": "key"}
        )
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=None,
            narration="Test",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        assert predictor._check_transaction(txn) is True

    def test_account_predictor_check_posting_none_flag(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试 posting flag 为 None 的交易."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        bot = ChatBot(
            model_settings={"name": "test", "base_url": "url", "api_key": "key"}
        )
        predictor = AccountPredictor(chat_bot=bot, index=index, extra_system_prompt="")

        txn = Transaction(
            date=date(2024, 1, 15),
            flag=FLAG_OKAY,
            narration="Test",
            payee=None,
            links=(),
            tags=(),
            meta=Meta({}),
            postings=[Posting("Assets:Test", None, None, None, None, None)],
        )

        assert predictor._check_transaction(txn) is True

    def test_history_index_accounts_property(
        self, temp_cache_dir: Path, embedding_settings: EmbeddingModelSettings
    ) -> None:
        """测试 accounts 属性返回正确的映射."""
        encoder = Encoder(model_settings=embedding_settings, cache_dir=temp_cache_dir)
        index = HistoryIndex(encoder=encoder, ndim=3)
        index._HistoryIndex__data_per_account = {
            "Assets:Test1": (Meta({"desc": "Account 1"}), MagicMock()),
            "Assets:Test2": (Meta({"desc": "Account 2"}), MagicMock()),
        }

        accounts = index.accounts

        assert "Assets:Test1" in accounts
        assert "Assets:Test2" in accounts
        assert accounts["Assets:Test1"].get("desc") == "Account 1"
