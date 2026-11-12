# SealBox（封印盒）实施计划

> 版本：v0.1 计划稿 · 2026-11-12 · 状态：待主人确认后开工
> 一句话：把文件/文件夹拖进窗口（或右键菜单），用一次性 UUID 密码加密成 `.7z` / `.zip` / 自解压程序，同时输出一份写明密码与校验信息的 TXT。

---

## 1. 需求拆解与验收标准

| # | 需求 | 实现方式 | 验收标准 |
|---|------|----------|----------|
| R1 | 生成不可重复密码 | `uuid.uuid4()`（122 bit 熵），可配置三种形态 | 连续生成 10 万个无重复；格式断言通过 |
| R2 | 用该密码加密文件 | 调 7-Zip 24.09：7z 用 AES-256 + `-mhe=on` | 错误密码解压失败，正确密码逐文件 SHA-256 一致 |
| R3 | 输出加密包 + 密码 TXT | 同名 `.txt`，含密码/格式/SHA-256/解压命令 | 两文件同时产出，TXT 字段齐全可机读（Key: Value） |
| R4 | 多种格式 | `.7z`、`.zip`（AES-256）、自解压（Win `.exe` / macOS `.command` / Linux `.run`） | 每格式在 Win 实机验证；mac 逻辑层单测 + 待实机 |
| R5 | 右键菜单 | Win：HKCU 注册表 + SendTo；mac：NSServices（Finder 右键→服务/快速操作） | 注册/注销无残留；单选、文件夹、空白处三种入口可用 |
| R6 | 有窗口、可拖拽 | PySide6 主窗：拖拽区 + 队列 + 进度 + 密码面板 | 拖入混合文件/文件夹即入队，进度与日志实时 |
| R7 | 跨平台（含 macOS，无移动端） | 纯 Python + Qt，路径/命令/菜单全部分平台适配 | Win 实跑；mac 由 CI 或实机跑通冒烟 |
| R8 | 不误伤 | 默认不覆盖已有文件、失败自动清理半成品、日志脱敏 | 断点/异常注入测试无残留损坏包 |

---

## 2. 技术选型

| 层 | 选择 | 理由 |
|----|------|------|
| 语言/运行时 | Python 3.13.5（本机已装） | 单代码库覆盖三平台，开发与验证快 |
| GUI | PySide6 6.11.1（Qt 6，本机已装） | 原生拖拽、跨平台、打包成熟；与现有 Qt 技术栈一致 |
| 压缩内核 | 外部 7-Zip 24.09（`C:\Program Files\7-Zip\7z.exe`，含 `7z.sfx` / `7zCon.sfx`） | 与官方算法完全一致、可复现；避免自实现 AES/容器格式 |
| Windows 打包 | PyInstaller（onedir）+ Inno Setup 安装器 | 安装/卸载时顺带注册/清理右键菜单 |
| macOS 打包 | PyInstaller → `.app` → ad-hoc `codesign` → DMG | 先解决"能跑"；公证（$99/年）按需再谈 |
| 测试 | pytest + pytest-qt + 真实 7z 回环 | 核心逻辑单测，格式/加密必须真跑 |

**不选**：Tauri/Electron（体积大、右键菜单仍要原生代码）；.NET/Avalonia（Win 最强但 mac 打包链路更重）；自己调 lib7z（版本与 ABI 麻烦）。

---

## 3. 核心设计

### 3.1 密码生成（`core/password.py`）

- 基础：`uuid4()`，三种形态：
  - `hex32`：`3f2a9c4e8b1d47f6a05c2e9d7b3f1a8c`（默认，好粘贴、无歧义字符）
  - `uuid`：`3f2a9c4e-8b1d-47f6-a05c-2e9d7b3f1a8c`（可读，按 UUID 规范）
  - `uuid+rand`：UUID 前缀 + 32 位 `secrets.token_hex(16)`（≈250 bit，给"特别怕撞"的场合）
- 只用 ASCII：7z 命令行/密码文件/跨平台编码全部安全。
- 每次任务独立生成，绝不复用；同一任务多格式共用同一密码（主人可关）。
- 生成记录进任务对象（不落日志明文）。

### 3.2 三种输出格式（`core/sevenzip.py`）

| 模式 | 命令要点 | 保护范围 | 说明 |
|------|----------|----------|------|
| 7z | `-t7z -m0=lzma2 -mx=9 -mhe=on -p<pw>` | **内容 + 文件名** | 推荐默认，头加密后连文件列表都看不到 |
| zip | `-tzip -mem=AES256 -mx=9 -p<pw>` | 仅内容 | ZIP 规范**无法加密文件名**，UI/文档必须明示；另留 ZipCrypto 兼容开关（默认关，标注不安全） |
| SFX | 见 3.3 | 同 7z | 双击即解，接收方无需装 7z |

