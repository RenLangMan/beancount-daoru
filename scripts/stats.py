#!/usr/bin/env python3
"""Beancount 导入管理脚本 - 整合所有导入相关操作.

子命令:
  stats        统计分析(账户/类型/完整性/收付款方式/映射)
  view         查看交易记录
  search       搜索特定账户的交易
  check        验证 Beancount 语法 (bean-check)
  report       生成报表 (bean-report)
  merge        合并到主账本
  archive      归档已导入的账单文件
  clean        清理空行

用法:
  python scripts/stats.py <子命令> [选项] [数据目录]

示例:
  python scripts/stats.py stats --all
  python scripts/stats.py stats --accounts --types
  python scripts/stats.py view --head 30
  python scripts/stats.py search --account ABC
  python scripts/stats.py check
  python scripts/stats.py report balances
  python scripts/stats.py merge --include
  python scripts/stats.py archive
  python scripts/stats.py clean
"""

import argparse
import csv
import io
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict, cast

if TYPE_CHECKING:
    from collections.abc import Callable


# ==================== 类型定义 ====================
class PostingDict(TypedDict):
    """Posting 数据结构."""

    account: str
    amount: float
    currency: str


class TransactionDict(TypedDict):
    """交易数据结构."""

    date: str
    flag: str
    payee: str
    narration: str
    postings: list[PostingDict]
    metadata: dict[str, str]
    line: int


class AccountStatsDict(TypedDict):
    """账户统计数据结构."""

    count: int
    total: float
    currency: str


class CategoryStatsDict(TypedDict):
    """类别统计数据结构."""

    count: int
    total: float


class MappingStatsDict(TypedDict):
    """映射统计数据结构."""

    count: int
    methods: set[str]


# Windows 兼容: 确保 stdout 支持 UTF-8
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ==================== 颜色定义 ====================
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
MAGENTA = "\033[0;35m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"


def print_title(title: str) -> None:
    """打印带边框的标题.

    Args:
        title: 标题文本
    """
    print(f"\n{MAGENTA}{'═' * 60}{NC}")
    print(f"{MAGENTA}  {title}{NC}")
    print(f"{MAGENTA}{'═' * 60}{NC}\n")


def print_section(title: str) -> None:
    """打印分隔段落标题.

    Args:
        title: 标题文本
    """
    print(f"\n{CYAN}{'─' * 50}{NC}")
    print(f"{CYAN}  {title}{NC}")
    print(f"{CYAN}{'─' * 50}{NC}")


def print_kv(key: str, value: str, indent: int = 2) -> None:
    """打印键值对.

    Args:
        key: 键名
        value: 值
        indent: 缩进空格数
    """
    print(f"{' ' * indent}{GREEN}{key}{NC}: {value}")


def print_warn(msg: str) -> None:
    """打印警告信息.

    Args:
        msg: 警告消息文本
    """
    print(f"{YELLOW}[WARN]{NC} {msg}")


def print_err(msg: str) -> None:
    """打印错误信息.

    Args:
        msg: 错误消息文本
    """
    print(f"{RED}[ERROR]{NC} {msg}")


def print_ok(msg: str) -> None:
    """打印成功信息.

    Args:
        msg: 成功消息文本
    """
    print(f"{GREEN}[OK]{NC} {msg}")


# ==================== 常量定义 ====================
BALANCE_THRESHOLD = 0.005  # 交易平衡阈值
MIN_POSTING_COUNT = 2  # 多 posting 交易阈值
MAX_METHODS_DISPLAY = 5  # 映射统计显示方法数量上限
DATE_RANGE_PARTS = 2  # 日期范围分割份数

# Beancount 命令定义 (用于 subprocess)
_BEAN_CHECK_CMD = "bean-check"
_BEAN_REPORT_CMD = "bean-report"

# ==================== 预编译正则表达式 ====================
_TXN_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\*)\s+\"(.+?)\"\s+\"(.+?)\"")
_META_PATTERN = re.compile(r"^\s+(\w+):\s+\"(.+?)\"")
_POSTING_PATTERN = re.compile(
    r"^\s+((?:Assets|Liabilities|Expenses|Income|Equity):\S+)"
    + r"\s+(-?[\d,]+\.\d+)\s+(\w+)"
)

# ==================== 通用工具 ====================
_ENCODING_ORDER = ["utf-8", "gbk", "utf-8-sig", "latin-1"]
_ALIPAY_ENCODING_ORDER = ["gbk", "utf-8-sig", "utf-8"]


