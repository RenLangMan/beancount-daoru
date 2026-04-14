#!/usr/bin/env python3
"""Chinese account name support patch for Beancount.

Apply this patch to enable Chinese characters in account names.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path


def apply_chinese_support() -> bool:
    """Apply Chinese account name support to Beancount."""
    try:
        import beancount

        account_path = Path(beancount.__file__).parent / "core" / "account.py"
        print(f"Target file: {account_path}")

        if not account_path.exists():
            print("[X] File not found")
            return False

        content = account_path.read_text(encoding="utf-8")

        # Check if patch already applied
        if r"\p{Han}" in content:
            print("[V] Chinese support already exists")
            return True

        # Pattern to replace
        old_str = r'ACC_COMP_NAME_RE = r"[\p{Lu}\p{Nd}][\p{L}\p{Nd}\-]*"'
        new_str = (
            r'ACC_COMP_NAME_RE = r"[\p{Han}\p{Lu}\p{Nd}][\p{Han}\p{L}\p{Nd}\-]*"'
            "  # Account name components (e.g. Cash or 现金)"
        )

        if old_str not in content:
            print("[X] Pattern not found")
            for i, line in enumerate(content.splitlines(), 1):
                if "ACC_COMP_NAME_RE" in line:
                    print(f"  Line {i}: {line}")
            return False

        # Create backup
        backup_path = account_path.with_suffix(".py.bak")
        if not backup_path.exists():
            _ = shutil.copy2(account_path, backup_path)
            print(f"[V] Backup created: {backup_path}")

        # Apply patch
        new_content = content.replace(old_str, new_str)
        _ = account_path.write_text(new_content, encoding="utf-8")
        print("[V] Chinese account name support added")
        return True

    except ImportError:
        print("[X] Cannot import beancount module")
        return False
    except OSError as e:
        print(f"[X] Patch failed: {e}")
        return False


def main() -> None:
    """Main entry point."""
    print("Applying Chinese account name support patch...")
    print("=" * 50)

    if apply_chinese_support():
        print("=" * 50)
        print("[V] Patch applied successfully!")
        print("\nYou can now use Chinese account names, e.g.:")
        print("  Assets:银行:工商银行:储蓄卡")
        print("  Income:工资:基本工资")
        print("  Expenses:食品:早餐")
        sys.exit(0)
    else:
        print("=" * 50)
        print("[X] Patch application failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
