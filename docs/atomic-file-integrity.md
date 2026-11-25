# COMMON-06 文件完整性与原子写入

证据和报告需要等内容全部写好，再出现在正式路径。直接用写入模式打开正式文件会先截断旧内容。这里使用同目录的临时文件，写完后先刷新缓冲并同步文件，再关闭句柄，最后用 `os.replace` 发布。同目录能避免跨文件系统替换，先关闭句柄也便于在 Windows 上替换。失败时调用方会收到原始错误，临时文件尽可能清理。
[Python 文件替换](https://docs.python.org/3.12/library/os.html#os.replace) · [Python 临时文件](https://docs.python.org/3.12/library/tempfile.html#tempfile.NamedTemporaryFile)

| 函数 | 用途 |
| --- | --- |
| `atomic_write_bytes(path, content)` | 写入二进制数据并自动创建父目录。 |
| `atomic_write_text(path, content)` | 以 UTF-8 写入文本，保留调用方传入的换行。 |
| `sha256_bytes(content)` | 对已有字节计算 SHA-256 十六进制摘要。 |
| `sha256_file(path)` | 流式计算文件摘要，适用于大文件。 |

原子替换保证正式路径的可见性。文件内容会在替换前同步，父目录元数据没有额外同步，因此突然断电后的持久性仍取决于操作系统和文件系统。同一路径有多个写入者时，以最后一次成功替换的内容为准，调用方需要自行协调写入顺序。