def _try_read_with_encoding(path: Path, enc: str) -> list[str] | None:
    """尝试用指定编码读取文件.

    Args:
        path: 文件路径
        enc: 编码名称

    Returns:
        文件内容列表或 None
    """
    try:
        return path.read_text(encoding=enc).splitlines(keepends=True)
    except (UnicodeDecodeError, UnicodeError):
        return None


def read_file_auto(path: Path) -> tuple[list[str], str] | tuple[None, None]:
    """自动检测编码读取文件内容.

    Args:
        path: 文件路径

    Returns:
        (文件内容列表, 编码) 或 (None, None)
    """
    for enc in _ENCODING_ORDER:
        content = _try_read_with_encoding(path, enc)
        if content is not None:
            return content, enc
    return None, None


def resolve_paths(data_dir: str) -> tuple[Path, Path, Path, Path, Path]:
    """解析并验证数据目录路径.

    Args:
        data_dir: 数据目录路径

    Returns:
        (基础目录, 导入文件, 主账本, 下载目录, 配置文件)
    """
    base = Path(data_dir).resolve()
    bean_file = base / "imported_transactions.bean"
    main_bean = base / "main.bean"
    downloads_dir = base / "downloads"
    config_file = base / "fava_import_config.py"

    if not base.exists():
        print_err(f"数据目录不存在: {base}")
        sys.exit(1)

    return base, bean_file, main_bean, downloads_dir, config_file


def find_alipay_csv(downloads_dir: Path) -> Path | None:
    """查找支付宝 CSV 文件.

    Args:
        downloads_dir: 下载目录路径

    Returns:
        支付宝 CSV 文件路径, 不存在则返回 None
    """
    if not downloads_dir.exists():
        return None
    for f in sorted(downloads_dir.iterdir()):
        if f.is_file() and "支付宝" in f.name and f.suffix == ".csv":
            return f
    return None


def find_all_csv(downloads_dir: Path) -> list[Path]:
    """查找所有 CSV 文件.

    Args:
        downloads_dir: 下载目录路径

    Returns:
        CSV 文件路径列表
    """
    if not downloads_dir.exists():
        return []
    return sorted(
        f for f in downloads_dir.iterdir() if f.is_file() and f.suffix == ".csv"
    )


def _read_csv_with_encoding(
    csv_file: Path, encoding: str, skip_lines: int
) -> list[dict[str, str]] | None:
    """尝试用指定编码读取 CSV 文件.

    Args:
        csv_file: CSV 文件路径
        encoding: 编码名称
        skip_lines: 跳过的行数

    Returns:
        行列表或 None
    """
    try:
        with csv_file.open(encoding=encoding) as f:
            for _i in range(skip_lines):
                _ = f.readline()
            reader = csv.DictReader(f)
            return list(reader)
    except (UnicodeDecodeError, UnicodeError):
        return None


def read_alipay_csv(
    csv_file: Path,
    skip_lines: int = 24,
) -> tuple[list[dict[str, str]], str] | tuple[None, None]:
    """读取支付宝 CSV 文件.

    Args:
        csv_file: CSV 文件路径
        skip_lines: 跳过的行数(默认24)

    Returns:
        (行列表, 编码) 或 (None, None)
    """
    for encoding in _ALIPAY_ENCODING_ORDER:
        rows = _read_csv_with_encoding(csv_file, encoding, skip_lines)
        if rows is not None:
            return rows, encoding
    return None, None


# ==================== 解析 Beancount 文件 ====================
def _parse_bean_line(
    line: str,
    txn_pattern: re.Pattern[str],
    meta_pattern: re.Pattern[str],
    posting_pattern: re.Pattern[str],
    current_txn: TransactionDict | None,
) -> tuple[TransactionDict | None, TransactionDict | None]:
    """解析单行 Beancount 内容.

    Args:
        line: 行内容
        txn_pattern: 交易正则
        meta_pattern: 元数据正则
        posting_pattern: posting 正则
        current_txn: 当前交易

    Returns:
        (新交易或None, 当前交易或None)
    """
    new_txn: TransactionDict | None = None
    completed: TransactionDict | None = None

    m = txn_pattern.match(line)
    if m:
        if current_txn:
            completed = current_txn
        else:
            new_txn = {
                "date": m.group(1),
                "flag": m.group(2),
                "payee": m.group(3),
                "narration": m.group(4),
                "postings": [],
                "metadata": {},
                "line": 0,
            }
    elif current_txn is not None:
        if (
            not _try_parse_metadata(line, meta_pattern, current_txn)
            and not _try_parse_posting(line, posting_pattern, current_txn)
            and not (line.strip() == "" and current_txn["postings"])
        ):
            completed = None  # 继续当前交易
        else:
            completed = current_txn if current_txn["postings"] else None

    return new_txn, completed


