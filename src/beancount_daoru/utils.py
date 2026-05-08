"""beancount_daoru 包的实用工具函数.

此模块包含在 beancount_daoru 包的不同部分中使用的各种实用工具函数,
用于执行常见的操作。
"""

import itertools
import re
import zipfile
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# 统一时区东八区,用于统一时间戳生成
TZ_UTC8 = timezone(timedelta(hours=8))


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


def parse_datetime_flexible(date_str: str) -> datetime | None:
    """灵活解析日期时间字符串.

    支持多种日期格式:
    - "2023-01-01 12:00:00" (完整格式)
    - "01/01 12:00:00" (无年份, 使用当前年份)
    - "2023-01-01" (仅日期)

    参数:
        date_str: 日期时间字符串

    返回:
        解析后的 datetime 对象, 解析失败返回 None
    """
    if not date_str:
        return None

    # 尝试完整格式
    formats = [
        "%Y-%m-%d %H:%M:%S",  # 2023-01-01 12:00:00
        "%Y-%m-%d",  # 2023-01-01
        "%Y/%m/%d %H:%M:%S",  # 2023/01/01 12:00:00
        "%Y/%m/%d",  # 2023/01/01
        "%m/%d %H:%M:%S",  # 01/01 12:00:00
        "%m/%d",  # 01/01
    ]

    # datetime.strptime 解析不含年份的格式时使用 1900 作为默认值
    default_year = 1900
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)  # noqa: DTZ007
            if "%m/%d" in fmt and dt.year == default_year:
                dt = dt.replace(year=datetime.now().year)  # noqa: DTZ005
            return dt.replace(tzinfo=TZ_UTC8)
        except ValueError:  # noqa: PERF203
            continue

    return None


def parse_date_flexible(date_str: str) -> date | None:
    """灵活解析日期字符串.

    参数:
        date_str: 日期字符串

    返回:
        解析后的 date 对象, 解析失败返回 None
    """
    dt = parse_datetime_flexible(date_str)
    return dt.date() if dt else None


def extract_zip_file(
    zip_path: str | Path,
    extract_dir: str | Path,
    password: str | None = None,
) -> list[Path]:
    """解压 ZIP 文件.

    参数:
        zip_path: ZIP 文件路径
        extract_dir: 解压目标目录
        password: 解压密码(可选)

    返回:
        解压后的文件路径列表

    异常:
        FileNotFoundError: ZIP 文件不存在
        zipfile.BadZipFile: 文件不是有效的 ZIP 格式
    """
    zip_path = Path(zip_path)
    extract_dir = Path(extract_dir)

    if not zip_path.exists():
        msg = f"ZIP 文件不存在: {zip_path}"
        raise FileNotFoundError(msg)

    if not zipfile.is_zipfile(zip_path):
        msg = f"文件不是有效的 ZIP 格式: {zip_path}"
        raise zipfile.BadZipFile(msg)

    extract_dir.mkdir(parents=True, exist_ok=True)

    extracted_files: list[Path] = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # 跳过目录
            if member.endswith("/"):
                continue

            try:
                # 处理加密文件
                if password:
                    zf.extract(member, extract_dir, pwd=password.encode())
                else:
                    zf.extract(member, extract_dir)

                extracted_files.append(extract_dir / member)
            except RuntimeError:
                # 可能需要密码
                if password:
                    raise
                continue

    return extracted_files
