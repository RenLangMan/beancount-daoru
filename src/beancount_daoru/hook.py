"""导入的 Beancount 条目后处理钩子系统.

此模块定义了钩子接口,允许对导入的条目进行后处理,
在最终输出前实现科目预测、路径标准化和其他转换功能。
"""

from typing import Protocol

from beancount import Account, Directives
from beangulp import Importer

Filename = str
Imported = tuple[Filename, Directives, Account, Importer]


class Hook(Protocol):
    """定义导入钩子接口的协议.

    钩子在初始导入之后、最终输出之前被调用,
    允许对导入的条目进行自定义处理。
    """

    def __call__(
        self, imported: list[Imported], existing: Directives
    ) -> list[Imported]:
        """处理导入的条目.

        参数:
            imported: 导入的条目列表
            existing: 现有的 Beancount 条目

        返回:
            处理后的导入条目列表
        """
        ...