def _try_parse_metadata(
    line: str, pattern: re.Pattern[str], txn: TransactionDict
) -> bool:
    """尝试解析元数据行.

    Args:
        line: 行内容
        pattern: 正则模式
        txn: 交易字典

    Returns:
        是否成功解析
    """
    m = pattern.match(line)
    if m:
        txn["metadata"][m.group(1)] = m.group(2)
        return True
    return False


def _try_parse_posting(
    line: str, pattern: re.Pattern[str], txn: TransactionDict
) -> bool:
    """尝试解析 posting 行.

    Args:
        line: 行内容
        pattern: 正则模式
        txn: 交易字典

    Returns:
        是否成功解析
    """
    m = pattern.match(line)
    if m:
        posting: PostingDict = {
            "account": m.group(1),
            "amount": float(m.group(2).replace(",", "")),
            "currency": m.group(3),
        }
        txn["postings"].append(posting)
        return True
    return False


def parse_bean_file(bean_file: Path) -> list[TransactionDict]:
    """解析 beancount 文件,提取交易和元数据.

    Args:
        bean_file: Beancount 文件路径

    Returns:
        交易字典列表
    """
    transactions: list[TransactionDict] = []
    current_txn: TransactionDict | None = None

    if not bean_file.exists():
        print_err(f"文件不存在: {bean_file}")
        return transactions

    content, _ = read_file_auto(bean_file)
    if content is None:
        print_err(f"无法读取文件: {bean_file}")
        return transactions

    for raw_line in content:
        line = raw_line.rstrip("\n")
        new_txn, completed = _parse_bean_line(
            line, _TXN_PATTERN, _META_PATTERN, _POSTING_PATTERN, current_txn
        )

        if completed:
            transactions.append(completed)
            if new_txn:
                new_txn["line"] = len(transactions)
                current_txn = new_txn
            else:
                current_txn = None
        elif new_txn:
            new_txn["line"] = len(transactions) + 1
            current_txn = new_txn

    if current_txn and current_txn["postings"]:
        transactions.append(current_txn)

    return transactions


def format_txn(
    txn: TransactionDict,
    *,
    show_metadata: bool = True,
) -> str:
    """格式化打印一条交易.

    Args:
        txn: 交易字典
        show_metadata: 是否显示元数据

    Returns:
        格式化后的交易字符串
    """
    lines: list[str] = []
    lines.append(f'{txn["date"]} {txn["flag"]} "{txn["payee"]}" "{txn["narration"]}"')
    if show_metadata:
        for k, v in txn["metadata"].items():
            lines.append(f'  {k}: "{v}"')
    for p in txn["postings"]:
        sign = "+" if p["amount"] >= 0 else ""
        lines.append(f"  {p['account']}  {sign}{p['amount']:.2f} {p['currency']}")
    return "\n".join(lines)