- 输出到用户指定目录，默认与原文件同级；重名自动加 ` (2)`，**不覆盖**。
- 支持"一次全出"：同密码同时生成 7z + zip + SFX。
- 进度：解析 7z stdout 的百分比/文件计数，映射到队列进度条。

### 3.3 自解压（跨平台差异，`core/sfx.py`）

- **Windows**：`7z a -sfx7z.sfx -mhe=on -p<pw> out.exe <items>` → `7z.sfx` 拼接载荷。
  - 默认 GUI 版 `7z.sfx`；提供 `7zCon.sfx`（控制台）选项。
  - 注意：未签名 exe 可能触发 SmartScreen/杀软误报，README 写明。
- **macOS**：7-Zip 无 SFX 模块。方案：生成 `xxx.command` 自解压脚本
  - 结构：`#!/bin/bash` 头 + 载荷定位（标记行 + `tail -c`）+ 落地到临时 `.7z` + 调 `7zz x -p...`
  - 两种变体：`light`（要求系统有 `7zz`，`brew install sevenzip`，包小）/ `fat`（内嵌 universal `7zz`，+约 8 MB，离线可用）
  - 首次运行需 `chmod +x`（脚本内自检）与 Gatekeeper"右键→打开"，UI 给提示。
- **Linux**：同 mac，产物 `xxx.run`，检测 `7zz`/`7z`/`7za`。

### 3.4 生成后自校验（`core/verifier.py`）

- 立刻 `7z t -p<pw>` 校验包可解密、条目数一致；SFX 先剥壳再测。
- TXT 写入 `SHA-256`（包）与条目清单摘要，事后可复核。
- 失败 → 删除半成品、任务标红、保留 7z stderr 摘要（脱敏后）。

### 3.5 密码 TXT 模板

```
========================================
 SealBox 加密包信息
========================================
文件      : report.7z
生成时间  : 2026-11-12 08:40:12 +08:00
格式      : 7z (AES-256, 文件名加密: 是)
密码      : 3f2a9c4e8b1d47f6a05c2e9d7b3f1a8c
SHA-256   : 9c1f...（64 位）
大小      : 12,345,678 字节 / 12 条目
解压命令  : 7z x -p"密码" report.7z
安全提示  : 密码与压缩包请分渠道发送；同目录保存等于未加密
```

### 3.6 安全边界（必须写进 README）

- 密码 TXT 与包同目录 = 拿到包就拿到密码；工具会提示，并提供"不落盘/只在界面显示/复制到剪贴板"三种策略（默认仍按主人要求落盘）。
- 日志不记录密码；异常堆栈过滤；TXT 在 mac/Linux 设 `chmod 600`。
- UUID 122 bit 熵对"防暴力破解"足够，但格式固定会降低离线猜测空间 → 大量/高价值数据建议 `uuid+rand` 模式。
- 加密强度取决于口令与 7z 的 KDF（7z 迭代 SHA-256，24.09 足够），不额外自研加密。

---

## 4. 右键菜单

### 4.1 Windows（免管理员，全部 HKCU）

| 位置 | 注册表键 | 作用 |
|------|----------|------|
| 文件 | `HKCU\Software\Classes\*\shell\SealBox` | 选中文件 → 加密 |
| 文件夹 | `HKCU\Software\Classes\Directory\shell\SealBox` | 选中文件夹 → 加密 |
| 文件夹空白处 | `HKCU\Software\Classes\Directory\Background\shell\SealBox` | 当前目录整体加密 |

- 用 `MUIVerb` + `SubCommands`（`ExtendedSubCommandsKey`）做子菜单：`加密为 7z` / `加密为 ZIP` / `生成自解压` / `三种都要`；图标用 `Icon`。
- 命令：`"...\SealBox.exe" --seal "%1" --format 7z --out "%w"`（背景用 `%V`）。
- **多选**：注册表 verb 对多选是"每项各调一次"。真正"多选→一个包"两条路：
  1. `SendTo` 快捷方式（资源管理器把**全部选中项**作为参数传入）→ 阶段 3b 实现，零 COM；
  2. 轻量 COM `IContextMenu` 扩展（ATL/C#）→ 阶段 3c 可选，能带进度与单选菜单。
- 安装/卸载：写前导出 `.reg` 备份；"移除右键菜单"按钮清空 `...\shell\SealBox*`；卸载器同逻辑。

### 4.2 macOS

