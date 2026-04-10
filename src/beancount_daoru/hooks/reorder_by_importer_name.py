"""按导入器名称重排序条目的钩子。

此模块提供了一个钩子实现，用于按导入器名称的升序对导入的条目进行排序。
"""

from beancount import Directives
from typing_extensions import override

from beancount_daoru.hook import Hook as BaseHook
from beancount_daoru.hook import Imported


class Hook(BaseHook):
    """按导入器名称重排序条目的钩子。

    此钩子根据导入器的名称对导入的条目进行排序，
    使得来自不同导入器的条目能够保持一致的顺序。
    """

    @override
    def __call__(
        self, imported: list[Imported], existing: Directives
    ) -> list[Imported]:
        """按导入器名称排序导入的条目。

        参数：
            imported: 导入的条目列表，每个元素为 (文件路径, 指令列表, 账户名, 导入器)
            existing: 现有的 Beancount 指令（本钩子中未使用）

        返回：
            按导入器名称排序后的导入条目列表
        """
        return sorted(imported, key=lambda x: x[3].name)
