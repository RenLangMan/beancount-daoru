"""中国金融机构的 Beancount 导入器.

此包为各种中国金融机构和支付平台提供导入器,
让用户能够轻松地将他们的财务记录转换为 Beancount 格式用于会计目的。
"""

# Windows 编码兼容: 尝试启用 UTF-8 模式。
# 注意: PYTHONUTF8 需要在解释器启动时设置才对 click.File 等生效,
# 这里设置主要确保后续的 open() 调用使用 UTF-8。
# 对于直接运行的脚本入口, 建议在脚本开头使用 os.execv 重启。
import os
import sys

if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    import io

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace"
        )

from beancount_daoru.hooks.path_to_name import Hook as PathToName
from beancount_daoru.hooks.reorder_by_importer_name import Hook as ReorderByImporterName
from beancount_daoru.hooks.sort_by_timestamp import SortByTimestamp
from beancount_daoru.importers.alipay import Importer as AlipayImporter
from beancount_daoru.importers.boc import Importer as BOCImporter
from beancount_daoru.importers.bocom import Importer as BOCOMImporter
from beancount_daoru.importers.jd import Importer as JDImporter
from beancount_daoru.importers.meituan import Importer as MeituanImporter
from beancount_daoru.importers.wechat import Importer as WechatImporter

__all__ = [
    "AlipayImporter",
    "BOCImporter",
    "BOCOMImporter",
    "JDImporter",
    "MeituanImporter",
    "PathToName",
    "ReorderByImporterName",
    "SortByTimestamp",
    "WechatImporter",
]

# 可选组件 - 仅在安装了依赖时可用
try:
    from beancount_daoru.hooks.predict_missing_posting import (
        Hook as PredictMissingPosting,
    )

    __all__ += ["PredictMissingPosting"]
except ImportError:
    pass