- 主方案：`.app` 的 `Info.plist` 声明 `NSServices`（`NSMenuItem`、`NSRequiredContext` = 文件/文件夹 URL、`NSSendFileTypes`），安装后出现在 Finder 右键 →「服务 / 快速操作」，且**一次可接收多选**。
- 备选：生成 `.workflow` 快速操作装到 `~/Library/Services`（双击即装，兼容老系统）。
- 首次需在「系统设置 → 键盘 → 服务」勾选；安装脚本尝试用 `defaults` 自动启用，失败则给图文提示。
- 未签名/未公证时 Finder 可能拦首次调用，README 给 `xattr -d com.apple.quarantine` 与右键打开说明。

### 4.3 Linux（附带）

- Nautilus/Nemo 脚本：`~/.local/share/nautilus/scripts/SealBox`（可执行 shell），作为加分项，非本期验收重点。

---

## 5. GUI 与 CLI

### 5.1 主窗口（`gui/`）

- 拖拽区（文件/文件夹混合，可多次追加）＋"选择文件/文件夹"按钮。
- 格式勾选（7z / zip / SFX，可多选）、输出目录、密码形态下拉、TXT 开关。
- 密码卡片：显示、复制、重新生成、"不落盘"开关。
- 队列：名称、大小、格式、状态、进度；支持取消/重试/清空。
- 结果区：打开输出目录、复制密码、查看 TXT、删除 TXT。
- 设置页：右键菜单安装/卸载、默认格式、7z 路径探测、日志级别。
- 单实例：`QLocalServer`（跨平台），右键菜单再次调用时把任务投递给已开窗口并置前，不新开进程。

### 5.2 CLI（同一入口，`sealbox --help`）

```
sealbox --seal <path> [<path>...] [--format 7z|zip|sfx|all]
        [--out DIR] [--password auto|<literal>] [--password-file auto|none|PATH]
        [--sfx-kind gui|console] [--no-verify] [--json]
sealbox --install-menu [--scope user] / --uninstall-menu
sealbox --verify <archive> --password-file <txt>
sealbox --extract <archive> --password-file <txt> --out DIR
sealbox --gui            # 默认
```

- `--json` 输出机器可读结果，便于脚本与自动化测试。
- 退出码：0 成功、1 用法/参数、2 7z 缺失、3 加密失败、4 校验失败。

---

## 6. 目录结构

```
sealbox/
├─ pyproject.toml
├─ README.md              # 用法、安全边界、平台差异
├─ docs/PLAN.md           # 本文件
├─ src/sealbox/
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ core/
│  │  ├─ password.py      # UUID 密码
│  │  ├─ job.py           # 任务模型/队列/取消
│  │  ├─ sevenzip.py      # 命令构造/执行/进度/探测
│  │  ├─ sfx.py           # exe/command/run 自解压
│  │  ├─ verifier.py      # 7z t 校验 + 哈希
│  │  └─ manifest.py      # TXT 生成
│  ├─ platform_/
│  │  ├─ win/shellmenu.py
│  │  ├─ mac/services.py
│  │  └─ linux/scripts.py
│  └─ gui/
│     ├─ app.py  dropzone.py  queueview.py  ipc.py  settings.py
├─ tests/
│  ├─ test_password.py  test_commands.py  test_manifest.py
│  ├─ test_roundtrip.py   # 真实 7z 回环（含中文名/空格/深路径/大文件）
│  └─ test_sfx.py  test_menu_registry.py（Win）
└─ packaging/
   ├─ win/pyinstaller.spec  win/inno.iss
   └─ mac/build_app.sh  mac/Info.plist  mac/entitlements.plist
```

---

## 7. 里程碑

| 阶段 | 内容 | 产出 | 预估 |
|------|------|------|------|
| M0 | 方案确认（本文件）+ 骨架/依赖 | 目录、pyproject、CI 脚本草稿 | 0.5h |
| M1 | 核心引擎 + CLI：密码、三种格式、SFX（Win 实跑 / mac 脚本）、校验、TXT | `sealbox --seal` 可用，pytest 全绿，真实回环通过 | 2–3h |
| M2 | GUI：拖拽、队列、进度、单实例 IPC | 窗口可日常使用 | 2h |
| M3 | Windows 右键菜单：注册表三处 + 子菜单 + SendTo 多选 + 安装/卸载 | 资源管理器右键可用，注册表无残留 | 1.5h |
| M4 | macOS 适配与打包：NSServices、`7zz` 定位、`.app` + ad-hoc 签名 + DMG、`.command` SFX 实跑 | mac 冒烟通过（**需实机或 CI**） | 2–3h |
| M5 | 安装包、自检、README、样本产物 | Win 安装器 + DMG + 演示包 | 1.5h |

