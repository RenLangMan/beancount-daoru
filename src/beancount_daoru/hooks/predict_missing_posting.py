"""使用 AI 预测交易中缺失会计科目的钩子.

此模块提供了一个复杂的钩子实现,使用机器学习技术基于历史数据
和交易描述的自然语言处理来预测导入交易中缺失的会计科目。
"""

import asyncio
import json
import re
from collections.abc import Mapping
from hashlib import blake2b
from pathlib import Path
from typing import TypedDict

import numpy as np
from beancount import (
    FLAG_OKAY,
    Account,
    Close,
    Directive,
    Directives,
    Meta,
    Open,
    Posting,
    Transaction,
    format_entry,
)
from diskcache import Cache
from openai import AsyncOpenAI
from openai.types.shared_params.response_format_json_schema import JSONSchema
from pydantic import TypeAdapter
from tqdm import tqdm
from typing_extensions import NotRequired, override
from usearch.index import Index, Matches

from beancount_daoru.hook import Hook as BaseHook
from beancount_daoru.hook import Imported


class EmbeddingModelSettings(TypedDict):
    """嵌入模型设置.

    属性:
        name: 模型名称标识符。
        base_url: 模型 API 的基础 URL。
        api_key: 认证用的 API 密钥。
    """

    name: str
    base_url: str
    api_key: str


class _Encoder:
    """文本编码器,负责将文本转换为向量嵌入.

    此类封装了文本向量化的逻辑,包括:
        - 使用 OpenAI 兼容 API 生成文本嵌入
        - 磁盘缓存机制避免重复计算
        - 异步 API 调用提高性能

    参数:
        model_settings: 嵌入模型配置
        cache_dir: 缓存目录路径
    """

    def __init__(
        self,
        /,
        model_settings: EmbeddingModelSettings,
        cache_dir: Path,
    ) -> None:
        """初始化编码器.

        参数:
            model_settings: 嵌入模型配置
            cache_dir: 缓存目录路径
        """
        self.__model_name = model_settings.get("name")
        self.__embeddings_client = AsyncOpenAI(
            base_url=model_settings.get("base_url"),
            api_key=model_settings.get("api_key"),
        ).embeddings

        cache_dir.mkdir(parents=True, exist_ok=True)
        _cache_prefix = re.sub(r"[^a-zA-Z0-9]", "_", self.__model_name)
        cache_path = cache_dir / f"{_cache_prefix}.embeddings.diskcache"
        self.__cache = Cache(cache_path)
        self.__validator = TypeAdapter(list[float])

    async def encode(self, text: str) -> list[float]:
        """将文本编码为向量嵌入.

        参数:
            text: 待编码的文本

        返回:
            表示文本嵌入的浮点数列表

        注意:
            如果文本已在缓存中,直接返回缓存结果;
            否则调用 API 获取嵌入并缓存。
        """
        if text in self.__cache:
            cached = self.__cache[text]  # pyright: ignore[reportUnknownVariableType]
            return self.__validator.validate_python(cached)

        response = await self.__embeddings_client.create(
            input=text,
            model=self.__model_name,
        )
        embedding = response.data[0].embedding

        self.__cache[text] = embedding
        return embedding


