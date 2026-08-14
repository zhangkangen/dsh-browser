# dsh-browser

A Windows desktop container that embeds the [@deepseek-ai/dsh](https://github.com/deepseek-ai/dsh) web UI with pywebview (WebView2/WinForms), providing a standalone DeepSeek Harness desktop app.

**English** | [中文](README.zh-CN.md)

## Overview

### Features

- Picks a free port on startup and launches `dsh web` offline, then loads the UI in an embedded WebView once ready
- Single-instance mutex: launching a second instance exits immediately
- Kills the whole process tree on window close — no orphan processes
- Fully offline: the dsh runtime ships with the app (`node.exe` + `node_modules`), no network install required
- Portable: extract and run, or use the Inno Setup installer

### How it works

```
┌────────────────────────────────────────────┐
│  dsh-browser.exe (Python/pywebview)        │
│                                            │
│  1. Find a free port                       │
│  2. Start dsh web --port (child process)   │
│  3. Poll until HTTP 200 is ready           │
│  4. WebView loads http://127.0.0.1:<port>  │
│  5. On close -> taskkill whole tree        │
└────────────────────────────────────────────┘
```

dsh runtime resolution order (`resolve_dsh_cmd` in `main.py`):

1. `node/` directory next to the program (exe/script dir, containing `node.exe` and `node_modules/@deepseek-ai/dsh`)
2. Directory pointed to by the `DSH_BROWSER_NODE_DIR` environment variable
3. `npx -y @deepseek-ai/dsh` on PATH (requires network)

### Directory layout

```
main.py            App entry point (the only source file)
dsh-browser.spec   PyInstaller build config
installer.iss      Inno Setup installer script
build.ps1          One-click build script (recommended entry)
requirements.txt   Python dependencies
version.txt        Single source of truth for the version
bundle/node/       Offline node runtime (node.exe + node_modules, copied into the build)
```

## Requirements

- Windows 10/11 (64-bit)
- Python 3.13+ (verified on 3.14.2)
- Optional for building: Inno Setup 6 (for the installer)
- Runtime: WebView2 runtime (usually preinstalled on Win10/11)

## Development

```powershell
pip install -r requirements.txt
python main.py
```

## Build & Package

### One-click build (recommended)

```powershell
.\build.ps1               # builds dist\dsh-browser\
.\build.ps1 -Installer    # builds and produces installer\dsh-browser-setup.exe
.\build.ps1 -InstallDeps  # installs Python deps first
.\build.ps1 -Python py3.13 # use a specific Python executable
```

The script automates:

1. Kills leftover dsh-browser processes (avoids PermissionError from locked DLLs in dist)
2. Checks build deps (pywebview / pythonnet)
3. `pyinstaller dsh-browser.spec` -> `dist\dsh-browser\` (exe + `_internal\`)
4. Copies `bundle\node\*` -> `dist\dsh-browser\node\`
5. Verifies `node.exe` and `@deepseek-ai/dsh/lib/bin.js` exist
6. With `-Installer`: reads `version.txt` and runs iscc -> `installer\dsh-browser-setup.exe`

### Manual packaging (for reference)

```powershell
pyinstaller dsh-browser.spec
Copy-Item bundle\node\* .\dist\dsh-browser\node\ -Recurse -Force
# Optional: Inno Setup packaging
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss /DMyAppVersion=0.1.0
```

Note: you must copy `bundle\node\*` after building, otherwise the exe cannot find the dsh runtime.

### Artifacts

- `dist\dsh-browser\`: portable directory (distribute the whole folder)
- `installer\dsh-browser-setup.exe`: Inno Setup installer (contains everything)

## Versioning

`version.txt` is the single source of truth for the version — change only this file:

- PyInstaller reads it to stamp the exe file version resource
- `build.ps1 -Installer` passes it to the installer via `iscc /DMyAppVersion=`

## FAQ

- **App won't start / exits silently**: make sure `node\` ships next to the exe and contains `node_modules\@deepseek-ai\dsh\lib\bin.js`; run `python main.py` from a terminal to see the tail of the error log.
- **Build fails with PermissionError**: a DLL in dist is locked (app running or leftover process). `build.ps1` handles this automatically; when packaging manually, end dsh-browser-related processes first.
