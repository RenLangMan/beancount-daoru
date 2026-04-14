# 在文件最开头添加
# pyright: reportUnknownVariableType=false
# pyright: reportUnusedCallResult=false
# pyright: reportAny=false
import os
import shutil
import sys
import warnings
from collections.abc import Generator
from pathlib import Path
from typing import Protocol

import git
import pytest
from xprocess import ProcessStarter, XProcess  # 确保这行正确

from tests.examples.conftest import (
    EXAMPLES_DIR,
    run_python_subprocess,
)

EXAMPLE_DIR = EXAMPLES_DIR / "predict"
DOWNLOADS_DIR = EXAMPLE_DIR / "downloads"
LEDGER_DIR = EXAMPLE_DIR / "ledger"
PREDICT_SCRIPTS = EXAMPLE_DIR / "import.py"
ACCOUNTS_FILE = LEDGER_DIR / "accounts.beancount"
EXISTING_FILE = LEDGER_DIR / "existing.beancount"
ZERO_SHOT_PREDICTED_FILE = LEDGER_DIR / "zero_shot_predicted.beancount"
FEW_SHOT_PREDICTED_FILE = LEDGER_DIR / "few_shot_predicted.beancount"


# 定义正确的接口协议
class StarterProtocol(Protocol):
    """定义 ProcessStarter 应该有的接口。"""

    @property
    def args(self) -> list[str]: ...

    @property
    def pattern(self) -> str: ...

    max_read_lines: int
    timeout: int


def start_llama_server(  # noqa: PLR0913
    *,
    xprocess: XProcess,
    model_path: str | None = None,
    model_hf: str | None = None,
    model_alias: str,
    port: int,
    ctx_size: int = 0,
    is_embedding: bool = False,
) -> Generator[None]:
    """启动 Llama.cpp 服务器进程。"""
    exec_name = "llama-server"
    if shutil.which(exec_name) is None:
        pytest.skip(f"{exec_name!r} not in PATH")

    # 使用简单的类定义,不重写 __init__
    class Starter(ProcessStarter):
        """Llama 服务器进程启动器。"""

        # 直接定义类属性
        max_read_lines = sys.maxsize
        timeout = 600

        @property
        def args(self) -> list[str]:
            cmd_args: list[str] = [exec_name]

            # 优先使用本地模型
            if model_path and Path(model_path).exists():
                cmd_args.extend(["-m", model_path])
            elif model_hf:
                cmd_args.extend(["-hf", model_hf])
            else:
                msg = "Either model_path or model_hf must be provided"
                raise ValueError(msg)

            cmd_args.extend(
                [
                    "--ctx-size",
                    str(ctx_size),
                    "--port",
                    str(port),
                    "--alias",
                    model_alias,
                    "--no-webui",
                ]
            )
            if is_embedding:
                cmd_args.append("--embedding")
            return cmd_args

        @property
        def pattern(self) -> str:
            return "main: server is listening on"

    server_name = f"{exec_name}-{port}-{model_alias}"
    _ = xprocess.ensure(server_name, Starter, persist_logs=False)
    yield
    # 终止进程
    proc_info = xprocess.getinfo(server_name)
    if proc_info.isrunning():
        proc_info.terminate()


@pytest.fixture(scope="session")
def embedding_server(xprocess: XProcess) -> Generator[None]:
    """嵌入模型服务器固件(session 级)。

    启动一个用于生成文本嵌入向量的 LLM 服务器。
    模型优先级:
    1. TEST_EMBEDDING_MODEL 环境变量指定的路径
    2. 默认路径 /opt/models/embeddinggemma-300m-Q4_0.gguf

    参数:
        xprocess: xprocess 实例,用于管理外部进程

    返回:
        服务器进程生成器,生命周期与测试会话相同

    环境变量:
        TEST_EMBEDDING_MODEL: 覆盖默认的嵌入模型路径
    """
    model_path = os.environ.get(
        "TEST_EMBEDDING_MODEL", "/opt/models/embeddinggemma-300m-Q4_0.gguf"
    )
    yield from start_llama_server(
        xprocess=xprocess,
        model_path=model_path,
        model_alias="embedding-model",
        port=1314,
        is_embedding=True,
        ctx_size=1024,
    )


