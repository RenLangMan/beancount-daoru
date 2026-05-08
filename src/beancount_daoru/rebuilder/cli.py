"""命令行接口."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from beancount_daoru.rebuilder.core import LedgerRebuilder


def parse_date(date_str: str | None) -> date | None:
    """解析日期字符串."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")  # noqa: DTZ007
        return dt.date()
    except ValueError as e:
        msg = f"无效日期格式: {date_str}, 请使用 YYYY-MM-DD"
        raise argparse.ArgumentTypeError(msg) from e


def main(argv: list[str] | None = None) -> int:
    """主入口."""
    parser = argparse.ArgumentParser(
        prog="beancount-rebuild",
        description="Beancount 账本重构工具 - 按日期分组并排序",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 重构整个账本
  beancount-rebuild main.beancount ./output

  # 只重构2024年的交易
  beancount-rebuild main.beancount ./output --start 2024-01-01 --end 2024-12-31

  # 不去重 Balance
  beancount-rebuild main.beancount ./output --no-dedup
        """,
    )

    parser.add_argument(
        "source",
        help="源 beancount 文件路径",
    )
    parser.add_argument(
        "output",
        help="输出目录路径",
    )
    parser.add_argument(
        "--start",
        "-s",
        type=parse_date,
        help="开始日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        "-e",
        type=parse_date,
        help="结束日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_false",
        dest="dedup",
        help="关闭 Balance 去重",
    )
    parser.add_argument(
        "--by-source",
        action="store_true",
        help="按源文件分组输出",
    )

    args = parser.parse_args(argv)

    try:
        rebuilder = LedgerRebuilder(
            source_file=args.source,
            output_dir=args.output,
            start_date=args.start,
            end_date=args.end,
            deduplicate_balance=args.dedup,
            group_by_source=args.by_source,
        )
        rebuilder.rebuild().print_stats()
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"❌ 错误: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
