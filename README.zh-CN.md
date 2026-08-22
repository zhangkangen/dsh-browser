# dsh-browser

Windows 桌面容器：用 pywebview（WebView2/WinForms）内嵌 [@deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) 的 Web UI，提供一个独立的 DeepSeek Harness 桌面应用。

[English](README.md) | **中文**

## 项目说明

### 特性

- 启动时自动寻找空闲端口，离线启动 `dsh web` 服务，就绪后在内嵌 WebView 中加载
- 内置单实例互斥锁，重复启动自动退出
- 关闭窗口即回收整个进程树，不留孤儿进程
- 可离线运行：dsh 运行时随包分发（`node.exe` + `node_modules`），不依赖网络安装
- 运行时自更新：每次启动查一次 npm 是否有新版 dsh（最多等 3 秒），关窗后静默安装、下次启动生效；离线启动永不受阻
- 免安装部署：解压即用，或使用 Inno Setup 安装包

### 工作原理

```
┌────────────────────────────────────────────┐
│  dsh-browser.exe (Python/pywebview)        │
│                                            │
│  1. 找空闲端口                              │
│  2. 启动 dsh web --port (子进程)            │
│  3. 轮询 HTTP 200 就绪                      │
│  4. WebView 加载 http://127.0.0.1:<port>    │
│  5. 关窗 → taskkill 整个进程树              │
└────────────────────────────────────────────┘
```

dsh 运行时解析优先级（`main.py` `resolve_dsh_cmd`）：

1. 程序同级的 `node/` 目录（exe/脚本所在目录，含 `node.exe` 与 `node_modules/@deepseek-ai/dsh`）
2. 环境变量 `DSH_BROWSER_NODE_DIR` 指向的目录
3. PATH 上的 `npx -y @deepseek-ai/dsh`（需联网）

### 目录结构

```
main.py            应用入口（唯一源码文件）
dsh-browser.spec   PyInstaller 打包配置
installer.iss      Inno Setup 安装包脚本
build.ps1          一键构建脚本（推荐入口）
requirements.txt   Python 依赖
version.txt        版本号单源
bundle/node/       离线 node 运行时（node.exe + node_modules，构建时复制进产物）
```

## 环境要求

- Windows 10/11（64 位）
- Python 3.13+（已验证 3.14.2）
- 构建可选：Inno Setup 6（生成安装包时用）
- 运行时：WebView2 运行时（Win10/11 通常自带）

## 开发运行

```powershell
pip install -r requirements.txt
python main.py
```

## 编译打包步骤

### 一键构建（推荐）

```powershell
.\build.ps1            # 构建 dist\dsh-browser\
.\build.ps1 -Installer # 构建并生成 installer\dsh-browser-setup.exe
.\build.ps1 -InstallDeps  # 先自动安装 Python 依赖
.\build.ps1 -Python py3.13 # 指定其他 Python 解释器
```

脚本自动完成：

1. 杀掉残留的 dsh-browser 进程（防止 dist 内 DLL 被占用导致 PermissionError）
2. 检查构建依赖（pywebview / pythonnet）
3. `pyinstaller dsh-browser.spec` → `dist\dsh-browser\`（exe + `_internal\`）
4. 复制 `bundle\node\*` → `dist\dsh-browser\node\`
5. 校验 `node.exe` 与 `@deepseek-ai/dsh/lib/bin.js` 存在
6. `-Installer` 时读取 `version.txt`，调用 iscc 打包 → `installer\dsh-browser-setup.exe`

### 手动打包（了解细节时）

```powershell
pyinstaller dsh-browser.spec
Copy-Item bundle\node\* .\dist\dsh-browser\node\ -Recurse -Force
# 可选：Inno Setup 打包
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss /DMyAppVersion=0.1.0
```

注意：构建后必须复制 `bundle\node\*`，否则 exe 找不到 dsh 运行时。

### 产物

- `dist\dsh-browser\`：免安装目录（整个目录分发即可）
- `installer\dsh-browser-setup.exe`：Inno Setup 安装包（含全部文件）

## 版本管理

版本号唯一来源为 `version.txt`，改版本只改这一个文件：

- PyInstaller 构建时读取它生成 exe 文件版本资源
- `build.ps1 -Installer` 通过 `iscc /DMyAppVersion=` 传给安装包脚本

## 常见问题

- **启动无反应/闪退**：确认 `node\` 目录随 exe 同目录分发，且包含 `node_modules\@deepseek-ai\dsh\lib\bin.js`；命令行方式运行 `python main.py` 可看到错误日志尾部。
- **自更新是怎么工作的？** 每次启动都会查一次 npm registry 上的最新 dsh（3 秒超时，离线时静默跳过）。发现新版后，在你关闭窗口*之后*才执行安装（捆绑包里没有 npm，会临时下载 npm 并用捆绑的 `node.exe` 引导；你自己的 `.npmrc` 镜像配置会被沿用）。新版本下次启动生效。慢网络下安装可能耗时几十分钟；任何失败都会自动回滚，绝不破坏现有运行时。程序目录只读（如装在 Program Files）时静默跳过更新。
- **构建报 PermissionError**：说明 dist 目录里有 DLL 被占用（程序在运行或残留进程），`build.ps1` 会自动处理，手动打包时需先结束 dsh-browser 相关进程。
