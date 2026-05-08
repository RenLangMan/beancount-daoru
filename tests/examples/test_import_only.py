import git

from tests.examples.conftest import (
    EXAMPLES_DIR,
    run_python_subprocess,
)

EXAMPLE_DIR = EXAMPLES_DIR / "import_only"
DOWNLOADS_DIR = EXAMPLE_DIR / "downloads"
DOCUMENTS_DIR = EXAMPLE_DIR / "documents"
IMPORTERS_DIR = EXAMPLE_DIR / "importers"
LEDGER_DIR = EXAMPLE_DIR / "ledger"
IMPORT_SCRIPT = EXAMPLE_DIR / "import.py"
IMPORTED_FILE = LEDGER_DIR / "imported.beancount"


def test_extract(git_repo: git.Repo) -> None:
    """测试从下载目录提取交易数据并导入.

    此测试执行导入脚本的 extract 命令,将下载目录中的账单文件
    转换为 Beancount 格式并保存到 ledger 目录。
    最后检查 Git 状态,确保没有未预期的修改。

    参数:
        git_repo: Git 仓库实例
    """
    IMPORTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    run_python_subprocess(
        IMPORT_SCRIPT,
        "extract",
        DOWNLOADS_DIR,
        "-o",
        IMPORTED_FILE,
        cwd=EXAMPLE_DIR,
    )

    diff = git_repo.git.diff(IMPORTED_FILE)  # pyright: ignore[reportAny]
    assert not diff, f"diff found\n{diff}\n"


def test_archive(git_repo: git.Repo) -> None:
    """测试归档处理后的账单文件.

    此测试执行导入脚本的 archive 命令,将下载目录中已处理的账单文件
    移动到 documents 目录进行归档。验证归档操作不会产生意外的文件修改
    或新文件。

    参数:
        git_repo: Git 仓库实例
    """
    try:
        run_python_subprocess(
            IMPORT_SCRIPT,
            "archive",
            DOWNLOADS_DIR,
            "-o",
            DOCUMENTS_DIR,
            "--overwrite",
            cwd=EXAMPLE_DIR,
        )

        # 检查是否有已跟踪文件的修改
        modification = git_repo.git.diff("--name-status", DOCUMENTS_DIR)  # pyright: ignore[reportAny]
        assert not modification, f"modification found\n{modification}\n"

        # 检查是否有未跟踪的新文件
        new_files = git_repo.git.ls_files("--others", DOCUMENTS_DIR)  # pyright: ignore[reportAny]
        assert not new_files, f"unexpected files found\n{new_files}\n"

    finally:
        # 恢复下载目录,确保下次测试时环境干净
        git_repo.git.restore("--worktree", DOWNLOADS_DIR)  # pyright: ignore[reportAny]
