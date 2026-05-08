import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import git
import pytest

EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"


@pytest.fixture(scope="session")
def git_repo() -> Generator[git.Repo]:
    """创建 Git 仓库实例的测试固件.

    此固件在整个测试会话中提供 Git 仓库实例,
    并配置 Git 以正确处理中文路径名(设置 core.quotepath=false)。

    返回:
        Git 仓库对象生成器

    生成:
        Git 仓库实例
    """
    repo = git.Repo(EXAMPLES_DIR, search_parent_directories=True)
    with repo.config_writer() as config:
        _ = config.set_value("core", "quotepath", "false")
        yield repo


def run_python_subprocess(
    *args: str | Path,
    cwd: Path,
) -> None:
    """在子进程中运行 Python 脚本.

    此函数在指定的工作目录中启动一个 Python 子进程来执行给定的脚本。
    自动处理路径转换,并设置 UTF-8 编码以正确处理中文输出。

    参数:
        *args: 要执行的 Python 脚本参数(字符串或路径对象)
        cwd: 子进程的工作目录

    异常:
        subprocess.CalledProcessError: 当子进程返回非零退出码时抛出
    """
    cmd = [sys.executable]
    for arg in args:
        if isinstance(arg, Path):
            # 将绝对路径转换为相对于工作目录的路径
            cmd.append(str(arg.relative_to(cwd)))
        else:
            cmd.append(arg)

    _ = subprocess.run(
        cmd,
        cwd=cwd,
        env=os.environ.copy() | {"PYTHONUTF8": "1"},
        check=True,
    )
