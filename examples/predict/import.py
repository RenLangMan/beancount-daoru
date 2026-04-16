import os
import sys

# Windows 编码兼容: 确保 Python 以 UTF-8 模式运行,
# 避免 ¥ 等特殊字符在 GBK 控制台/文件上导致 UnicodeEncodeError。
# PYTHONUTF8 必须在解释器启动时设置才对 click.File 等生效,
# 因此如果未设置则自动重启自身。
if sys.platform == "win32" and not os.environ.get("PYTHONUTF8"):
    os.environ["PYTHONUTF8"] = "1"
    os.execv(sys.executable, [sys.executable, *sys.argv])  # noqa: S606

# 自动切换到脚本所在目录, 使 downloads/ 等相对路径正确解析
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

from textwrap import dedent  # noqa: E402

import beangulp  # noqa: E402

from beancount_daoru import (  # noqa: E402
    AlipayImporter,
    PathToName,
    PredictMissingPosting,
)

CONFIG = [
    AlipayImporter(
        account_mapping={
            "1234567890": {
                None: "Assets:Payment:Alipay",
                "余额宝": "Assets:Payment:Alipay:YuEBao",
                "余额宝收益": "Income:Investment:Fund:YuEBao",
            },
        },
        currency_mapping={
            None: "CNY",
        },
    ),
]

HOOKS = [
    PredictMissingPosting(
        chat_model_settings={
            "name": "Qwen3-4B-Instruct-2507",
            "base_url": "http://127.0.0.1:9527/v1",
            "api_key": "api-key-not-set",
            "temperature": 0,  # for test
        },
        embed_model_settings={
            "name": "embeddinggemma-300m",
            "base_url": "http://127.0.0.1:1314/v1",
            "api_key": "api-key-not-set",
        },
        extra_system_prompt=(
            dedent(
                """
                特殊规则:
                - 退款 (包括退货) 必须作为负支出处理,切勿将退款分类为收入
                - 对于难以用现有标签分类的账户,视为信息不足
                """
            ).strip()
        ),
    ),
    PathToName(),
]


if __name__ == "__main__":
    ingest = beangulp.Ingest(CONFIG, HOOKS)
    ingest()
