# SealBox 封印盒

用一次性 UUID 密码把文件 / 文件夹加密成 **7z / ZIP / 自解压程序**，同时生成一份写明密码与校验信息的 TXT。
带窗口、拖拽、系统托盘、开机自启动、右键菜单和压缩记录。

> 📘 图文版使用说明书：[docs/manual.pdf](docs/manual.pdf) · [HTML 源](docs/manual.html)

```
文件 / 文件夹 ──拖入──▶ 一次性 UUID 密码 ──▶ report.zip（AES-256，默认） + report.密码.txt
                                        ├─▶ report.7z（文件名也加密）
                                        └─▶ report.exe / report.command（自解压）
```

## 功能

| 功能 | 说明 |
|------|------|
| 密码 | `uuid4` 生成，**默认 22 位短 UUID**（Base57，大小写混合，约 122 bit）；加密时不可手动指定，解压/校验才需要输入密码 |
| 7z | AES-256 + `-mhe=on`，**文件名也加密**，没有密码连文件列表都读不出 |
| ZIP | **默认格式**；AES-256 加密内容；受 ZIP 规范限制，**文件名无法加密** |
| 自解压 | Windows 生成 `.exe`（`7z.sfx`）；macOS/Linux 生成 `.command` / `.run`（shell 自解压） |
| 密码 TXT | `<名称>.密码.txt`：密码、格式、大小、SHA-256、解压命令、安全提示 |
| 压缩记录 | `history.jsonl`，可查看原名 → 包名、密码、大小，支持复制/导出 CSV |
| 完成弹窗 | 列出加密包、密码、TXT 路径，一键复制密码 / 打开目录 |
| 拖到程序图标 | 把文件拖到 exe / 快捷方式上，程序自动打开并预置任务；压缩包自动进入解压页 |
| 右键菜单 | Windows 文件/文件夹/空白处单层入口（打开窗口选格式）；macOS Quick Action；Linux 文件管理器脚本 |
| 系统托盘 | 关闭最小化到托盘；托盘菜单显示主窗 / 退出 |
| 开机自启动 | Windows 登录项 / macOS LaunchAgent / Linux autostart，自启时静默驻留托盘 |
| 单实例 | 全局命名管道（按用户）只允许一个实例；第二次启动会把任务投递给已开窗口并唤醒，不重复开进程 |

## 快速开始

依赖：Python 3.10+、7-Zip（Windows 装 7-Zip，macOS `brew install sevenzip`，Linux 安装 7zip）、PySide6。

```powershell
# 源码运行（无需安装）
python sealbox_gui.py                # 打开窗口
python sealbox_gui.py 报告.docx      # 打开并预置文件
python sealbox_gui.py 资料\          # 预置文件夹

# 命令行（无窗口）
$env:PYTHONPATH = "src"
python -m sealbox --seal --cli 报告.docx
python -m sealbox --seal --cli --format all 资料\
python -m sealbox --extract --cli 报告.7z --out 输出\
python -m sealbox --verify --cli 报告.7z --pwd <密码>
```

## 右键菜单 / 自启动

```powershell
python -m sealbox --install-menu      # Windows：HKCU 注册，免管理员
python -m sealbox --uninstall-menu
python -m sealbox --autostart enable  # 开机自启动（托盘模式）
python -m sealbox --autostart status
python -m sealbox --autostart disable
```

- Windows：文件、文件夹、文件夹空白处 →「SealBox 封印盒」，子菜单可选 7z / ZIP / 自解压 / 全部。
- 右键菜单只做注册/移除，不改动任何快捷方式。
- macOS：安装 Finder 快速操作（`~/Library/Services`），首次需在「系统设置 → 键盘 → 服务」勾选。**未在实机验证**。
- Linux：写入 Nautilus / Nemo / Caja 的 scripts 目录。

## 开发

```
src/sealbox/
  core/      password / sevenzip / job / sfx / verifier / manifest / history
  platform_/ win/shellmenu · mac/services · linux/filemanager · autostart
  gui/       app（主窗 + 托盘）/ dropzone / ipc / theme
tests/       unittest（含真实 7z 回环）
```