class _TransactionIndex:
    """交易索引,用于相似交易检索.

    此类维护一个向量索引,用于根据交易描述的语义相似性
    快速检索历史交易。

    参数:
        encoder: 文本编码器
        ndim: 向量维度
    """

    def __init__(
        self,
        encoder: _Encoder,
        ndim: int,
    ) -> None:
        """初始化交易索引.

        参数:
            encoder: 文本编码器
            ndim: 向量维度
        """
        self.__encoder = encoder
        self.__transaction_mapping: dict[int, Transaction] = {}
        self.__embedding_index = Index(ndim=ndim)

    async def add(self, transaction: Transaction) -> None:
        """向索引中添加交易.

        参数:
            transaction: 要添加的 Beancount 交易
        """
        description = self._create_description(transaction)
        transaction_id = self._hash(description)
        if transaction_id not in self.__embedding_index:
            embedding = await self.__encoder.encode(description)
            _ = self.__embedding_index.add(
                keys=transaction_id,
                vectors=np.array(embedding),
            )
            self.__transaction_mapping[transaction_id] = transaction

    def _create_description(self, transaction: Transaction) -> str:
        """创建交易的文本描述.

        参数:
            transaction: Beancount 交易

        返回:
            交易的格式化字符串表示
        """
        return format_entry(transaction)

    def _hash(self, text: str) -> int:
        """计算文本的哈希值.

        参数:
            text: 输入文本

        返回:
            文本的整数哈希值
        """
        hasher = blake2b(digest_size=8)
        hasher.update(text.encode("utf-8"))
        return int.from_bytes(hasher.digest(), "big")

    async def search(
        self, transaction: Transaction, topk: int
    ) -> list[tuple[Transaction, float]]:
        """搜索与给定交易最相似的交易.

        参数:
            transaction: 查询交易
            topk: 返回的最相似交易数量

        返回:
            (交易, 距离分数) 元组的列表,按相似度排序
        """
        description = self._create_description(transaction)
        query_embedding = await self.__encoder.encode(description)

        matches = self.__embedding_index.search(
            vectors=np.array(query_embedding),
            count=topk,
        )

        if not isinstance(matches, Matches):
            raise TypeError(matches)

        return [
            (self.__transaction_mapping[match.key], float(match.distance))
            for match in matches
        ]


class _HistoryIndex:
    """历史交易索引管理器.

    此类管理按账户组织的交易索引,用于维护整个账簿的历史交易数据,
    支持按账户进行相似交易检索。

    参数:
        encoder: 文本编码器
        ndim: 向量维度
    """

    def __init__(
        self,
        encoder: _Encoder,
        ndim: int,
    ) -> None:
        """初始化历史索引.

        参数:
            encoder: 文本编码器
            ndim: 向量维度
        """
        self.__encoder = encoder
        self.__ndim = ndim
        self.__data_per_account: dict[Account, tuple[Meta, _TransactionIndex]] = {}

    async def add(self, directive: Directive) -> None:
        """向历史索引中添加指令.

        参数:
            directive: Beancount 指令(Open、Close 或 Transaction)

        异常:
            ValueError: 当账户重复开户、关闭不存在的账户或
                       交易使用不存在的账户时抛出
        """
        match directive:
            case Open():
                if directive.account in self.__data_per_account:
                    msg = f"open existing account: {directive}"
                    raise ValueError(msg)
                txn_index = _TransactionIndex(
                    encoder=self.__encoder,
                    ndim=self.__ndim,
                )
                self.__data_per_account[directive.account] = (directive.meta, txn_index)
            case Close():
                if directive.account not in self.__data_per_account:
                    msg = f"close non-existing account: {directive}"
                    raise ValueError(msg)
                del self.__data_per_account[directive.account]
            case Transaction() as txn:
                if self._check_transaction(txn):
                    for posting in txn.postings:
                        if posting.account not in self.__data_per_account:
                            msg = f"transaction with non-existing account: {txn}"
                            raise ValueError(msg)
                        other_postings = [p for p in txn.postings if p is not posting]
                        missing_posting_txn = txn._replace(postings=other_postings)
                        index = self.__data_per_account[posting.account][1]
                        await index.add(missing_posting_txn)
            case _:
                pass

    def _check_transaction(self, transaction: Transaction) -> bool:
        """检查交易是否有效,可用于索引.

        参数:
            transaction: Beancount 交易

        返回:
            如果交易有效返回 True,否则返回 False
        """
        if transaction.flag is not None and transaction.flag != FLAG_OKAY:
            return False
        if len(transaction.postings) < 2:  # noqa: PLR2004
            return False
        for posting in transaction.postings:
            if posting.flag is not None and posting.flag != FLAG_OKAY:
                return False
        return True

    @property
    def accounts(self) -> Mapping[Account, Meta]:
        """获取所有可用账户及其元数据.

        返回:
            账户名到元数据的映射
        """
        return {account: meta for account, (meta, _) in self.__data_per_account.items()}

    async def search(
        self, transaction: Transaction, n_few_shots: int
    ) -> list[tuple[Transaction, Account, float]]:
        """搜索与给定交易相似的交易.

        参数:
            transaction: 查询交易
            n_few_shots: 返回的相似交易数量

        返回:
            (交易, 账户名, 距离分数) 元组的列表,按相似度排序
        """
        candidates: list[tuple[Transaction, Account, float]] = []
        for account, (_, transaction_index) in self.__data_per_account.items():
            for target_transaction, distance in await transaction_index.search(
                transaction, 1
            ):
                candidates.append((target_transaction, account, distance))

        candidates.sort(key=lambda x: x[2])
        return candidates[:n_few_shots]