# ==================== 子命令: stats ====================
def cmd_stats(args: argparse.Namespace) -> None:
    """统计分析.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    base, bean_file, _, downloads_dir, _config_file = resolve_paths(data_dir)
    transactions = parse_bean_file(bean_file)

    accounts: bool = cast("bool", args.accounts)
    payment: bool = cast("bool", args.payment)
    types: bool = cast("bool", args.types)
    integrity: bool = cast("bool", args.integrity)
    mapping: bool = cast("bool", args.mapping)
    specific = accounts or payment or types or integrity or mapping
    run_all = not specific

    print(f"\n{BOLD}Beancount 导入统计{NC}")
    print(f"  数据目录: {base}")
    print(f"  交易文件: {bean_file.name} {'✓' if bean_file.exists() else '✗'}")
    if transactions:
        print(f"  交易数量: {len(transactions)}")

    if run_all or accounts:
        _stats_accounts(transactions)
    if run_all or types:
        _stats_types(transactions)
    if run_all or integrity:
        _stats_integrity(transactions, bean_file)
    if run_all or payment:
        _stats_payment(downloads_dir)
    if run_all or mapping:
        _stats_mapping(downloads_dir)


def _stats_accounts(transactions: list[TransactionDict]) -> None:
    """统计各账户交易次数和金额.

    Args:
        transactions: 交易列表
    """
    print_title("账户交易统计")

    account_stats: dict[str, AccountStatsDict] = {}
    for txn in transactions:
        for posting in txn["postings"]:
            acc = posting["account"]
            if acc not in account_stats:
                account_stats[acc] = {"count": 0, "total": 0.0, "currency": "CNY"}
            account_stats[acc]["count"] += 1
            account_stats[acc]["total"] += posting["amount"]
            account_stats[acc]["currency"] = posting["currency"]

    sorted_stats = sorted(
        account_stats.items(), key=lambda x: x[1]["count"], reverse=True
    )

    print(f"  {'次数':>6}  {'金额':>14}  {'账户'}")
    print(f"  {'─' * 6}  {'─' * 14}  {'─' * 40}")
    for acc, data in sorted_stats:
        sign = "+" if data["total"] >= 0 else ""
        print(f"  {data['count']:>6}  {sign}{data['total']:>13.2f}  {acc}")

    total_count = sum(d["count"] for d in account_stats.values())
    total_amount = sum(d["total"] for d in account_stats.values())
    print(f"\n  {'合计':>6}  {total_amount:>14.2f}  ({total_count} 条 posting)")

    print_section("按账户类别汇总")
    category_stats: dict[str, CategoryStatsDict] = {}
    for acc, data in account_stats.items():
        cat = acc.split(":")[0]
        if cat not in category_stats:
            category_stats[cat] = {"count": 0, "total": 0.0}
        category_stats[cat]["count"] += data["count"]
        category_stats[cat]["total"] += data["total"]

    for cat in ["Assets", "Liabilities", "Expenses", "Income", "Equity"]:
        if cat in category_stats:
            d = category_stats[cat]
            sign = "+" if d["total"] >= 0 else ""
            print_kv(cat, f"{d['count']}次, {sign}{d['total']:.2f} CNY")


def _stats_types(transactions: list[TransactionDict]) -> None:
    """统计交易类型和状态.

    Args:
        transactions: 交易列表
    """
    print_title("交易类型与状态统计")

    type_counter: Counter[str] = Counter()
    for txn in transactions:
        t = txn["metadata"].get("type", "未知")
        type_counter[t] += 1

    print_section("交易类型 (type)")
    for t, count in type_counter.most_common():
        print_kv(t, f"{count}次")

    status_counter: Counter[str] = Counter()
    for txn in transactions:
        s = txn["metadata"].get("status", "未知")
        status_counter[s] += 1

    print_section("交易状态 (status)")
    for s, count in status_counter.most_common():
        print_kv(s, f"{count}次")

    dc_counter: Counter[str] = Counter()
    for txn in transactions:
        dc = txn["metadata"].get("dc", "未知")
        dc_counter[dc] += 1

    print_section("收支方向 (dc)")
    for dc, count in dc_counter.most_common():
        print_kv(dc, f"{count}次")


def _stats_integrity(transactions: list[TransactionDict], bean_file: Path) -> None:
    """检查交易完整性.

    Args:
        transactions: 交易列表
        bean_file: Beancount 文件路径
    """
    print_title("交易完整性检查")

    total = len(transactions)
    print_kv("总交易数", str(total))

    single_posting = [txn for txn in transactions if len(txn["postings"]) == 1]
    print_kv(
        "单 posting 交易",
        f"{len(single_posting)}条"
        + (f" {YELLOW}(可能缺少对冲账户){NC}" if single_posting else ""),
    )

    no_posting = [txn for txn in transactions if len(txn["postings"]) == 0]
    print_kv(
        "无 posting 交易",
        f"{len(no_posting)}条" + (f" {RED}(异常！){NC}" if no_posting else ""),
    )

    multi_posting = [
        txn for txn in transactions if len(txn["postings"]) > MIN_POSTING_COUNT
    ]
    print_kv(f"多 posting 交易(>{MIN_POSTING_COUNT})", f"{len(multi_posting)}条")

    unbalanced: list[tuple[TransactionDict, float]] = []
    for txn in transactions:
        if txn["postings"]:
            total_amount = sum(p["amount"] for p in txn["postings"])
            if abs(total_amount) > BALANCE_THRESHOLD:
                unbalanced.append((txn, total_amount))

    print_kv(
        "不平衡交易",
        f"{len(unbalanced)}条"
        + (f" {RED}(需要关注！){NC}" if unbalanced else f" {GREEN}✓ 全部平衡{NC}"),
    )

    if unbalanced:
        print_section("不平衡交易详情(前10条)")
        for txn, diff in unbalanced[:10]:
            print(f'  {txn["date"]} "{txn["payee"]}" - 差额: {diff:.2f}')

    if bean_file.exists():
        content, _ = read_file_auto(bean_file)
        if content:
            print_kv("文件总行数", str(len(content)))

    if transactions:
        dates = [txn["date"] for txn in transactions]
        print_kv("日期范围", f"{min(dates)} ~ {max(dates)}")


def _stats_payment(downloads_dir: Path) -> None:
    """统计原始收付款方式汇总."""
    csv_file = find_alipay_csv(downloads_dir)
    if not csv_file:
        print_title("收付款方式统计(原始账单)")
        print_warn("未找到支付宝 CSV 文件,跳过此统计")
        return

    print_title("收付款方式统计(原始账单)")

    rows, _enc = read_alipay_csv(csv_file)
    if rows is None:
        print_err("无法读取 CSV 文件")
        return

    payment_methods: Counter[str] = Counter()
    payment_methods_clean: Counter[str] = Counter()

    for row in rows:
        method = row.get("收/付款方式", "")
        if method:
            payment_methods[method] += 1
            clean = method.split("&")[0].strip()
            payment_methods_clean[clean] += 1

    print_section("原始收付款方式(含优惠变体)")
    for method, count in payment_methods.most_common():
        print(f"  {count:>4}次: {method}")

    print_section("清理后收付款方式(去掉优惠后缀)")
    for method, count in payment_methods_clean.most_common():
        print(f"  {count:>4}次: {method}")


def _map_payment_method(clean: str) -> str | None:
    """映射支付方式到账户.

    Args:
        clean: 清理后的支付方式

    Returns:
        账户路径或None
    """
    mapping = {
        "网商银行储蓄卡(7521)": "Assets:Flow:Bank:Hubby:WSBank:No7521",
        "农业银行储蓄卡(6773)": "Assets:Flow:Bank:Hubby:ABC:No6773",
        "武汉农商行储蓄卡(9026)": "Assets:Flow:Bank:Hubby:WHRC:No9026",
        "工商银行储蓄卡(5566)": "Assets:Flow:Bank:Hubby:ICBC:No5566",
        "账户余额": "Assets:Flow:EBank:Alipay:老公支付宝余额",
        "花呗": "Liabilities:Life:Alipay:Huabei:老公花呗",
        "花呗分期(3期)": "Liabilities:Life:Alipay:Huabei:老公花呗",
    }

    for key, acc in mapping.items():
        if clean == key or clean.startswith(key):
            return acc
    return None


def _stats_mapping(downloads_dir: Path) -> None:  # noqa: C901, PLR0912
    """对比原始支付方式和映射账户."""
    csv_file = find_alipay_csv(downloads_dir)
    if not csv_file:
        print_title("支付方式 → Beancount 账户映射")
        print_warn("未找到支付宝 CSV 文件,跳过此统计")
        return

    print_title("支付方式 → Beancount 账户映射")

    rows, _enc = read_alipay_csv(csv_file)
    if rows is None:
        print_err("无法读取 CSV 文件")
        return

    stats: dict[str, MappingStatsDict] = {}

    for row in rows:
        method = row.get("收/付款方式", "")
        if not method:
            continue

        clean = method.split("&")[0].strip()
        account = _map_payment_method(clean)

        if account:
            if account not in stats:
                stats[account] = {"count": 0, "methods": set()}
            stats[account]["count"] += 1
            stats[account]["methods"].add(method)
        else:
            if "⚠ 未映射" not in stats:
                stats["⚠ 未映射"] = {"count": 0, "methods": set()}
            stats["⚠ 未映射"]["count"] += 1
            stats["⚠ 未映射"]["methods"].add(method)

    for account, data in sorted(
        stats.items(), key=lambda x: x[1]["count"], reverse=True
    ):
        print(f"\n  {BOLD}{account}{NC}: {data['count']}次")
        methods = sorted(data["methods"])
        if len(methods) <= MAX_METHODS_DISPLAY:
            for m in methods:
                print(f"    └─ {m}")
        else:
            for m in methods[:MAX_METHODS_DISPLAY]:
                print(f"    └─ {m}")
            print(f"    └─ ... 共 {len(methods)} 种变体")


# ==================== 子命令: view ====================
def _display_transactions(
    subset: list[TransactionDict],
    title: str,
    *,
    brief: bool = False,
) -> None:
    """显示交易子集.

    Args:
        subset: 要显示的交易列表
        title: 显示标题
        brief: 是否简洁模式
    """
    print_title(title)
    for txn in subset:
        print(format_txn(txn, show_metadata=not brief))
        print()


def cmd_view(args: argparse.Namespace) -> None:
    """查看交易记录.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    _base, bean_file, _, _, _config_file = resolve_paths(data_dir)
    transactions = parse_bean_file(bean_file)

    if not transactions:
        print_err("未找到任何交易记录")
        return

    brief_arg: bool = cast("bool", args.brief)
    brief = not brief_arg
    head_arg: int | None = cast("int | None", args.head)
    tail_arg: int | None = cast("int | None", args.tail)
    date_arg: str | None = cast("str | None", args.date)
    date_range_arg: str | None = cast("str | None", args.date_range)

    if head_arg:
        _display_transactions(
            transactions[:head_arg],
            f"前 {head_arg} 条交易",
            brief=brief,
        )
    elif tail_arg:
        subset = transactions[-tail_arg:]
        _display_transactions(
            subset,
            f"最后 {len(subset)} 条交易",
            brief=brief,
        )
    elif date_arg:
        filtered = [t for t in transactions if t["date"] == date_arg]
        _display_transactions(
            filtered,
            f"日期 {date_arg} 的交易 ({len(filtered)}条)",
            brief=brief,
        )
    elif date_range_arg:
        parts: list[str] = date_range_arg.split(",")
        if len(parts) == DATE_RANGE_PARTS:
            start: str = parts[0]
            end: str = parts[1]
            filtered = [t for t in transactions if start <= t["date"] <= end]
            _display_transactions(
                filtered,
                f"{start} ~ {end} 的交易 ({len(filtered)}条)",
                brief=brief,
            )
        else:
            print_err("--date-range 格式: YYYY-MM-DD,YYYY-MM-DD")
    else:
        _display_overview(transactions)


