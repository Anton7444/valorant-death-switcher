# -*- mode: python ; coding: utf-8 -*-
"""Standalone Windows executable for direct GitHub Release downloads."""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [('src/valorant_switcher/templates', 'valorant_switcher/templates')]
binaries = []
hiddenimports = collect_submodules('winrt')
dxcam_datas, dxcam_binaries, dxcam_imports = collect_all('dxcam')
datas += dxcam_datas
binaries += dxcam_binaries
hiddenimports += dxcam_imports

a = Analysis(
    ['run.py'],
    pathex=['src'],
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
# Qt6Core needs the Windows ICU DLL. ICU 78 found in other packages exports
# incompatible suffixed names, so exclude it as in the folder build.
a.binaries = [
    item for item in a.binaries
    if item[0].split('\\')[-1].split('/')[-1].lower() not in {'icuuc.dll', 'icudt78.dll'}
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ValorantDeathSwitcherStandalone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
