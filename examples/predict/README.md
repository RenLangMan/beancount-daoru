# 示例：导入并分类

这是一个高级导入示例，演示如何使用 LLM（大语言模型）对账单进行智能分类。

```plaintext
predict/
├── downloads/     # 待导入的账单文件
├── ledger/        # 导入结果目录
│   ├── accounts.beancount         # 账户定义文件（从现有账户中进行预测）
│   ├── existing.beancount         # 现有的交易记录（用于Zero-shot 预测）
│   ├── few_shot_predicted.beancount  # Few-shot 预测结果
│   └── zero_shot_predicted.beancount # Zero-shot 预测结果
├── import.py      # 导入配置脚本
└── README.md      # 说明文档
```

## 使用 llama.cpp 部署开源模型

在 Windows 11 上可通过 winget 安装 llama.cpp，默认支持 vulkan 加速。其他安装方式可参考 [llama.cpp 的安装文档](https://github.com/ggml-org/llama.cpp?tab=readme-ov-file#quick-start)。

```powershell
winget install llama.cpp
```

分别部署用于 Embedding 和 Chat 的模型，例子中使用最轻量的模型。

```shell
llama-server -hf 'unsloth/embeddinggemma-300m-GGUF:Q4_0' --port 1314 \
  --embedding
llama-server -hf 'unsloth/Qwen3-4B-Instruct-2507-GGUF:IQ4_NL' --port 9527
```

> [!TIP]
> 如果网络不通，可设置环境变量从 ModelScope 下载模型
>
> ```powershell
> $env:MODEL_ENDPOINT="https://www.modelscope.cn"
> ```

通过 openai 的 v1/models 接口查询 llama.cpp 识别到的模型名称（未必与文件名一致）

```powershell
curl http://127.0.0.1:1314/v1/models
curl http://127.0.0.1:9527/v1/models
```

## 使用 beangulp 命令导入

> [!NOTE]
> `import.py` 会自动切换到脚本所在目录, 因此**无论从哪个目录执行**, `downloads/`、`ledger/` 等相对路径都能正确解析.
>
> [!WARNING]
> 在 Windows 上, 建议设置环境变量使 Python 全局使用 UTF-8, 能够避免很多编码问题.
>
> ```powershell
> $env:PYTHONUTF8 = "1"
> ```
>
> 脚本已内置自动重启机制(Windows 下若 `PYTHONUTF8` 未设置会自动以 UTF-8 模式重启),
> 但手动设置环境变量可避免重启带来的额外开销.

### 方式一：在示例目录下执行

```shell
cd examples/predict

# 查看是否能够识别账单文件
python import.py identify downloads

# 提取并预测分类
python import.py extract downloads -o ledger/predicted.beancount -e ledger/existing.beancount

# 文件归档
python import.py archive downloads -o documents
```

### 方式二：从项目根目录执行

```shell
# 在项目根目录下执行，路径无需调整
python examples/predict/import.py identify downloads
python examples/predict/import.py extract downloads -o ledger/predicted.beancount -e ledger/existing.beancount
python examples/predict/import.py archive downloads -o documents
```

### 命令说明

| 命令                                          | 说明                                                                                              |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `identify downloads`                          | 扫描 `downloads` 目录，显示哪些文件可被识别和导入                                                 |
| `extract downloads -o <output> -e <existing>` | 将账单文件转换为 Beancount 格式，并用 LLM 预测缺失的分类；`-e` 指定已有交易记录用于 Few-shot 参考 |
| `archive downloads -o documents`              | 将已导入的账单文件移动到 `documents` 目录，避免重复导入                                           |

> [!TIP]
> `archive` 命令若提示 `Destination file already exists`，说明文件之前已归档过，
> 这是 `beangulp` 的安全机制，防止覆盖已有文件。如需重新归档，请先删除 `documents/` 中对应的文件。