@pytest.fixture(scope="session")
def chat_completion_server(xprocess: XProcess) -> Generator[None]:
    """聊天补全模型服务器固件(session 级)。

    启动一个用于生成文本补全的 LLM 服务器。
    模型优先级:
    1. TEST_CHAT_MODEL 环境变量指定的路径
    2. 默认路径 /opt/models/qwen3-4b-instruct-2507-iq4_nl.gguf

    参数:
        xprocess: xprocess 实例,用于管理外部进程

    返回:
        服务器进程生成器,生命周期与测试会话相同

    环境变量:
        TEST_CHAT_MODEL: 覆盖默认的聊天模型路径
    """
    model_path = os.environ.get(
        "TEST_CHAT_MODEL", "/opt/models/qwen3-4b-instruct-2507-iq4_nl.gguf"
    )
    yield from start_llama_server(
        xprocess=xprocess,
        model_path=model_path,
        model_alias="chat-model",
        port=9527,
        ctx_size=8 * 1024,
    )


def __check_diff_with_tolerance(
    git_repo: git.Repo, file_path: Path, /, max_lines: int
) -> None:
    """检查 Git diff 并在允许的行数内容忍差异.

    由于 LLM 生成结果可能具有非确定性,此函数允许一定数量的差异行。
    如果差异行数超过阈值则测试失败,否则仅发出警告。

    参数:
        git_repo: Git 仓库实例
        file_path: 要检查的文件路径
        max_lines: 允许的最大差异行数
    """
    diff = git_repo.git.diff(file_path)  # type: ignore[assignment]
    if diff and isinstance(diff, str):
        lines = diff.split("\n")
        changes = [
            line
            for line in lines
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        ]
        if len(changes) > max_lines:
            pytest.fail(diff)
        else:
            warnings.warn(diff, stacklevel=2)


@pytest.mark.llm
@pytest.mark.usefixtures("embedding_server", "chat_completion_server")
def test_zero_shot(git_repo: git.Repo) -> None:
    """测试零样本预测(Zero-shot prediction).

    使用账户定义文件作为上下文,让 LLM 预测交易中缺失的会计科目。
    允许最多 4 行的差异,因为 LLM 输出可能有轻微变化。

    参数:
        git_repo: Git 仓库实例
    """
    ZERO_SHOT_PREDICTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    run_python_subprocess(
        PREDICT_SCRIPTS,
        "extract",
        DOWNLOADS_DIR,
        "-e",
        ACCOUNTS_FILE,
        "-o",
        ZERO_SHOT_PREDICTED_FILE,
        cwd=EXAMPLE_DIR,
    )

    __check_diff_with_tolerance(git_repo, ZERO_SHOT_PREDICTED_FILE, max_lines=4)


@pytest.mark.llm
@pytest.mark.usefixtures("embedding_server", "chat_completion_server")
def test_few_shot(git_repo: git.Repo) -> None:
    """测试少样本预测(Few-shot prediction).

    使用现有账簿作为历史示例,让 LLM 基于相似交易预测缺失的会计科目。
    要求完全没有差异(max_lines=0),因为使用历史数据应该产生更稳定的结果。

    参数:
        git_repo: Git 仓库实例
    """
    FEW_SHOT_PREDICTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    run_python_subprocess(
        PREDICT_SCRIPTS,
        "extract",
        DOWNLOADS_DIR,
        "-e",
        EXISTING_FILE,
        "-o",
        FEW_SHOT_PREDICTED_FILE,
        cwd=EXAMPLE_DIR,
    )

    __check_diff_with_tolerance(git_repo, FEW_SHOT_PREDICTED_FILE, max_lines=0)