```powershell
$env:PYTHONPATH = "src"
python -m unittest discover -s tests -v
python -m compileall -q src
```

打包（建议）：PyInstaller onedir + Inno Setup（Windows）／`.app` + ad-hoc 签名 + DMG（macOS）。

## 安全边界（务必阅读）

1. **密码 TXT 与加密包放同一目录 = 没有加密**。请分渠道发送；界面里可关闭 TXT 写入，只复制密码。
2. **ZIP 藏不住文件名**；需要完整保护请用 7z。
3. 压缩记录与密码 TXT 都含明文密码，仅存本机；macOS/Linux 下权限 600，Windows 依赖用户目录权限。
4. 7z 的密码走命令行参数，本机同用户进程理论上可读取；本工具不在日志里记录密码。
5. 未签名的自解压 `.exe` 可能触发 SmartScreen / 杀软提示；macOS 首次运行需右键打开。

## 微信 / 企业微信

桌面端没有「发送前回调」的官方接口，无法在点发送的瞬间无感拦截。可行替代：

- **复制文件 → 托盘提示 → 一键加密并把包放回剪贴板**，再到聊天窗口粘贴（跨微信/企微/QQ/邮件）。
- 把文件拖到 SealBox 窗口 / 右键菜单，先加密再发送。
- 自动化发送（UIA 操作聊天窗口）属于可选实验项，需评估风控与版本兼容。

## 平台状态

| 平台 | 状态 |
|------|------|
| Windows 10/11 | 本机 + CI 实测：三格式加密/解密回环、SFX exe、GUI、托盘、右键菜单、自启动、记录 |
| macOS | CI（macos-latest / arm64）构建通过；产物已下载并校验（Mach-O arm64、内置 7zz）；**未在实机运行验证** |
| Linux | CI（ubuntu-22.04 / x64）构建通过；产物已下载并校验（ELF x64、内置 7zz）；**未在实机运行验证** |

## 打包

PyInstaller 不支持交叉编译：**在哪个系统构建，就得到哪个系统的产物**。三套入口已就绪，产物统一为目录版（onedir，启动无需解包）：

```powershell
# Windows（出 dist\SealBox\、dist\SealBoxCLI\、dist\SealBox-win64.zip）
packaging\build_win.cmd
# 或
python packaging\build.py
```

```bash
# macOS（出 dist/SealBox.app、dist/SealBoxCLI/、dist/SealBox-macos.zip）
bash packaging/build_mac.sh

# Linux（出 dist/SealBox/、dist/SealBoxCLI/、dist/SealBox-linux-x64.zip）
bash packaging/build_linux.sh
```

- 构建前 `packaging/build.py` 会把当前平台的 7-Zip 复制进 `_vendor/7z`，产物自带压缩内核，目标机器无需再装 7-Zip。
- GUI 与 CLI 都是目录版：`SealBox/SealBox.exe + _internal/`，**`_internal` 不能删**。
- 便携 zip 由构建脚本自动生成；macOS 额外生成 ad-hoc 签名的 `.app`。
- 云端三平台：`.github/workflows/build.yml`（windows-latest / macos-14 / ubuntu-22.04）矩阵构建并上传 artifact。
- 体积：目录约 120 MB（PySide6 占大头），zip 约 97 MB；启动约 1 秒内。

### 产物说明

- `dist/SealBox/SealBox.exe`：窗口版（无控制台），右键菜单、开机自启动都指向它。
- `dist/SealBoxCLI/SealBoxCLI.exe`：控制台版，终端里跑 `--seal --cli` / `--extract --cli` / `--verify --cli`。
- `dist/SealBox-win64.zip`：上述两个目录，解压即用。
- `dist/SHA256SUMS.txt`：校验和。
- macOS / Linux：同结构；macOS 用 `SealBox.app`，由本机脚本或 CI 构建。
