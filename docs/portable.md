# 便携包：下载、校验与启动

**所有数据均为合成仿真数据（SYNTHETIC SIMULATION DATA），没有硬件连接。** 便携包与源码版使用相同的数值约定和教学预设。程序运行不需要账号、网络、外部 Python 安装或付费服务。

便携包使用 PyInstaller 6.22.3，包含运行所需的 Python 与依赖。Windows 与 macOS 分别在对应操作系统上构建；Mac 产物不作为 Windows 构建或验证结果。PyInstaller 官方说明了其 [自包含打包与平台限制](https://pyinstaller.org/en/stable/operating-mode.html)。

## 产物与验证状态

| Actions artifact | 其中的程序压缩包 | 目标 | 启动入口 |
| --- | --- | --- | --- |
| `portable-windows-x64` | `portable-windows-x64.zip` | Windows x64 | `VirtualInstrumentLab.exe` |
| `portable-macos-arm64` | `portable-macos-arm64.tar.gz` | Apple silicon / macOS arm64 | `VirtualInstrumentLab.app` |

每份 artifact 还包括 `SHA256SUMS.txt`、`BUILD_INFO.json` 与 `SELF_TEST.json`。构建环境、提交与依赖信息看 `BUILD_INFO.json`；该包的自测结果看 `SELF_TEST.json`。当前不提供 Windows arm64 或 Intel Mac 的便携构建，也未验证所有操作系统版本。

程序压缩包解压后的顶层是 Windows 的 `VirtualInstrumentLab/` 文件夹，或 macOS 的 `VirtualInstrumentLab.app`，另附 `PORTABLE_README.txt`、`BUILD_INFO.json`、`LICENSE` 与 `THIRD_PARTY_LICENSES/`。Windows 的 EXE 位于 `VirtualInstrumentLab/` 内，与 `_internal/` 保持相对位置。`SELF_TEST.json` 放在待分发压缩包旁，而不写回已测试的压缩包。

构建流程配置为：分别使用 Windows x64 和 macOS arm64 runner 构建包，将压缩包解压到源码目录外、含空格与 Unicode 字符的临时目录，在隔离的 `PATH` 环境中启动包内程序，执行无界面导出和 Tk GUI 基本流程检查。这样检查的是移动后的打包程序，而不仅是源码环境中的 Python。

**配置不等于已通过验证。请检查所下载 artifact 对应提交的 Actions 状态及 `SELF_TEST.json`；不要把源码测试或另一操作系统的测试视为该包已通过。** 自动化 GUI 自测涉及预设切换、参数校验与导出等回调，不代表 Windows 窗口外观、高 DPI、所有字体或原生文件对话框已经人工检查。Windows GUI 人工检查尚未完成。

## 下载与核对

1. 登录 GitHub，进入项目 [Actions](https://github.com/bte808/virtual-instrument-lab/actions)，选择所需提交的便携构建运行。
2. 核对提交 SHA，并确认该平台的构建和自测成功，再在该运行的 Artifacts 区下载对应平台产物。
3. 解开 GitHub 下载的 artifact 外层 ZIP，得到上表中的程序压缩包与三个元数据文件。程序压缩包还需要单独解压。
4. 在该目录核对程序压缩包的 SHA-256。检查 `BUILD_INFO.json` 中的提交与所选运行一致，并阅读 `SELF_TEST.json`。

本项目将便携 artifacts 保留 **14 天**。过期后需要新的成功构建；它们不是永久下载链接，也没有自动发布为 GitHub Release。GitHub artifact 下载需要登录，参见 [GitHub 官方下载说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)。

Windows PowerShell 中显示待比较的校验值：

```powershell
Get-Content .\SHA256SUMS.txt
Get-FileHash .\portable-windows-x64.zip -Algorithm SHA256
```

确认 `Get-FileHash` 的 Hash 与 `SHA256SUMS.txt` 中该 ZIP 文件的值相同；字母大小写不影响比较。若不匹配，不要运行该文件，重新获取同一次成功构建的产物。

macOS Terminal 中校验：

```bash
shasum -a 256 -c SHA256SUMS.txt
```

校验值用来检查下载内容与所附清单是否一致，不是发布者身份签名。请同时核对仓库、Actions 运行和提交。

## Windows x64

在包含程序 ZIP 的目录运行：

```powershell
Expand-Archive -LiteralPath .\portable-windows-x64.zip -DestinationPath '.\Virtual Instrument Lab'
```

打开解压后的文件夹，找到并双击 `VirtualInstrumentLab.exe`。**保留整个 onedir 文件夹及其中的依赖目录，不能只复制 EXE。** 程序不需要另外安装 Python；用界面的导出按钮把结果保存到可写目录。

也可在 `VirtualInstrumentLab.exe` 所在目录运行 PowerShell：

```powershell
.\VirtualInstrumentLab.exe
.\VirtualInstrumentLab.exe --headless --preset 'Clean reference' --output-dir '.\Synthetic output'
.\VirtualInstrumentLab.exe --smoke-test
```

Windows 构建保留控制台命令行能力，并使用 `--hide-console hide-late`：双击时仅隐藏程序自己创建的控制台，从已有 PowerShell 或命令提示符启动时保留该控制台。具体含义见 [PyInstaller 的控制台选项](https://pyinstaller.org/en/stable/usage.html#windows-and-macos-specific-options)。

## macOS arm64

在包含程序压缩包的目录运行：

```bash
mkdir -p 'Virtual Instrument Lab'
tar -xzf portable-macos-arm64.tar.gz -C 'Virtual Instrument Lab'
```

在 Finder 中找到并双击 `VirtualInstrumentLab.app`。**保持整个 `.app` 包完整**，不要单独取出其中的可执行文件或依赖。此构建面向 Apple silicon（arm64）；Intel Mac 可使用 [源码安装](../README.md#macos--terminal)。

从 `.app` 所在目录启动命令行模式：

```bash
./VirtualInstrumentLab.app/Contents/MacOS/VirtualInstrumentLab --headless --preset 'Clean reference' --output-dir './Synthetic output'
./VirtualInstrumentLab.app/Contents/MacOS/VirtualInstrumentLab --smoke-test
```

`--smoke-test` 需要可用的图形桌面，会自动检查基本界面流程后退出。无界面导出会生成 CSV、JSON 设置和 PNG；所有输出仍应保留合成仿真标签。

## 签名与系统限制

Windows 包未使用发布者证书签名。macOS 包仅使用 ad-hoc 签名，没有 Apple Developer ID 签名，也没有经过公证；ad-hoc 签名不证明发布者身份。系统可能阻止这些包运行。

若系统阻止运行，请改用 [审阅后的源码安装方式](../README.md#源码环境)。本项目不提供关闭安全保护、移除隔离标记或绕过系统警告的操作步骤，也不要求管理员权限或购买证书。

## 在目标系统自行构建

构建需要 Python 与编译打包依赖，运行已构建好的包则不需要外部 Python。先按 README 创建独立 `.venv`，再安装构建依赖。macOS 示例：

```bash
.venv/bin/python -m pip install -e '.[build]'
.venv/bin/python scripts/build_portable.py
.venv/bin/python scripts/verify_portable.py --artifact-dir dist/artifacts
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[build]"
.\.venv\Scripts\python.exe scripts/build_portable.py
.\.venv\Scripts\python.exe scripts/verify_portable.py --artifact-dir dist/artifacts
```

`scripts/build_portable.py` 将本机系统的包与元数据写入 `dist/artifacts/`。`scripts/verify_portable.py` 将压缩包解压到源码目录外的临时目录进行验证，然后把 `SELF_TEST.json` 写在压缩包旁。验证 GUI 时需要可用的图形桌面；运行命令并不能替代检查退出状态与报告。其他参数可查看脚本 `--help` 和当前提交的 Actions 工作流。

Windows x64 必须在 Windows x64 环境构建；macOS arm64 必须在 macOS arm64 环境构建。CI 配置对应 `windows-latest` x64 与 `macos-14` arm64。构建及验证成功后再分发完整压缩包和元数据。

程序自身代码使用 [MIT License](../LICENSE)；包内 Python 与第三方依赖保留各自的许可证条件。
