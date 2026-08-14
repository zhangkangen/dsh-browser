# dsh-browser

Windows 桌面容器：pywebview（WebView2/WinForms）内嵌 `@deepseek-ai/dsh` 的 Web UI。源码只有一个文件 `main.py`，无测试、无 lint。

## 运行时行为（main.py，改动前必读）

- 流程：找空闲端口 → 启动 `dsh web --port` → 轮询 HTTP 200 → WebView 加载 → 关窗后 `taskkill /PID /T /F` 杀掉整个进程树（防孤儿进程）。
- dsh 运行时解析优先级：exe/脚本同级的 `node/` → 环境变量 `DSH_BROWSER_NODE_DIR` → PATH 上的 `npx -y @deepseek-ai/dsh`。
- `env.pop("NODE_OPTIONS")` 是有意的：WorkBuddy 注入的 safe-delete shim 会拦截 dsh 的 trash 操作，不要删。
- 运行时需要一个完整 `node/` 目录（node.exe + node_modules，含 `@deepseek-ai/dsh/lib/bin.js`）。离线源在 `bundle/node/`，PyInstaller 产物不自动包含它。
- 单实例：main 开头 `CreateMutexW` 会话级互斥锁，已有实例时直接退出（main.py `acquire_single_instance`）。

## 开发

- `python main.py` 直接跑源码。依赖见 `requirements.txt`：`pywebview` + `pythonnet`（Windows 后端 winforms，必须）、`pyinstaller`。已验证 Python 3.14.2 可跑通。

## 构建（标准入口：build.ps1）

- `.\build.ps1` → `dist\dsh-browser\`；`.\build.ps1 -Installer` 追加 Inno 打包；`-InstallDeps` 先装依赖；`-Python xxx` 指定解释器。
- build.ps1 自动：杀残留 dsh-browser 进程（防 DLL 占用 PermissionError）→ 检查 webview/pythonnet → pyinstaller → 复制 `bundle\node\*` → 校验 node.exe + bin.js → 可选 iscc 打包。
- 脚本是纯英文：PowerShell 5.1 按 ANSI 解析无 BOM 的 UTF-8 文件，中文会乱码报错（已踩过）。
- 版本号单源 `version.txt`：spec 读它生成 exe 版本资源（`VSVersionInfo` 需从 `PyInstaller.utils.win32.versioninfo` 显式导入），build.ps1 用 `iscc /DMyAppVersion=` 传给 installer.iss。改版本只动 version.txt。

## 打包细节（手跑 pyinstaller 时）

- `pyinstaller dsh-browser.spec` → 输出 `dist\dsh-browser\`（exe + `_internal\`）。
- spec 中 `hiddenimports=['webview.platforms.winforms']` + `collect_all('pythonnet')` + `collect_all('clr_loader')` 缺一不可，少了 exe 启动即崩。
- 构建后必须把 `bundle\node\*` 复制到 `dist\dsh-browser\node\`，否则 exe 找不到 dsh 运行时。
- 已知坑：dist 目录里 DLL 被占用（程序在运行/残留进程）时构建报 PermissionError（曾卡在 libcrypto-3-x64.dll）。先杀掉残留进程再构建。
- warn 文件里的 missing module（System.*、Microsoft.Web 等 .NET 命名空间）是正常的，pythonnet 运行时解析，无需处理。
- `dist2\` 是实验输出（build2.log，无 node），不是发布产物；`installer.iss` 只认 `dist\`。

## 安装包

- `installer.iss`（Inno Setup 6）输入 `dist\dsh-browser\*`（含 node/），输出 `installer\dsh-browser-setup.exe`。若改用其他 distpath，必须同步改这里。