class ChatModelSettings(TypedDict):
    """聊天模型设置.

    属性:
        name: 模型名称标识符。
        base_url: 模型 API 的基础 URL。
        api_key: 认证用的 API 密钥。
        temperature: 生成温度参数(控制随机性),可选。
    """

    name: str
    base_url: str
    api_key: str
    temperature: NotRequired[float]


class _ChatBot:
    """聊天机器人封装,负责与大语言模型交互.

    此类封装了与大语言模型的交互逻辑,包括:
        - 系统提示和用户提示的组合
        - JSON 格式响应的结构化输出
        - 异步 API 调用

    参数:
        model_settings: 聊天模型配置
    """

    def __init__(self, *, model_settings: ChatModelSettings) -> None:
        """初始化聊天机器人.

        参数:
            model_settings: 聊天模型配置
        """
        self.__model_name = model_settings.get("name")
        self.__chat_client = AsyncOpenAI(
            base_url=model_settings.get("base_url"),
            api_key=model_settings.get("api_key"),
        ).chat.completions
        self.__temperature = model_settings.get("temperature", None)

    async def complete(
        self,
        user_prompt: str,
        /,
        system_prompt: str,
        response_format: JSONSchema,
    ) -> str:
        """执行聊天补全请求.

        参数:
            user_prompt: 用户提示内容
            system_prompt: 系统提示内容
            response_format: 响应格式的 JSON Schema

        返回:
            模型返回的内容字符串

        异常:
            ValueError: 当模型返回内容为 None 时抛出
        """
        response = await self.__chat_client.create(
            model=self.__model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": response_format,
            },
            temperature=self.__temperature,
        )
        content = response.choices[0].message.content
        if content is None:
            msg = "content is None"
            raise ValueError(msg)
        return content