def _display_overview(transactions: list[TransactionDict]) -> None:
    """显示交易概览.

    Args:
        transactions: 交易列表
    """
    print_title(f"交易概览 (共 {len(transactions)} 条)")
    for txn in transactions:
        postings_str = ", ".join(
            f"{p['account'].split(':')[-1]} {p['amount']:+.2f}" for p in txn["postings"]
        )
        _dc: str = txn["metadata"].get("dc", "")
        type_: str = txn["metadata"].get("type", "")
        print(f"  {txn['date']} {txn['payee']:<20s}  {type_:<8s}  {postings_str}")


# ==================== 子命令: search ====================
def cmd_search(args: argparse.Namespace) -> None:
    """搜索特定账户的交易.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    _base, bean_file, _, _, _config_file = resolve_paths(data_dir)
    transactions = parse_bean_file(bean_file)

    if not transactions:
        print_err("未找到任何交易记录")
        return

    search_criteria = _get_search_criteria(args)
    if not search_criteria:
        print_warn("请提供搜索条件: --account, --payee 或 --type")
        return

    results = [txn for txn in transactions if _matches_criteria(txn, search_criteria)]

    if not results:
        print_warn("未找到匹配的交易")
        return

    account: str | None = cast("str | None", args.account)
    payee: str | None = cast("str | None", args.payee)
    type_: str | None = cast("str | None", args.type)
    label = account or payee or type_
    label_str = label or ""
    print_title(f"搜索结果: {label_str} ({len(results)}条)")

    # 金额汇总
    total_by_account: defaultdict[str, float] = defaultdict(float)
    for txn in results:
        for p in txn["postings"]:
            total_by_account[p["account"]] += p["amount"]

    brief_arg: bool = cast("bool", args.brief)
    for txn in results:
        print(format_txn(txn, show_metadata=not brief_arg))
        print()

    print_section("金额汇总")
    for acc, total in sorted(total_by_account.items(), key=lambda x: x[1]):
        sign = "+" if total >= 0 else ""
        print(f"  {acc}: {sign}{total:.2f} CNY")


def _get_search_criteria(args: argparse.Namespace) -> dict[str, str] | None:
    """从命令行参数获取搜索条件.

    Args:
        args: 命令行参数

    Returns:
        包含搜索条件的字典, 或 None
    """
    account_arg: str | None = getattr(args, "account", None)
    payee_arg: str | None = getattr(args, "payee", None)
    type_arg: str | None = getattr(args, "type", None)

    if account_arg:
        return {"type": "account", "value": account_arg}
    if payee_arg:
        return {"type": "payee", "value": payee_arg}
    if type_arg:
        return {"type": "type", "value": type_arg}
    return None


def _matches_criteria(
    txn: TransactionDict,
    criteria: dict[str, str],
) -> bool:
    """检查交易是否匹配搜索条件.

    Args:
        txn: 交易字典
        criteria: 搜索条件

    Returns:
        是否匹配
    """
    criteria_type = criteria["type"]
    value = criteria["value"]

    if criteria_type == "account":
        for posting in txn["postings"]:
            if value.upper() in posting["account"].upper():
                return True
    elif criteria_type == "payee":
        return value.lower() in txn["payee"].lower()
    elif criteria_type == "type":
        return value.lower() in txn["metadata"].get("type", "").lower()
    return False


# ==================== 子命令: check ====================
def cmd_check(args: argparse.Namespace) -> None:
    """验证 Beancount 语法.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    _base, bean_file, main_bean, _, _config_file = resolve_paths(data_dir)
    main_bean_arg: bool = cast("bool", args.main)

    target = main_bean if main_bean_arg else bean_file
    if not target.exists():
        print_err(f"文件不存在: {target}")
        return

    bean_check_cmd = shutil.which(_BEAN_CHECK_CMD)
    if not bean_check_cmd:
        print_err("bean-check 命令未找到,请确保 beancount 已安装")
        print("  安装方法: pip install beancount")
        return

    print_title(f"Beancount 语法检查: {target.name}")

    result = subprocess.run(
        [bean_check_cmd, str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode == 0:
        print_ok("语法检查通过,无错误！")
    else:
        print_err("发现语法错误:")
        print(result.stdout)
        if result.stderr:
            print(result.stderr)


# ==================== 子命令: report ====================
def cmd_report(args: argparse.Namespace) -> None:
    """生成报表.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    _base, bean_file, main_bean, _, _config_file = resolve_paths(data_dir)
    main_bean_arg: bool = cast("bool", args.main)

    target = main_bean if main_bean_arg else bean_file
    if not target.exists():
        print_err(f"文件不存在: {target}")
        return

    bean_report_cmd = shutil.which(_BEAN_REPORT_CMD)
    if not bean_report_cmd:
        print_err("bean-report 命令未找到,请确保 beancount 已安装")
        print("  安装方法: pip install beancount")
        return

    report_type: str = cast("str", args.report_type) or "balances"
    print_title(f"Beancount 报表: {report_type}")

    result = subprocess.run(
        [bean_report_cmd, str(target), report_type],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)


# ==================== 子命令: merge ====================
def cmd_merge(args: argparse.Namespace) -> None:
    """合并到主账本.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    _base, bean_file, main_bean, _, _config_file = resolve_paths(data_dir)
    include_arg: bool = cast("bool", args.include)

    if not bean_file.exists():
        print_err(f"导入文件不存在: {bean_file}")
        return

    if not main_bean.exists():
        print_err(f"主账本不存在: {main_bean}")
        return

    if include_arg:
        print_title("合并到主账本 (include 方式)")

        # 检查是否已经引用
        content, _ = read_file_auto(main_bean)
        if content:
            for line in content:
                if "imported_transactions.bean" in line:
                    print_warn("主账本已引用 imported_transactions.bean,无需重复添加")
                    return

        main_bean.open("a", encoding="utf-8").close()
        with main_bean.open("a", encoding="utf-8") as f:
            _ = f.write("\n;; 导入的支付宝账单\n")
            _ = f.write('include "imported_transactions.bean"\n')

        print_ok(f"已在 {main_bean.name} 中添加 include 引用")
    else:
        print_title("合并到主账本 (直接追加方式)")
        print_warn("此操作会将导入交易直接追加到主账本末尾")
        confirm = input("  确认继续？(y/N): ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

        import_content, _enc = read_file_auto(bean_file)
        if import_content:
            with main_bean.open("a", encoding="utf-8") as f:
                _ = f.write("\n;; 以下为导入的交易记录\n")
                f.writelines(import_content)
            print_ok(f"已将 {bean_file.name} 追加到 {main_bean.name}")


# ==================== 子命令: archive ====================
def cmd_archive(args: argparse.Namespace) -> None:
    """归档已导入的账单文件.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    base, _bean_file, _main_bean, downloads_dir, _config_file = resolve_paths(data_dir)

    if not downloads_dir.exists():
        print_err("downloads 目录不存在")
        return

    output: str = cast("str", args.output)
    archive_dir = base / (output or "archive")
    archive_dir.mkdir(exist_ok=True)

    csv_files = find_all_csv(downloads_dir)
    if not csv_files:
        print_warn("downloads 目录中没有 CSV 文件")
        return

    print_title("归档账单文件")

    for csv_file in csv_files:
        dest = archive_dir / csv_file.name
        if dest.exists():
            # 添加时间戳避免覆盖
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            dest = archive_dir / f"{csv_file.stem}_{ts}{csv_file.suffix}"

        _ = shutil.move(str(csv_file), str(dest))
        print_ok(f"{csv_file.name} -> {dest.relative_to(base)}")

    print(f"\n已归档 {len(csv_files)} 个文件到 {archive_dir.relative_to(base)}/")


# ==================== 子命令: clean ====================
def cmd_clean(args: argparse.Namespace) -> None:
    """清理空行.

    Args:
        args: 命令行参数
    """
    data_dir: str = cast("str", args.data_dir)
    _base, bean_file, _, _, _config_file = resolve_paths(data_dir)

    if not bean_file.exists():
        print_err(f"文件不存在: {bean_file}")
        return

    content, enc = read_file_auto(bean_file)
    if content is None:
        print_err("无法读取文件")
        return

    original_lines = len(content)
    cleaned = [line for line in content if line.strip() != ""]
    removed = original_lines - len(cleaned)

    if removed == 0:
        print_ok("文件中没有多余空行")
        return

    # 保留原编码写入
    write_enc = enc or "utf-8"
    with bean_file.open("w", encoding=write_enc) as f:
        f.writelines(cleaned)

    print_ok(f"已清理 {removed} 个空行 (原 {original_lines} 行 -> {len(cleaned)} 行)")


# ==================== 主入口 ====================
def main() -> None:
    """主入口函数,解析命令行参数并执行相应子命令."""
    parser = argparse.ArgumentParser(
        description="Beancount 导入管理脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    _ = parser.add_argument(
        "--data-dir",
        default="beancount-data",
        help="beancount-data 目录路径(默认: beancount-data)",
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # --- stats 子命令 ---
    p_stats = subparsers.add_parser("stats", help="统计分析")
    _ = p_stats.add_argument("--all", action="store_true", help="运行所有统计")
    _ = p_stats.add_argument(
        "--accounts", action="store_true", help="统计各账户交易次数和金额"
    )
    _ = p_stats.add_argument(
        "--payment", action="store_true", help="统计原始收付款方式汇总"
    )
    _ = p_stats.add_argument("--types", action="store_true", help="统计交易类型和状态")
    _ = p_stats.add_argument("--integrity", action="store_true", help="检查交易完整性")
    _ = p_stats.add_argument(
        "--mapping", action="store_true", help="对比原始支付方式和映射账户"
    )

    # --- view 子命令 ---
    p_view = subparsers.add_parser("view", help="查看交易记录")
    _ = p_view.add_argument("--head", type=int, metavar="N", help="查看前 N 条交易")
    _ = p_view.add_argument("--tail", type=int, metavar="N", help="查看最后 N 条交易")
    _ = p_view.add_argument("--date", metavar="YYYY-MM-DD", help="查看指定日期的交易")
    _ = p_view.add_argument(
        "--date-range", metavar="START,END", help="查看日期范围内的交易"
    )
    _ = p_view.add_argument(
        "--brief", action="store_true", help="简洁模式(不显示元数据)"
    )

    # --- search 子命令 ---
    p_search = subparsers.add_parser("search", help="搜索交易")
    _ = p_search.add_argument(
        "--account", "-a", metavar="KEYWORD", help="按账户关键词搜索"
    )
    _ = p_search.add_argument("--payee", "-p", metavar="KEYWORD", help="按收款方搜索")
    _ = p_search.add_argument("--type", "-t", metavar="KEYWORD", help="按交易类型搜索")
    _ = p_search.add_argument("--brief", action="store_true", help="简洁模式")

    # --- check 子命令 ---
    p_check = subparsers.add_parser("check", help="验证 Beancount 语法")
    _ = p_check.add_argument(
        "--main", action="store_true", help="检查主账本(默认检查导入文件)"
    )

    # --- report 子命令 ---
    p_report = subparsers.add_parser("report", help="生成报表")
    _ = p_report.add_argument(
        "report_type",
        nargs="?",
        default="balances",
        help="报表类型: balances, income_statement 等(默认: balances)",
    )
    _ = p_report.add_argument(
        "--main", action="store_true", help="使用主账本(默认使用导入文件)"
    )

    # --- merge 子命令 ---
    p_merge = subparsers.add_parser("merge", help="合并到主账本")
    _ = p_merge.add_argument(
        "--include",
        action="store_true",
        help="使用 include 方式引用(推荐,默认为直接追加)",
    )

    # --- archive 子命令 ---
    p_archive = subparsers.add_parser("archive", help="归档账单文件")
    _ = p_archive.add_argument(
        "-o", "--output", default="archive", help="归档目录(默认: archive)"
    )

    # --- clean 子命令 ---
    _ = subparsers.add_parser("clean", help="清理空行")

    args = parser.parse_args()

    command_arg: str | None = getattr(args, "command", None)
    if command_arg is None:
        # 默认运行 stats --all
        args.command = "stats"
        args.all = True
        args.accounts = False
        args.payment = False
        args.types = False
        args.integrity = False
        args.mapping = False

    commands: dict[str, Callable[[argparse.Namespace], None]] = {
        "stats": cmd_stats,
        "view": cmd_view,
        "search": cmd_search,
        "check": cmd_check,
        "report": cmd_report,
        "merge": cmd_merge,
        "archive": cmd_archive,
        "clean": cmd_clean,
    }

    cmd_func: Callable[[argparse.Namespace], None] | None = commands.get(args.command)  # type: ignore[assignment]
    if cmd_func:
        cmd_func(args)
    else:
        _ = parser.print_help()


if __name__ == "__main__":
    main()
