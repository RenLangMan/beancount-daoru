"""中国金融机构的 Beancount 导入器。

此包为各种中国金融机构和支付平台提供导入器，
让用户能够轻松地将他们的财务记录转换为 Beancount 格式用于会计目的。
"""

from beancount_daoru.hooks.path_to_name import Hook as PathToName
from beancount_daoru.hooks.reorder_by_importer_name import Hook as ReorderByImporterName
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
