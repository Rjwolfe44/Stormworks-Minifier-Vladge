# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

block_cipher = None

# ── GUI Analysis ──────────────────────────────────────────────────────────────
gui_a = Analysis(
    ['src\\gui\\app.py'],
    pathex=[],
    binaries=[],
    datas=[('src', 'src')],
    hiddenimports=['customtkinter', 'pyperclip', 'tkinterdnd2', 'watchdog', 'pypresence'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'matplotlib', 'numpy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

gui_pyz = PYZ(gui_a.pure, gui_a.zipped_data, cipher=block_cipher)

# Standalone GUI (Onefile)
gui_exe_onefile = EXE(
    gui_pyz,
    gui_a.scripts,
    gui_a.binaries,
    gui_a.zipfiles,
    gui_a.datas,
    [],
    name='VladgeMinifier_Standalone',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src\\assets\\logo.ico',
)

# Shared Directory GUI (Onedir)
gui_exe_onedir = EXE(
    gui_pyz,
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name='VladgeMinifier',
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
    icon='src\\assets\\logo.ico',
)

# ── CLI Analysis ──────────────────────────────────────────────────────────────
cli_a = Analysis(
    ['src\\cli\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('src', 'src')],
    hiddenimports=['pyperclip'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'matplotlib', 'numpy', 'customtkinter', 'tkinter'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

cli_pyz = PYZ(cli_a.pure, cli_a.zipped_data, cipher=block_cipher)

# Shared Directory CLI (Onedir)
cli_exe_onedir = EXE(
    cli_pyz,
    cli_a.scripts,
    [],
    exclude_binaries=True,
    name='vladgeminifier-cli',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src\\assets\\logo.ico',
)

# ── Merge Dependencies ──────────────────────────────────────────────────────
def merge_lists(l1, l2):
    seen = set()
    merged = []
    for item in l1 + l2:
        if item[0] not in seen:
            seen.add(item[0])
            merged.append(item)
    return merged

merged_binaries = merge_lists(gui_a.binaries, cli_a.binaries)
merged_zipfiles = merge_lists(gui_a.zipfiles, cli_a.zipfiles)
merged_datas = merge_lists(gui_a.datas, cli_a.datas)

# ── Collect both into ONE directory ───────────────────────────────────────────
coll = COLLECT(
    gui_exe_onedir,
    cli_exe_onedir,
    merged_binaries,
    merged_zipfiles,
    merged_datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VladgeMinifier_Export',
)
