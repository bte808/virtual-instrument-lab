# Virtual Instrument Lab · 虚拟仪器实验台

[![Numerical and export tests](https://github.com/bte808/virtual-instrument-lab/actions/workflows/tests.yml/badge.svg)](https://github.com/bte808/virtual-instrument-lab/actions/workflows/tests.yml)

面向测控学生的离线信号与双相锁相检测实验台。用可复现的合成信号观察噪声、滤波、频谱和锁相检测的关系。

**全部数据均为合成仿真数据（SYNTHETIC SIMULATION DATA）。本项目没有硬件连接，也不提供真实测量、标定或认证结果。** 运行时不需要账号、网络或付费服务；首次安装依赖需要网络，或使用预先下载的依赖包。

![Clean reference 预设：合成信号、因果滤波与锁相启动过程](docs/images/clean-reference.png)

## 功能

- 正弦信号、直流偏置、指定 seed 的高斯噪声和单频干扰。
- 因果低通滤波、时域曲线和单边峰值幅度谱。
- 双相锁相检测的 X/Y、峰值幅值和相位，显示启动瞬态与未充分稳定提示。
- 三组教学预设，以及 CSV、JSON 设置、PNG 图像导出。
- Tkinter 图形界面与独立 NumPy/SciPy 数值核心；也可无界面批量导出。

## 安装与启动

建议使用 **Python 3.11 或 3.12，带 Tk 8.6 或更新版本**。源码要求 Python ≥ 3.9；自动化测试矩阵覆盖 Python 3.11/3.12。先安装现代 CPython 与 Git，或下载仓库 ZIP 后在解压目录运行对应命令。每个项目使用自己的 `.venv`。

### Windows · PowerShell

```powershell
git clone https://github.com/bte808/virtual-instrument-lab.git
cd virtual-instrument-lab
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m tkinter
.\.venv\Scripts\python.exe -m virtual_instrument_lab
```

`-m tkinter` 应打开 Tk 测试窗口，关闭后再启动实验台。使用 Python 3.11 时把第一条 Python 命令中的 `-3.12` 改成 `-3.11`。若 `py` 不可用，可改用已安装的 `python`。直接调用虚拟环境中的 Python，无需修改 PowerShell 执行策略。

### macOS · Terminal

```bash
git clone https://github.com/bte808/virtual-instrument-lab.git
cd virtual-instrument-lab
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m tkinter
.venv/bin/python -m virtual_instrument_lab
```

如果安装的是 Python 3.11，请使用 `python3.11` 创建环境。确认该 Python 提供 Tk 8.6 或更新版本；缺少 `_tkinter` 时应安装带 Tk 支持的 Python，或为所用 Python 发行版安装匹配的 Tk 支持，然后重新创建虚拟环境。无界面导出不依赖 Tk。

本机 macOS 已使用隔离环境中的 **Python 3.12.15 / Tk 9.0.4** 完成原生 Tk 窗口创建、更新与关闭检查。系统 Python 3.9 / Tk 8.5 的窗口检查在本机挂起，该组合不作为本项目支持的 GUI 运行环境；请使用上述现代 Python/Tk 环境。

### 第一次实验

1. 选择 `Clean reference` 预设并运行，观察输入信号与 X/Y 启动过程。
2. 对照结果区的峰值幅值、相位和稳定状态；零信号的相位应显示为未定义。
3. 修改噪声与干扰，再运行并比较时域、频域和锁相曲线。
4. 用界面按钮导出 CSV、保存/载入 JSON 设置、导出 PNG。

具体操作与预期现象见 [三组教学实验](docs/experiments.md)。

## 无界面导出与测试

以下命令使用 macOS 的虚拟环境路径；Windows 请把 `.venv/bin/python` 替换为 `.\.venv\Scripts\python.exe`。

```bash
.venv/bin/python -m virtual_instrument_lab --headless --preset 'Clean reference' --output-dir output
.venv/bin/python -m pytest tests -m 'not gui'
.venv/bin/python -m virtual_instrument_lab --smoke-test
```

无界面模式在 `output` 中生成 CSV、JSON 设置和 PNG。CSV 保留时域采样及仿真元数据；JSON 用于恢复参数，PNG 用于教学报告。图形界面的 `--smoke-test` 需要真实桌面和可用的 Tk，会运行三组预设并检查无效输入后的恢复流程。它是自动化基本流程检查，不能代替人工检查窗口缩放、字体与文件对话框。

[GitHub Actions](https://github.com/bte808/virtual-instrument-lab/actions) 配置为在 Windows/macOS、Python 3.11/3.12 上运行数值与导出测试，并执行无界面示例导出。Windows 作业还设置 `VIL_RUN_GUI_TESTS=1` 运行 Tk 回调基本流程测试，涵盖预设、输入错误恢复、未定义相位、导出、设置回读与取消对话框。**配置存在不等于测试已经通过；以对应提交的 Actions 结果为准。** Windows GUI 的人工检查尚未完成，自动化回调测试不验证所有窗口布局、字体、缩放或原生文件对话框；也不能用 macOS 结果作为 Windows GUI 验证。

## 数值约定

输入主信号为 `A cos(2π f t + φ)`，`A` 为**峰值**，不是 RMS，也不是峰峰值；直流、干扰和高斯噪声叠加得到模拟输入。参考相位为 0°，双相锁相使用原始模拟输入：

```text
X = LP₂( 2 x cos(2π f_ref t))
Y = LP₂(-2 x sin(2π f_ref t))
R = hypot(mean(X), mean(Y))
φ = atan2(mean(Y), mean(X))
```

`LP₂` 是两级因果 RC 低通。频率匹配并充分稳定时，`R` 估计输入主信号的峰值，正相位对应输入相对参考的正相位。零/近零幅值的相位未定义。输入低通为单级，锁相路径始终从原始输入混频。

采样为 `N = round(fs × duration)`、`t = arange(N)/fs`，不重复终点。FFT 使用矩形窗；单边谱只将非 DC、非偶数样本 Nyquist 的频点加倍。非整周期记录会产生频谱泄漏，不能把任意最高谱线直接当作精确幅值。

所有滤波器从零状态启动，不消除启动瞬态。图中保留瞬态并标记保守稳定时间；参考频率不匹配、有限记录、噪声或过宽带宽都会影响估计。稳定标记是启动条件，不是测量准确度承诺。完整约定、限制和练习见 [实验说明](docs/experiments.md)。

## 项目结构

```text
virtual_instrument_lab/
  core.py        # 参数校验、仿真、滤波、频谱、锁相
  exports.py     # CSV / JSON / PNG
  plotting.py    # 绘图，与 Tk 界面分离
  app.py         # Tkinter 界面
  __main__.py    # 图形 / 无界面 / smoke-test 入口
tests/           # 数值、导出与界面基本流程检查
docs/            # 教学实验与实现约定
```

不包含硬件驱动、云端服务或预编译可执行程序。Windows 和 macOS 都从源码安装启动；若以后提供可执行程序，应分别在目标系统构建和验证。

## 本机验证记录

在实际 macOS 上，Python 3.9.6 与隔离的 Python 3.12.15 均通过 **93 项数值/导出测试**。Python 3.12.15 / Tk 9.0.4 的完整 GUI smoke 通过三组预设切换、错误输入恢复、零信号未定义相位、CSV/PNG 导出、JSON 设置回读和取消对话框流程。测试使用临时文件及模拟的文件对话框，没有连接硬件。

`Clean reference` 的无界面运行得到 `0.999986 V peak`、`29.999991°`（设定为 `1 V peak`、`30°`），保留启动过程并输出 CSV/JSON/PNG；示例图已检查布局。Windows 的数值、导出及自动 GUI smoke 结果以各提交的 Actions 记录为准；Windows 窗口外观、高 DPI 与原生文件对话框尚未人工检查。

## License

[MIT](LICENSE) · Copyright © 2026 bte808.
