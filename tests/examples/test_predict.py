import shutil
import sys
import warnings
from collections.abc import Generator
from pathlib import Path

import git
import pytest
from typing_extensions import override
from xprocess import ProcessStarter, XProcess

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


def start_llama_server(  # noqa: PLR0913
    *,
    xprocess: XProcess,
    model_hf: str,
    model_alias: str,
    port: int,
    ctx_size: int = 0,
    is_embedding: bool = False,
) -> Generator[None]:
    """启动 Llama.cpp 服务器进程。

    此函数启动一个 llama-server 进程，用于提供 LLM 推理服务。
    支持嵌入模型和聊天补全模型两种模式。

    参数：
        xprocess: xprocess 实例，用于管理外部进程
        model_hf: Hugging Face 模型标识符
        model_alias: 模型别名
        port: 服务端口号
        ctx_size: 上下文大小（token 数）
        is_embedding: 是否为嵌入模式（True）还是聊天补全模式（False）

    返回：
        生成器，在服务器运行期间保持进程

    注意：
        如果 llama-server 不在 PATH 中，测试会被跳过
    """
    exec_name = "llama-server"
    if shutil.which(exec_name) is None:
        pytest.skip(f"{exec_name!r} not in PATH")

    class Starter(ProcessStarter):
        """Llama 服务器进程启动器。"""

        @property
        @override
        def args(self) -> list[str]:  # pyright: ignore[reportIncompatibleMethodOverride]
            """构建启动命令参数列表。"""
            cmd_args: list[str] = [
                exec_name,
                "-hf",
                model_hf,
                "--ctx-size",
                str(ctx_size),
                "--port",
                str(port),
                "--alias",
                model_alias,
                "--no-webui",
            ]
            if is_embedding:
                cmd_args.append("--embedding")
            return cmd_args

        @property
        @override
        def pattern(self) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
            """匹配进程启动成功的日志模式。"""
            return "main: server is listening on"

        max_read_lines: int = sys.maxsize

    server_name = f"{exec_name}-{port}-{model_alias}"
    _ = xprocess.ensure(server_name, Starter, persist_logs=False)  # pyright: ignore[reportUnknownVariableType]
    yield
    _ = xprocess.getinfo(server_name).terminate()


@pytest.fixture(scope="session")
def embedding_server(xprocess: XProcess) -> Generator[None]:
    """嵌入模型服务器固件。

    启动一个用于生成文本嵌入向量的 LLM 服务器。
    使用 unsloth/embeddinggemma-300m-GGUF 量化模型。

    参数：
        xprocess: xprocess 实例

    返回：
        服务器进程生成器
    """
    yield from start_llama_server(
        xprocess=xprocess,
        model_hf="unsloth/embeddinggemma-300m-GGUF:Q4_0",
        model_alias="embeddinggemma-300m",
        port=1314,
        is_embedding=True,
        ctx_size=1024,
    )


@pytest.fixture(scope="session")
def chat_completion_server(xprocess: XProcess) -> Generator[None]:
    """聊天补全模型服务器固件。

    启动一个用于生成文本补全的 LLM 服务器。
    使用 unsloth/Qwen3-4B-Instruct-2507-GGUF 量化模型。

    参数：
        xprocess: xprocess 实例

    返回：
        服务器进程生成器
    """
    yield from start_llama_server(
        xprocess=xprocess,
        model_hf="unsloth/Qwen3-4B-Instruct-2507-GGUF:IQ4_NL",
        model_alias="Qwen3-4B-Instruct-2507",
        port=9527,
        ctx_size=8 * 1024,
    )


def __check_diff_with_tolerance(
    git_repo: git.Repo, file_path: Path, /, max_lines: int
) -> None:
    """检查 Git diff 并在允许的行数内容忍差异。

    由于 LLM 生成结果可能具有非确定性，此函数允许一定数量的差异行。
    如果差异行数超过阈值则测试失败，否则仅发出警告。

    参数：
        git_repo: Git 仓库实例
        file_path: 要检查的文件路径
        max_lines: 允许的最大差异行数
    """
    diff: str = git_repo.git.diff(file_path)  # pyright: ignore[reportAny]
    if diff:
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


@pytest.mark.usefixtures("embedding_server", "chat_completion_server")
def test_zero_shot(git_repo: git.Repo) -> None:
    """测试零样本预测（Zero-shot prediction）。

    使用账户定义文件作为上下文，让 LLM 预测交易中缺失的会计科目。
    允许最多 4 行的差异，因为 LLM 输出可能有轻微变化。

    参数：
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


@pytest.mark.usefixtures("embedding_server", "chat_completion_server")
def test_few_shot(git_repo: git.Repo) -> None:
    """测试少样本预测（Few-shot prediction）。

    使用现有账簿作为历史示例，让 LLM 基于相似交易预测缺失的会计科目。
    要求完全没有差异（max_lines=0），因为使用历史数据应该产生更稳定的结果。

    参数：
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
