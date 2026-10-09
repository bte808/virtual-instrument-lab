Virtual Instrument Lab / 虚拟仪器实验台
Repository: https://github.com/bte808/virtual-instrument-lab

SYNTHETIC SIMULATION DATA. NO HARDWARE CONNECTED.
全部数据均为合成仿真数据，没有硬件连接；不代表真实测量、标定或认证。

This portable application includes Python and its runtime dependencies.
No separate Python installation, account, network or paid service is required
to run it. Keep the entire application directory or .app bundle together.

本便携程序自带 Python 与运行依赖。运行时无需另行安装 Python、登录账号、
联网或使用付费服务。必须保留整个程序目录或 .app 包，不能只复制可执行文件。

CHECK BEFORE RUNNING / 运行前核对
- Download the artifact from the intended repository Actions run and commit.
- Check that the target-platform build and self-test succeeded.
- Compare the archive SHA-256 with SHA256SUMS.txt.
- Read BUILD_INFO.json for the build environment and commit.
- Read SELF_TEST.json for that bundle's actual checks and results.
- Configuration alone is not evidence that a build or test passed.

核对来源仓库、Actions 运行及提交；确认对应平台构建和自测通过；核对压缩包
SHA-256，并阅读 BUILD_INFO.json 与 SELF_TEST.json。哈希不等于发布者身份签名。

WINDOWS X64
Extract the full archive, then double-click VirtualInstrumentLab.exe.
Keep every support file and directory beside the executable.
For command-line use, open PowerShell in the executable's directory:

  .\VirtualInstrumentLab.exe --headless --preset "Clean reference" --output-dir ".\Synthetic output"
  .\VirtualInstrumentLab.exe --smoke-test

The application hides only a console it owns when launched separately; an
existing PowerShell or command prompt stays available for CLI output.

Windows x64：完整解压后双击 VirtualInstrumentLab.exe；所有依赖目录需保持完整。
双击启动时隐藏程序自己创建的控制台；从已有终端运行时保留命令行输出。

MACOS ARM64 / APPLE SILICON
Extract the tar.gz archive, then open VirtualInstrumentLab.app in Finder.
Keep the complete .app bundle intact. For CLI use, in the .app's parent folder:

  ./VirtualInstrumentLab.app/Contents/MacOS/VirtualInstrumentLab --headless --preset "Clean reference" --output-dir "./Synthetic output"
  ./VirtualInstrumentLab.app/Contents/MacOS/VirtualInstrumentLab --smoke-test

macOS arm64：完整解压后在 Finder 中打开 VirtualInstrumentLab.app。
此便携包面向 Apple silicon；Intel Mac 请使用源码安装方式。

EXPORTS AND CHECKS / 导出与检查
Headless mode exports synthetic CSV data, JSON settings and a PNG figure.
Choose a writable output directory. The smoke test needs a graphical desktop;
it exercises basic callbacks and exits. Automated checks do not replace manual
checks of window layout, display scaling, fonts and native file dialogs.
Manual Windows GUI checks have not been completed.

无界面模式导出合成 CSV 数据、JSON 设置与 PNG 图像，请使用可写的输出目录。
smoke-test 需要图形桌面，执行基本回调后退出。Windows 界面外观、高 DPI、字体
与原生文件对话框尚未人工检查；自动化通过不等于这些检查已完成。

SIGNING / 签名
Windows: unsigned; no publisher certificate.
macOS: ad-hoc signature only; no Developer ID signature or notarization.
If the operating system blocks execution, use the reviewed source installation
documented in the repository. Do not disable security protections or bypass
system warnings. No administrator privileges or paid certificate are required
by this project.

Windows 未使用发布者证书签名；macOS 仅为 ad-hoc 签名，没有 Developer ID 或公证。
若系统阻止运行，请使用审阅后的源码安装方式；不要关闭安全保护或绕过系统警告。

DISTRIBUTION / 分发
These are GitHub Actions artifacts, not a GitHub Release. Artifact downloads
require GitHub login and expire after the configured 14-day retention period.
Windows and macOS bundles are built and checked on their own target systems.
A macOS result is not Windows validation.

本产物为 GitHub Actions artifact，并非 GitHub Release；下载需要 GitHub 登录，
保留期为 14 天。两种系统分别构建验证，不能将 Mac 结果当作 Windows 验证。

More details / 完整说明:
https://github.com/bte808/virtual-instrument-lab/blob/main/docs/portable.md

Project code: MIT License, copyright 2026 bte808.
Bundled Python and third-party libraries retain their own license terms.
