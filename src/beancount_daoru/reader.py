"""读取金融文档的基础模块.

此模块定义了基础 Reader 类,为读取各种文档格式(PDF、Excel 等)
并将其转换为可供提取器处理的结构化数据提供通用接口。
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol


class Reader(Protocol):
    """文档读取器的抽象基类.

    读取器负责将原始文档文件(PDF、Excel 等)解析为结构化的字典,
    这些字典可以被验证并转换为类型化的记录.
    """

    def read_captions(
        self,
        file: Path,
    ) -> Iterator[str]:
        """从文件中读取标题/页眉文本.

        参数:
            file: 要读取的文件路径。

        返回:
            标题文本字符串的迭代器。
        """
        ...

    def read_records(self, file: Path) -> Iterator[dict[str, str]]:
        """从文件中读取字典形式的记录.

        参数:
            file: 要读取的文件路径。

        返回:
            表示单条记录的字典迭代器。
        """
        ...
