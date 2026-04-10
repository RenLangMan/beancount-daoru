"""将文件路径转换为文件名的钩子。

此模块提供了一个钩子实现，用于将文件路径仅转换为文件名，
丢弃目录信息。
"""

from pathlib import Path

from beancount import Directives
from typing_extensions import override

from beancount_daoru.hook import Hook as BaseHook
from beancount_daoru.hook import Imported


class Hook(BaseHook):
    """将文件路径转换为文件名的钩子。

    此钩子将导入条目中的文件路径转换为仅包含文件名部分，
    移除所有目录路径信息。

    示例：
        原始导入条目中的文件路径：'/path/to/file.bean'
        转换后：'file.bean'

    这有助于：
        - 隐藏敏感的目录结构信息
        - 简化输出中的文件引用
        - 保持输出整洁，仅显示有意义的文件名
    """

    @override
    def __call__(
        self, imported: list[Imported], existing: Directives
    ) -> list[Imported]:
        """处理导入的条目，将文件路径转换为文件名。

        参数：
            imported: 导入的条目列表，每个元素为 (文件路径, 指令列表, 账户名, 导入器)
            existing: 现有的 Beancount 指令（本钩子中未使用）

        返回：
            转换后的导入条目列表，其中文件路径已被替换为文件名
        """
        return [
            (Path(filename).name, directives, account, importer)
            for filename, directives, account, importer in imported
        ]