class _AccountPredictor:
    """会计科目预测器.

    此类结合历史交易索引和大语言模型来预测交易中缺失的会计科目。

    参数:
        chat_bot: 聊天机器人实例
        index: 历史交易索引
        extra_system_prompt: 额外的系统提示
    """

    def __init__(
        self,
        /,
        chat_bot: _ChatBot,
        index: _HistoryIndex,
        extra_system_prompt: str,
    ) -> None:
        """初始化会计科目预测器.

        参数:
            chat_bot: 聊天机器人实例
            index: 历史交易索引
            extra_system_prompt: 额外的系统提示
        """
        self.__chat_bot = chat_bot
        self.__index = index
        self.__extra_system_prompt = extra_system_prompt
        self.__validator = TypeAdapter(str | None)

    def _check_transaction(self, transaction: Transaction) -> bool:
        """检查交易是否适合进行科目预测.

        参数:
            transaction: Beancount 交易

        返回:
            如果交易适合预测返回 True,否则返回 False
        """
        if transaction.flag is not None and transaction.flag != FLAG_OKAY:
            return False
        if len(transaction.postings) != 1:
            return False
        for posting in transaction.postings:
            if posting.flag is not None and posting.flag != FLAG_OKAY:
                return False
        return True

    @property
    def system_prompt(self) -> str:
        """构建系统提示.

        返回:
            完整的系统提示字符串,包含角色定义、规则、语法说明和可用账户
        """
        builder: list[str] = []

        role = (
            "ROLE: Beancount accounting expert. "
            "Your ONLY task is to predict missing accounts for transactions."
        )
        builder.append(role)

        rule = (
            "RULE: Return ONLY the exact account name if HIGH confident. "
            "Otherwise return 'NULL'. NO explanations."
        )
        builder.append(rule)
        builder.append("")

        # Beancount syntax
        builder.append("")
        builder.append("BEANCOUNT SYNTAX:")
        builder.append("YYYY-MM-DD [[Payee] Narration]")
        builder.append("  [Key: Value]")
        builder.append("  [Key: Value]")
        builder.append("  ...")
        builder.append("  Account Amount")
        builder.append("  Account Amount")
        builder.append("  ...")

        # Account structure rules
        builder.append("ACCOUNT HIERARCHY (MOST SPECIFIC FIRST):")
        builder.append("- Expenses:[Category]:[Subcategory] - For spending")
        builder.append("- Assets:[Account] - For money storage")
        builder.append("- Income:[Source] - For earnings")
        builder.append("- Liabilities:[Debt] - For debts")
        builder.append("- Equity:[Adjustment] - For net worth changes")
        builder.append("")

        # Classification logic
        builder.append("")
        builder.append("CLASSIFICATION LOGIC:")
        builder.append("- Analyze Payee, Narration and key-value Metadata for clues")
        builder.append("- Match expense types to most specific sub-account available")
        builder.append("- Prefer historical patterns over generic accounts")

        # other prompt
        if self.__extra_system_prompt:
            builder.append("")
            builder.append("ADDITIONAL INSTRUCTIONS:")
            builder.append(self.__extra_system_prompt)

        # Available accounts with metadata
        builder.append("")
        builder.append("AVAILABLE ACCOUNTS WITH DESCRIPTION:")
        for account, meta in self.__index.accounts.items():
            builder.append(f"- {account}: {meta.get('desc', 'No description')}")

        return "\n".join(builder)

    async def user_prompt(self, transaction: Transaction) -> str:
        """构建用户提示.

        参数:
            transaction: 需要预测的 Beancount 交易

        返回:
            用户提示字符串,包含交易信息和相似历史示例
        """
        similar_examples = await self.__index.search(transaction, 3)

        builder: list[str] = []

        builder.append("PREDICT MISSING ACCOUNT FOR THIS TRANSACTION:")
        builder.append(format_entry(transaction).strip())

        if similar_examples:
            builder.append(f"HISTORICAL MATCHES ({len(similar_examples)}):")
            for idx, (txn, account, distance) in enumerate(similar_examples, 1):
                sim = 1 / (1 + distance)
                builder.append("")
                builder.append(
                    f"Example #{idx} ({sim:.0%} match) is predictted as {account!r}:"
                )
                builder.append(format_entry(txn).strip())
        else:
            builder.append("HISTORICAL MATCHES: not found")

        return "\n".join(builder)

    @property
    def response_format(self) -> JSONSchema:
        """获取响应格式的 JSON Schema.

        返回:
            限制响应只能为可用账户名或 null 的 JSON 对象,允许更灵活的响应格式
        """
        return {
            "name": "predictted_account",
            "strict": False,  # 改为 False,允许更灵活的响应
            "schema": {
                "type": "object",
                "properties": {
                    "account": {
                        "type": ["string", "null"],
                        "description": (
                            "The predicted account name or null if not confident"
                        ),
                    }
                },
                "required": ["account"],
            },
        }

    async def predict(self, transaction: Transaction) -> Account | None:
        """预测交易中缺失的会计科目.

        此方法使用大语言模型分析交易上下文,预测最合适的会计科目。
        预测流程包括:
            1. 验证交易是否适合预测(单条 posting,状态正常)
            2. 构建用户提示(包含历史相似交易示例)
            3. 调用 LLM 获取预测结果
            4. 解析 JSON 响应并返回账户名

        参数:
            transaction: Beancount 交易对象,应包含单条 posting

        返回:
            预测的账户名(如 "Expenses:Food"),如果无法预测则返回 None

        注意:
            - 返回的账户名不带 '!' 前缀,前缀由调用方添加
            - 如果 LLM 返回 null 或 NULL,表示无法预测
            - 支持解析 JSON 格式的响应:{"account": "Expenses:Food"}
        """
        # 检查交易是否适合预测
        if not self._check_transaction(transaction):
            return None

        # 构建用户提示
        user_prompt = await self.user_prompt(transaction)

        # 调用 LLM 获取预测
        response = await self.__chat_bot.complete(
            user_prompt,
            system_prompt=self.system_prompt,
            response_format=self.response_format,
        )

        # 解析 JSON 响应
        # 验证响应

        try:
            data = json.loads(response)
            predicted_account = data.get("account")
        except (json.JSONDecodeError, AttributeError, KeyError):
            # 如果 JSON 解析失败,尝试直接使用响应文本
            predicted_account = response.strip() if response else None

        # 验证并返回预测结果
        if predicted_account and predicted_account not in ("NULL", "null"):
            # 直接返回账户名,不添加 '!' 前缀
            # 前缀由 _process_directive 方法根据账户类型添加
            return predicted_account

        return None


