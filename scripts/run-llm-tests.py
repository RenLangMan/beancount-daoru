#!/usr/bin/env python3
"""LLM 测试菜单 - 交互式选择运行单个测试函数."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 测试文件和测试函数映射
TESTS: dict[str, list[str]] = {
    "=== 端到端测试 (需要真实模型) ===": [
        "test_examples/test_predict.py::test_zero_shot",
        "test_examples/test_predict.py::test_few_shot",
    ],
    # Excel Reader 测试
    "Excel Reader (Excel读取器)": [
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_init_with_header",
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_init_with_encoding",
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_convert_none",
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_convert_string",
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_convert_integer",
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_convert_float",
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_convert_empty_string",
        "beancount_daoru/readers/test_excel.py::TestExcelReader::test_convert_whitespace_only",
        "beancount_daoru/readers/test_excel.py::TestExcelReaderIntegration::test_read_captions_csv",
        "beancount_daoru/readers/test_excel.py::TestExcelReaderIntegration::test_read_captions_no_header",
        "beancount_daoru/readers/test_excel.py::TestExcelReaderIntegration::test_read_records_csv",
        "beancount_daoru/readers/test_excel.py::TestExcelReaderIntegration::test_read_records_with_whitespace",
        "beancount_daoru/readers/test_excel.py::TestExcelReaderIntegration::test_read_records_no_data_rows",
        "beancount_daoru/readers/test_excel.py::TestExcelReaderIntegration::test_read_captions_multiline",
        "beancount_daoru/readers/test_excel.py::TestExcelReaderIntegration::test_read_records_with_special_chars",
    ],
    # PDF Table Reader 测试
    "PDF Table Reader (PDF表格读取器)": [
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReader::test_init",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReader::test_init_with_float_bbox",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_captions_single_page",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_captions_multi_page",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_captions_empty_text",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_single_page",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_multi_page",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_no_table",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_empty_table",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_strips_whitespace",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_handles_none_values",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_header_with_none",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_records_mixed_pages",
        "beancount_daoru/readers/test_pdf_table.py::TestPdfTableReaderMocked::test_read_captions_and_records_together",
    ],
    # Encoder 测试
    "Encoder (嵌入编码器)": [
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEncoder::test_encode_cached",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEncoder::test_encode_miss_cache",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEncoder::test_encode_different_texts",
    ],
    # TransactionIndex 测试
    "TransactionIndex (交易索引)": [
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestTransactionIndex::test_add_transaction",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestTransactionIndex::test_search_empty_index",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestTransactionIndex::test_hash_consistency",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestTransactionIndex::test_hash_different_texts",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestTransactionIndex::test_search_topk",
    ],
    # HistoryIndex 测试
    "HistoryIndex (历史索引)": [
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_add_open_directive",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_add_open_duplicate_raises",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_add_close_directive",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_add_close_non_existing_raises",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_add_transaction_with_non_existing_account",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_check_transaction_valid",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_check_transaction_with_warning_flag",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_check_transaction_single_posting",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_check_transaction_posting_with_flag",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHistoryIndex::test_search_returns_similar_transactions",
    ],
    # ChatBot 测试
    "ChatBot (聊天机器人)": [
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestChatBot::test_complete_success",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestChatBot::test_complete_with_temperature",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestChatBot::test_complete_content_none_raises",
    ],
    # AccountPredictor 测试
    "AccountPredictor (账户预测器)": [
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_check_transaction_valid",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_check_transaction_multi_posting",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_system_prompt_contains_role",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_system_prompt_with_extra_prompt",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_user_prompt_format",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_user_prompt_with_similar",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_response_format",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_predict_invalid_transaction_returns_none",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_predict_returns_formatted_account",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_predict_returns_null_for_null_response",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestAccountPredictor::test_predict_preserves_exclamation",
    ],
    # Hook 测试
    "Hook (钩子初始化)": [
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHook::test_hook_initialization",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHook::test_hook_with_cache_dir",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestHook::test_hook_with_extra_prompt",
    ],
    # 边界情况测试
    "EdgeCases (边界情况)": [
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEdgeCases::test_encoder_empty_text",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEdgeCases::test_encoder_unicode_text",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEdgeCases::test_hash_unicode",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEdgeCases::test_account_predictor_check_none_flag",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEdgeCases::test_account_predictor_check_posting_none_flag",
        "beancount_daoru/hooks/test_predict_missing_posting.py::TestEdgeCases::test_history_index_accounts_property",
    ],
}


def flatten_tests() -> dict[int, tuple[str, str]]:
    """将测试列表扁平化为编号映射."""
    items: dict[int, tuple[str, str]] = {}
    idx = 1
    for section, test_list in TESTS.items():
        for test in test_list:
            items[idx] = (section, test)
            idx += 1
    return items


def print_menu() -> None:
    """打印菜单."""
    print("\n" + "=" * 60)
    print("       LLM 测试菜单 - 按编号选择测试")
    print("=" * 60)

    idx = 1
    current_section = ""
    for section, test_list in TESTS.items():
        if section != current_section:
            print(f"\n{section}")
            current_section = section
        for test in test_list:
            # 提取简短的测试名
            test_name = test.split("::")[-1]
            print(f"  {idx:2d}. {test_name}")
            idx += 1

    print("\n" + "-" * 60)
    print("  0. 运行所有单元测试 (不含集成测试)")
    print("  a. 运行所有端到端测试 (需要真实模型)")
    print("  q. 退出")
    print("-" * 60)


def run_test(test_path: str) -> int:
    """运行单个测试."""
    cmd = [
        "python",
        "-m",
        "pytest",
        f"tests/{test_path}",
        "-v",
        "--tb=short",
        "-p",
        "no:xprocess",  # 跳过 xprocess (避免启动服务器)
    ]
    print(f"\n>>> 运行: {test_path}")
    print("-" * 40)
    result = subprocess.run(cmd, check=False, cwd=Path(__file__).parent.parent)
    return result.returncode


def run_all_unit_tests() -> int:
    """运行所有单元测试 (不含端到端集成测试)."""
    print("\n>>> 运行所有单元测试...")
    print("-" * 40)
    cmd = [
        "python",
        "-m",
        "pytest",
        "tests/beancount_daoru/hooks/test_predict_missing_posting.py",
        "-v",
        "--tb=short",
    ]
    result = subprocess.run(cmd, check=False, cwd=Path(__file__).parent.parent)
    return result.returncode


def run_all_e2e_tests() -> int:
    """运行所有端到端集成测试."""
    print("\n>>> 运行所有端到端测试 (需要真实模型)...")
    print("-" * 40)
    cmd = [
        "python",
        "-m",
        "pytest",
        "tests/examples/test_predict.py",
        "-v",
        "--tb=short",
        "-m",
        "llm",
    ]
    result = subprocess.run(cmd, check=False, cwd=Path(__file__).parent.parent)
    return result.returncode


def main() -> None:
    """主函数 - 显示测试菜单并运行选择的测试."""
    tests = flatten_tests()

    while True:
        print_menu()

        try:
            choice = input("\n请选择 (0/a/q/编号): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\n退出")
            sys.exit(0)

        if choice == "q":
            print("退出")
            break

        if choice == "0":
            run_all_unit_tests()
            continue

        if choice == "a":
            run_all_e2e_tests()
            continue

        try:
            idx = int(choice)
            if idx < 1 or idx > len(tests):
                print(f"无效选择，请输入 0-{len(tests)} 之间的数字")
                continue
        except ValueError:
            print("无效输入，请输入数字、a 或 q")
            continue

        _section, test_path = tests[idx]
        run_test(test_path)


if __name__ == "__main__":
    main()
