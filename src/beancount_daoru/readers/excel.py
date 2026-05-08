"""Excel 文档读取器实现.

此模块提供了使用 pyexcel 读取 Excel 和 CSV 文件的功能,
能够处理中国金融平台常用的各种编码和格式。
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import chardet
import pyexcel
from typing_extensions import override

from beancount_daoru.reader import Reader as BaseReader


class Reader(BaseReader):
    """Excel 和 CSV 文件读取器.

    使用 pyexcel 读取各种电子表格格式,能够处理中国金融文档中
    常见的编码和格式变化。支持自动检测编码。
    """

    def __init__(
        self,
        /,
        header: int,
        encoding: str | None = None,
    ) -> None:
        """初始化 Excel 读取器.

        参数:
            header: 数据开始前需要跳过的表头行数
            encoding: 文件编码,None 表示自动检测编码(仅对 CSV 有效)
        """
        self.__header = header
        self.__encoding = encoding

    def _is_csv(self, file: Path) -> bool:
        """判断是否为 CSV 文件."""
        return file.suffix.lower() == ".csv"

    def _get_encoding(self, file: Path) -> str | None:
        """获取文件编码.

        参数:
            file: 文件路径

        返回:
            CSV 文件返回检测到的编码,Excel 文件返回 None
        """
        if not self._is_csv(file):
            return None
        if self.__encoding is not None:
            return self.__encoding
        detected = chardet.detect(file.read_bytes())
        return detected.get("encoding") or "utf-8"

    def _get_pyexcel_kwargs(self, file: Path) -> dict[str, Any]:
        """获取传递给 pyexcel 的参数.

        参数:
            file: 文件路径

        返回:
            根据文件类型构造的参数字典
        """
        kwargs: dict[str, Any] = {}
        encoding = self._get_encoding(file)
        if encoding:
            kwargs["encoding"] = encoding
        return kwargs

    @override
    def read_captions(self, file: Path) -> Iterator[str]:
        """读取文件中的标题/元数据行.

        参数:
            file: 要读取的文件路径

        返回:
            标题行中所有单元格值的字符串迭代器
        """
        kwargs = self._get_pyexcel_kwargs(file)
        for row in pyexcel.get_array(  # pyright: ignore[reportUnknownVariableType]
            file_name=file,
            row_limit=self.__header,
            auto_detect_int=False,
            auto_detect_float=False,
            auto_detect_datetime=False,
            skip_empty_rows=True,
            **kwargs,
        ):
            yield from row

    @override
    def read_records(self, file: Path) -> Iterator[dict[str, str]]:
        """读取文件中的数据记录.

        参数:
            file: 要读取的文件路径

        返回:
            数据记录字典的迭代器,每个字典的键为列名,值为对应的单元格内容
        """
        kwargs = self._get_pyexcel_kwargs(file)
        for row in pyexcel.iget_records(  # pyright: ignore[reportUnknownVariableType]
            file_name=file,
            start_row=self.__header,
            auto_detect_int=False,
            auto_detect_float=False,
            auto_detect_datetime=False,
            skip_empty_rows=True,
            **kwargs,
        ):
            yield {
                self.__convert(key): self.__convert(value)  # pyright: ignore[reportUnknownArgumentType]
                for key, value in row.items()  # pyright: ignore[reportUnknownVariableType]
            }

    def __convert(self, value: object) -> str:
        """将任意值转换为字符串.

        参数:
            value: 待转换的值

        返回:
            转换后的字符串,若值为 None 则返回空字符串
        """
        return "" if value is None else str(value).strip()