class Hook(BaseHook):
    """预测交易中缺失会计科目的钩子.

    使用大语言模型分析交易上下文和历史模式,为缺失的记账分录
    预测最合适的会计科目。

    此钩子实现了一种复杂的方法,使用大语言模型和相似性搜索
    自动分类交易记账分录。底层技术包括:

    1. **嵌入向量化**:使用嵌入模型将交易描述转换为捕获语义
       含义的向量表示。

    2. **相似性检索**:在现有账簿中执行相似性搜索,基于向量
       表示查找历史相似交易。

    3. **大语言模型分类**:利用大语言模型,结合历史交易模式
       和当前交易的上下文信息进行智能分类决策。

    4. **缓存机制**:将向量缓存到磁盘,避免重复计算的开销,
       提高后续运行的性能。

    参数:
        chat_model_settings: 聊天模型配置
        embed_model_settings: 嵌入模型配置
        cache_dir: 缓存索引和嵌入的目录路径
        extra_system_prompt: 给大语言模型的额外指令
    """

    def __init__(
        self,
        *,
        chat_model_settings: ChatModelSettings,
        embed_model_settings: EmbeddingModelSettings,
        cache_dir: Path | None = None,
        extra_system_prompt: str = "",
    ) -> None:
        """初始化会计科目预测钩子.

        参数:
            chat_model_settings: 聊天模型配置
            embed_model_settings: 嵌入模型配置
            cache_dir: 缓存索引和嵌入的目录路径
            extra_system_prompt: 给大语言模型的额外指令
        """
        if cache_dir is None:
            cache_dir = Path(Path.cwd(), ".cache", *__name__.split("."))
        self.__chat_bot = _ChatBot(model_settings=chat_model_settings)
        self.__encoder = _Encoder(
            model_settings=embed_model_settings,
            cache_dir=cache_dir,
        )
        self.__extra_system_prompt = extra_system_prompt

    @override
    def __call__(
        self, imported: list[Imported], existing: Directives
    ) -> list[Imported]:
        """执行钩子,处理导入的条目.

        参数:
            imported: 导入的条目列表
            existing: 现有的 Beancount 指令

        返回:
            处理后的导入条目列表
        """
        return asyncio.run(self._transform(imported, existing))

    async def _transform(
        self, imported: list[Imported], existing: Directives
    ) -> list[Imported]:
        """异步转换导入的条目.

        参数:
            imported: 导入的条目列表
            existing: 现有的 Beancount 指令

        返回:
            处理后的导入条目列表
        """
        measurement_embedding = await self.__encoder.encode("for test")

        index = _HistoryIndex(
            encoder=self.__encoder,
            ndim=len(measurement_embedding),
        )

        for directive in tqdm(
            existing,
            desc="索引现有指令",
            leave=False,
        ):
            await index.add(directive)

        predictor = _AccountPredictor(
            chat_bot=self.__chat_bot,
            index=index,
            extra_system_prompt=self.__extra_system_prompt,
        )

        result: list[Imported] = []
        for filename, directives, account, importer in tqdm(
            imported,
            desc="预测导入文件中的交易",
            leave=False,
        ):
            processed = await self._process_one_file(directives, predictor)
            result.append((filename, processed, account, importer))
        return result

    async def _process_one_file(
        self, directives: Directives, predictor: _AccountPredictor
    ) -> Directives:
        """处理单个文件中的所有指令.

        参数:
            directives: 文件中的指令列表
            predictor: 会计科目预测器

        返回:
            处理后的指令列表
        """
        tasks = [
            self._process_with_index(index, directive, predictor)
            for index, directive in enumerate(directives)
        ]

        results_with_index: list[tuple[int, Directive]] = []
        for future in tqdm(
            asyncio.as_completed(tasks),
            total=len(tasks),
            desc="预测当前文件中的导入指令",
            leave=False,
        ):
            index, processed_directive = await future
            results_with_index.append((index, processed_directive))

        results_with_index.sort(key=lambda x: x[0])
        return [x[1] for x in results_with_index]

    async def _process_with_index(
        self, index: int, directive: Directive, predictor: _AccountPredictor
    ) -> tuple[int, Directive]:
        """处理单个指令并保留原始索引.

        参数:
            index: 指令在列表中的索引
            directive: Beancount 指令
            predictor: 会计科目预测器

        返回:
            (原始索引, 处理后的指令) 元组
        """
        result = await self._process_directive(directive, predictor)
        return index, result

    async def _process_directive(
        self, directive: Directive, predictor: _AccountPredictor
    ) -> Directive:
        """处理单个 Beancount 指令.

        此方法处理单个 Beancount 指令,对于交易类型,
        会尝试预测缺失的会计科目并添加到交易中。

        处理逻辑:
            1. 如果不是交易指令,直接返回原指令
            2. 调用预测器获取预测的账户名
            3. 如果预测失败,返回原指令
            4. 费用类账户(Expenses开头)添加 '!' 前缀作为待定标记
            5. 收入类账户(Income开头)不添加 '!' 前缀
            6. 将预测的 posting 添加到交易中,不添加额外的 flag 标记

        参数:
            directive: Beancount 指令(可能是交易或其他类型)
            predictor: 会计科目预测器实例

        返回:
            处理后的指令,如果是交易且预测成功,则包含预测的记账分录

        注意:
            - '!' 前缀表示待定科目,需要人工确认
            - 不会修改原有的 postings,只在末尾添加新的 posting
        """
        if not isinstance(directive, Transaction):
            return directive

        predicted_account = await predictor.predict(directive)
        if predicted_account is None:
            return directive

        # 格式化账户名:费用类添加 '!' 前缀作为待定标记
        account = predicted_account
        if account.startswith("Expenses") and not account.startswith("!"):
            account = f"! {account}"
        # 收入类账户保持原样

        # 不添加任何 flag,避免输出 '*' 或 '!' 标记
        # 因为 '!' 已经作为账户名的前缀存在
        return directive._replace(
            postings=[
                *directive.postings,
                Posting(account, None, None, None, None, None),
            ]
        )


# Public aliases for internal classes
Encoder = _Encoder
TransactionIndex = _TransactionIndex
HistoryIndex = _HistoryIndex
AccountPredictor = _AccountPredictor
ChatBot = _ChatBot
