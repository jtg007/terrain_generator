# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Terrain Generator GUI

Build with:
    pyinstaller terrain_generator.spec --onefile --windowed

Or install PyInstaller first:
    pip install pyinstaller
"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

# Project root directory - use sys._MEIPASS when bundled, otherwise use script location
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    try:
        PROJECT_ROOT = Path(__file__).parent.absolute()
    except NameError:
        PROJECT_ROOT = Path.cwd()

# We explicitly let PyInstaller auto-detect PySide6 modules
hiddenimports = []

# Collect data files from packages
datas = []

# Config directory - bundle data files only, not python code
config_dir = PROJECT_ROOT / 'config'
if config_dir.exists():
    # Bundle only actual config data files
    for f in ['presets.json', 'textures.json', 'skyboxes.json']:
        fp = config_dir / f
        if fp.exists():
            datas.append((str(fp), 'config'))

# map_rules.json if exists
rules_file = PROJECT_ROOT / 'map_rules.json'
if rules_file.exists():
    datas.append((str(rules_file), '.'))

# Include icons folder
icons_dir = PROJECT_ROOT / 'icons'
if icons_dir.exists():
    datas.append((str(icons_dir), 'icons'))

# Include models folder
models_dir = PROJECT_ROOT / 'models'
if models_dir.exists():
    datas.append((str(models_dir), 'models'))


a = Analysis(
    [str(PROJECT_ROOT / 'tools' / 'terrain_generator.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy._core.tests',
        'pandas',
        'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

build_mode = os.environ.get('BUILD_MODE', 'onefile')

if build_mode == 'onedir':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='TerrainGenerator',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,  # Windowed mode - no console
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,  # Add icon.ico here if you have one
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='TerrainGenerator',
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='TerrainGenerator',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,  # Windowed mode - no console
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,  # Add icon.ico here if you have one
    )
