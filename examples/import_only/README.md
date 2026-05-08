# 示例：仅导入

这是一个基础的导入示例，演示如何使用 beancount-daoru 工具将账单文件导入到 Beancount 中。

```plaintext
import_only/
├── documents/     # 归档的账单文件
├── downloads/     # 待导入的账单文件
├── ledger/        # 导入结果目录
│   └── imported.beancount  # 导入的交易记录
├── import.py      # 导入配置脚本
└── README.md      # 说明文档
```

## 使用 beangulp 命令导入

> [!NOTE]
> `import.py` 会自动切换到脚本所在目录, 因此**无论从哪个目录执行**, `downloads/`、`ledger/`、`documents/` 等相对路径都能正确解析.
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
cd examples/import_only

# 查看是否能够识别账单文件
python import.py identify downloads

# 提取交易数据到指定文件中
python import.py extract downloads -o ledger/imported.beancount

# 文件归档
python import.py archive downloads -o documents
```

### 方式二：从项目根目录执行

```shell
# 在项目根目录下执行，路径无需调整
python examples/import_only/import.py identify downloads
python examples/import_only/import.py extract downloads -o ledger/imported.beancount
python examples/import_only/import.py archive downloads -o documents
```

### 命令说明

| 命令                                             | 说明                                                    |
| ------------------------------------------------ | ------------------------------------------------------- |
| `identify downloads`                             | 扫描 `downloads` 目录，显示哪些文件可被识别和导入       |
| `extract downloads -o ledger/imported.beancount` | 将可识别的账单文件转换为 Beancount 格式交易记录         |
| `archive downloads -o documents`                 | 将已导入的账单文件移动到 `documents` 目录，避免重复导入 |

> [!TIP]
> `archive` 命令若提示 `Destination file already exists`，说明文件之前已归档过，
> 这是 `beangulp` 的安全机制，防止覆盖已有文件。如需重新归档，请先删除 `documents/` 中对应的文件。
