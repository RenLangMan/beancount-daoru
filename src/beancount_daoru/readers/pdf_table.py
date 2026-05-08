"""PDF 表格读取器实现.

此模块提供了使用 pdfplumber 从 PDF 文件中读取表格数据的功能,
能够处理中国金融文档中复杂的布局和文本提取需求。
"""

from collections.abc import Iterator
from pathlib import Path

import pdfplumber
from typing_extensions import override

from beancount_daoru.reader import Reader as BaseReader

BBox = tuple[int | float, int | float, int | float, int | float]


class Reader(BaseReader):
    """用于包含表格数据的 PDF 文件读取器.

    使用 pdfplumber 从 PDF 文档中提取表格,通过指定边界框
    将交易表格与其他内容分离。
    """

    def __init__(
        self,
        /,
        table_bbox: BBox,
    ) -> None:
        """初始化 PDF 表格读取器.

        参数:
            table_bbox: 定义表格区域的边界框 (x0, y0, x1, y1)
        """
        self.__table_bbox = table_bbox

    @override
    def read_captions(self, file: Path) -> Iterator[str]:
        """读取 PDF 中的标题/元数据文本.

        参数:
            file: 要读取的 PDF 文件路径

        返回:
            每页中表格区域外的文本内容迭代器
        """
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                yield page.outside_bbox(self.__table_bbox).extract_text_simple()

    @override
    def read_records(self, file: Path) -> Iterator[dict[str, str]]:
        """读取 PDF 中的表格数据记录.

        参数:
            file: 要读取的 PDF 文件路径

        返回:
            数据记录字典的迭代器,每个字典的键为列名,值为对应的单元格内容
        """
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                table = page.within_bbox(self.__table_bbox).extract_table()
                if table:
                    header = [value or "" for value in table[0]]
                    for row in table[1:]:
                        yield {
                            field: (value or "").strip()
                            for field, value in zip(header, row, strict=True)
                        }