依赖关系：M1 → M2 → M3；M4 依赖 M1（SFX 脚本）与 M5 的打包脚本；M3/M4 可并行。

---

## 8. 测试计划

1. **单元**：密码唯一性/格式/熵估计；命令参数快照（每格式）；TXT 字段；路径转义（空格、`&`、中文、emoji、超长）；7z 探测失败路径。
2. **回环（关键）**：临时树 → 三格式加密 → 用密码解压 → 逐文件 SHA-256 对比；错误密码必须失败；`zip` 断言"文件名可见"提示正确；`-mhe=on` 断言列表不可读。
3. **边界**：空文件夹、只读文件、1 GB 级文件（流式+进度）、同名冲突、任务取消、磁盘满（模拟）。
4. **GUI**：pytest-qt 冒烟（投递拖拽事件、队列状态机）；人工检查拖拽与视觉。
5. **右键菜单**：`reg query` 断言键值；点击走 `ui_map`/`ui_click` 自动化或人工；卸载后断言零残留。
6. **跨平台**：本机 Win 全量；mac 逻辑用单测 + GitHub Actions `macos-14` 跑 `test_roundtrip` / `test_sfx`（如需仓库）。

---

## 9. 风险与待确认

| 风险 | 影响 | 应对 |
|------|------|------|
| 本机无 macOS 实机 | M4 无法"真跑真验" | 主人提供实机/远程 mac，或接受 CI 验证 + 逻辑单测；Finder 集成标注"待实机确认" |
| ZIP 不能加密文件名 | 安全预期落差 | UI 显式提示 + 默认推荐 7z；文档写明 |
| SFX exe 被杀软/SmartScreen 拦 | 收件方体验 | 文档说明；可选提供 7z 包 + 批处理解压替代 |
| macOS Gatekeeper/签名 | 首次运行被拦 | ad-hoc 签名 + 文档；公证需 Apple 开发者账号 |
| 右键多选（Win 注册表限制） | 多选只能逐项/走 SendTo | 阶段 3b SendTo 兜底，3c 可选 COM |
| 7z 版本差异（mac 24.09/`7zz`） | 参数兼容 | 启动时探测版本；不支持的参数降级并提示 |

**待主人确认**：技术栈、项目名与落盘位置、密码默认形态、mac 验证条件、是否要 Linux 入口。

---

## 10. 追加需求落地（2026-11-12 已实现）

| 需求 | 实现 | 验证 |
|------|------|------|
| 现代化界面 | PySide6 卡片式浅色主题、分段页签、chips、圆角按钮、深色日志区 | 实机截图确认 |
| 系统托盘 | `QSystemTrayIcon`：显示主窗 / 退出，关闭最小化到托盘，完成气泡 | 托盘模式启动无主窗 |
| 开机自启动 | Win 登录项 / macOS LaunchAgent / Linux autostart；GUI 开关 + `--autostart` | Win enable/status/disable 实测 |
| 压缩记录 | `history.jsonl`：原名 → 包名、密码、大小、SHA-256、TXT 路径 | CLI 与 GUI 均可查看/复制/导出 |
| 完成弹窗 | 结果窗列出包名、密码、TXT，带复制与打开目录 | 实机截图确认 |
| 拖到程序图标 | argv 路径 → 预置任务；单实例投递；压缩包自动切解压页 | 用 `.7z` 启动实测 |
| 解压 / 校验 | 解压页 + 自动读取 `<名称>.密码.txt` | 实机截图 + 回环测试 |
| 右键菜单 | Win 三处入口 + 子菜单 + SendTo 多选 | 15 个键实测，卸载无残留 |

## 11. 微信 / 企业微信「发送前拦截」结论

**桌面端没有官方回调，做不到「用户点发送 → 无感拦截并替换」。**

- 个人微信 4.x（xwechat）与企业微信均未开放发送钩子；官方只有企业微信「会话内容存档」API，且是异步审计，不能阻断/替换。
- 理论上只有注入 DLL/内核驱动 hook 才能拦住发送，代价是：版本升级即失效、可能被杀软/风控判定外挂、违反用户协议、企业环境合规风险。
- 可落地的替代（推荐顺序）：
  1. **托盘剪贴板守门员**：复制文件后弹托盘提示 → 一键加密 → 加密包写回剪贴板 → 用户粘贴发送；覆盖微信/企微/QQ/邮件，零注入。
  2. **拖到 SealBox**：加密后自动复制到剪贴板并弹窗提示。
  3. **UIA 自动化发送**（可选实验）：定位聊天窗口自动粘贴发送，需微信 Qt gate，存在风控风险。
  4. **企微文件夹自动压缩**：只能在发送前用右键/SendTo 先替换成加密包，无法在其压缩瞬间介入。
