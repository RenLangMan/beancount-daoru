"""beancount_daoru 包的实用工具函数.

此模块包含在 beancount_daoru 包的不同部分中使用的各种实用工具函数,
用于执行常见的操作。
"""

import itertools
import re
from collections.abc import Iterator


def search_patterns(
    texts: Iterator[str], *patterns: re.Pattern[str]
) -> tuple[Iterator[re.Match[str]], ...]:
    """在文本迭代器中搜索多个正则表达式模式.

    此函数通过为每个模式创建文本迭代器的独立副本,高效地在文本字符串迭代器中
    搜索多个正则表达式模式,避免多次遍历迭代器。

    参数:
        texts: 要搜索的文本字符串迭代器。
        *patterns: 要搜索的多个编译后的正则表达式模式。

    返回:
        迭代器的元组,每个迭代器包含对应模式的匹配结果。
        迭代器的顺序与提供的模式顺序一致。
    """

    def _find_all(
        text_iter: Iterator[str], pattern: re.Pattern[str]
    ) -> Iterator[re.Match[str]]:
        """在文本迭代器中查找所有匹配项.

        参数:
            text_iter: 文本字符串迭代器
            pattern: 编译后的正则表达式模式

        返回:
            所有匹配结果的迭代器
        """
        for text in text_iter:
            yield from pattern.finditer(text)

    text_iters = itertools.tee(texts, len(patterns))
    return tuple(
        _find_all(text_iter, pattern)
        for text_iter, pattern in zip(text_iters, patterns, strict=False)
    )
