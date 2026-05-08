"""账本重构核心模块.

提供账本加载、分析、排序和输出功能.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from beancount import loader
from beancount.parser import printer

from beancount_daoru.rebuilder.sorter import EntrySorter

if TYPE_CHECKING:
    from beancount.core.data import Directive


class LedgerRebuilder:
    """账本重构器.

    功能:
    - 加载 beancount 文件
    - 按日期范围筛选
    - 去重 Balance 条目
    - 按时间戳排序
    - 按月份分组输出

    输出结构:
    ```
    output_dir/
    ├── accounts/
    │   └── all.bean          # Open/Close 条目
    ├── config/
    │   ├── commodities.bean  # Commodity 定义
    │   ├── custom.bean       # Custom 条目
    │   └── prices.bean       # Price 条目
    ├── transactions/
    │   ├── 2024/
    │   │   ├── 01.bean       # 1月所有条目(已排序)
    │   │   ├── 02.bean       # 2月所有条目(已排序)
    │   │   └── ...
    │   └── ...
    └── main.bean             # 主索引文件
    ```
    """

    # 配置类条目类型（不受日期筛选影响）
    CONFIG_TYPES: frozenset[str] = frozenset(
        {"Open", "Close", "Commodity", "Custom", "Price"}
    )

    def __init__(  # noqa: PLR0913
        self,
        source_file: str | Path,
        output_dir: str | Path,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        deduplicate_balance: bool = True,
        group_by_source: bool = False,
    ) -> None:
        """初始化重构器.

        Args:
            source_file: 源 beancount 文件路径
            output_dir: 输出目录路径
            start_date: 开始日期（包含）
            end_date: 结束日期（包含）
            deduplicate_balance: 是否去重 Balance 条目
            group_by_source: 是否按源文件分组
        """
        self.source_file = Path(source_file).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.start_date = start_date
        self.end_date = end_date
        self.deduplicate_balance = deduplicate_balance
        self.group_by_source = group_by_source

        # 验证源文件
        if not self.source_file.exists():
            msg = f"源文件不存在: {self.source_file}"
            raise FileNotFoundError(msg)

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 状态
        self.entries: list[Directive] = []
        self.errors: list[Any] = []
        self.options: dict[str, Any] = {}
        self.stats = {
            "total": 0,
            "filtered": 0,
            "deduplicated": 0,
            "by_type": defaultdict(int),
        }
        self._balance_cache: set[tuple] = set()

    def load(self) -> LedgerRebuilder:
        """加载源文件."""
        print(f"📖 加载: {self.source_file}")
        self.entries, self.errors, self.options = loader.load_file(
            str(self.source_file)
        )
        print(f"✅ 加载完成: {len(self.entries)} 条记录")

        if self.errors:
            print(f"⚠️  发现 {len(self.errors)} 个错误")

        return self

    def filter_entries(self) -> LedgerRebuilder:
        """筛选条目（按日期范围、去重）."""
        filtered: list[Directive] = []

        for entry in self.entries:
            # 检查是否应该包含
            if not self._should_include(entry):
                self.stats["filtered"] += 1
                continue

            # 检查 Balance 去重
            if self._is_duplicate_balance(entry):
                self.stats["deduplicated"] += 1
                continue

            filtered.append(entry)
            self.stats["by_type"][type(entry).__name__] += 1

        self.entries = filtered
        self.stats["total"] = len(filtered)
        print(f"✅ 筛选完成: {self.stats['total']} 条")

        return self

    def _should_include(self, entry: Directive) -> bool:
        """判断条目是否应该包含."""
        entry_type = type(entry).__name__

        # 配置类条目始终包含
        if entry_type in self.CONFIG_TYPES:
            return True

        # 无日期属性也包含
        if not hasattr(entry, "date"):
            return True

        entry_date = entry.date

        # 日期范围检查
        if self.start_date and entry_date < self.start_date:
            return False
        return not (self.end_date and entry_date > self.end_date)

    def _is_duplicate_balance(self, entry: Directive) -> bool:
        """检查是否是重复的 Balance 条目."""
        if not self.deduplicate_balance:
            return False
        if type(entry).__name__ != "Balance":
            return False

        # 创建唯一键
        # 使用 hasattr 确保类型检查兼容性
        amount = getattr(entry, "amount", None)
        account = getattr(entry, "account", "")
        key = (
            entry.date,
            account,
            str(amount.number) if amount else "",
            amount.currency if amount else "",
        )

        if key in self._balance_cache:
            return True

        self._balance_cache.add(key)
        return False

    def rebuild(self) -> LedgerRebuilder:
        """执行重构."""
        print("=" * 60)
        print(" Beancount 账本重构")
        print("=" * 60)

        self.load().filter_entries()

        # 分离配置类条目和交易类条目
        config_entries = []
        transaction_entries = []

        for entry in self.entries:
            if type(entry).__name__ in self.CONFIG_TYPES:
                config_entries.append(entry)
            else:
                transaction_entries.append(entry)

        # 对条目元数据排序
        EntrySorter.sort_entries_metadata(transaction_entries)
        EntrySorter.sort_entries_metadata(config_entries)

        # 对交易类条目排序并按日期分组
        sorted_grouped = EntrySorter.sort_and_group_by_date(transaction_entries)

        # 写入文件
        self._write_config_files(config_entries)
        self._write_transaction_files(sorted_grouped)
        self._write_main_index(sorted_grouped)

        print("\n" + "=" * 60)
        print("🎉 重构完成!")
        print(f"输出目录: {self.output_dir}")
        print("=" * 60)

        return self

    def _write_config_files(self, entries: list[Directive]) -> None:
        """写入配置类条目."""
        config_dir = self.output_dir / "config"
        config_dir.mkdir(exist_ok=True)

        # 按类型分组
        by_type: dict[str, list[Directive]] = defaultdict(list)
        for entry in entries:
            by_type[type(entry).__name__].append(entry)

        # 写入各类配置文件
        for entry_type, type_entries in sorted(by_type.items()):
            filename = f"{entry_type.lower()}s.bean"
            filepath = config_dir / filename

            with filepath.open("w", encoding="utf-8") as f:
                f.write(self._file_header(f"{entry_type} 定义"))
                for entry in type_entries:
                    printer.print_entry(entry, file=f)
                    f.write("\n")

            print(f"✅ {filename}: {len(type_entries)} 条")

    def _write_transaction_files(
        self,
        grouped_entries: dict[date, list[Directive]],
    ) -> None:
        """写入交易类条目（按月份分组）."""
        tx_dir = self.output_dir / "transactions"
        tx_dir.mkdir(exist_ok=True)

        # 按年月组织，每月的所有条目合并到一个文件
        by_year_month: dict[tuple[int, int], list[Directive]] = defaultdict(list)
        for entry_date, entries in grouped_entries.items():
            by_year_month[(entry_date.year, entry_date.month)].extend(entries)

        # 写入文件
        total_months = 0
        for (year, month), month_entries in sorted(by_year_month.items()):
            month_file = tx_dir / f"{year}" / f"{month:02d}.bean"
            month_file.parent.mkdir(parents=True, exist_ok=True)

            with month_file.open("w", encoding="utf-8") as f:
                f.write(
                    self._file_header(
                        f"{year}年{month:02d}月",
                        extra=f"条目数: {len(month_entries)}",
                    )
                )

                # 写入该月所有条目（已排序）
                for entry in month_entries:
                    # 可选：添加时间戳注释
                    if hasattr(entry, "meta") and entry.meta:
                        ts = entry.meta.get("timestamp")
                        if ts:
                            f.write(f"; timestamp: {ts}\n")

                    printer.print_entry(entry, file=f)
                    f.write("\n")

            total_months += 1

        total_entries = sum(len(e) for e in grouped_entries.values())
        print(f"✅ 交易文件: {total_months} 月, {total_entries} 条")

    def _write_main_index(
        self,
        grouped_entries: dict[date, list[Directive]],
    ) -> None:
        """写入主索引文件."""
        main_file = self.output_dir / "main.bean"

        # 收集所有年月
        year_months = sorted({(d.year, d.month) for d in grouped_entries})

        with main_file.open("w", encoding="utf-8") as f:
            f.write(self._file_header("主索引", extra=f"总条目: {self.stats['total']}"))

            # 配置
            f.write("\n; ========== 配置 ==========\n")
            config_dir = self.output_dir / "config"
            if config_dir.exists():
                for config_file in sorted(config_dir.glob("*.bean")):
                    rel_path = config_file.relative_to(self.output_dir)
                    f.write(f'include "{rel_path}"\n')

            # 交易（按年月）
            f.write("\n; ========== 交易 ==========\n")
            for year, month in year_months:
                rel_path = f"transactions/{year}/{month:02d}.bean"
                f.write(f'include "{rel_path}"\n')

        print(f"✅ 主索引: {main_file}")

    def _file_header(self, title: str, extra: str | None = None) -> str:
        """生成文件头."""
        lines = [
            "; " + "=" * 50,
            f"; {title}",
        ]
        if extra:
            lines.append(f"; {extra}")
        lines.extend(
            [
                f"; 生成时间: {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",  # noqa: E501
                "; " + "=" * 50,
                "",
            ]
        )
        return "\n".join(lines)

    def print_stats(self) -> None:
        """打印统计信息."""
        print("\n📊 统计:")
        print("-" * 40)
        print(f"筛选: {self.stats['filtered']} 条")
        print(f"去重: {self.stats['deduplicated']} 条")
        print("-" * 40)
        for entry_type, count in sorted(
            self.stats["by_type"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {entry_type:15s}: {count:6d}")
