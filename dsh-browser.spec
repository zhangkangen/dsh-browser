# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

datas = []
binaries = []
hiddenimports = ['webview.platforms.winforms']
tmp_ret = collect_all('pythonnet')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('clr_loader')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

version_path = os.path.join(SPECPATH, 'version.txt')
with open(version_path, encoding='utf-8') as f:
    app_version = f.read().strip()
ver_parts = [int(p) for p in app_version.split('.')]
while len(ver_parts) < 4:
    ver_parts.append(0)

version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=tuple(ver_parts),
        prodvers=tuple(ver_parts),
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo([
            StringTable(
                '080404b0',
                [
                    StringStruct('CompanyName', 'DeepSeek Harness'),
                    StringStruct('FileDescription', 'dsh-browser'),
                    StringStruct('FileVersion', app_version),
                    StringStruct('InternalName', 'dsh-browser'),
                    StringStruct('OriginalFilename', 'dsh-browser.exe'),
                    StringStruct('ProductName', 'DeepSeek Harness 浏览器容器'),
                    StringStruct('ProductVersion', app_version),
                ],
            )
        ]),
        VarFileInfo([VarStruct('Translation', [2052, 1200])]),
    ],
)


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='dsh-browser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='dsh-browser',
)
