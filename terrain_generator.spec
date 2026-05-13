# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Terrain Generator GUI

Standard build:  pyinstaller terrain_generator.spec
Fast build:      BUILD_FAST=1 pyinstaller terrain_generator.spec
Debug build:     BUILD_DEBUG=1 pyinstaller terrain_generator.spec

Note: PyInstaller cannot cross-compile. The Windows EXE must be built on Windows,
and the Linux binary must be built on Linux.
"""

import sys
import os
from pathlib import Path

block_cipher = None

if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    try:
        PROJECT_ROOT = Path(__file__).parent.absolute()
    except NameError:
        PROJECT_ROOT = Path.cwd()

hiddenimports = [
    'src.displacement_builder',
    'src.entity_placer',
    'src.skybox_manager',
    'src.material_manager',
    'src.terrain_pipeline',
    'src.canyon_generator',
    'src.noise',
    'src.vmf_gen',
    'src.config_model',
    'src.layout_validator',
    'scipy.ndimage',
    'scipy._lib',
    'scipy.sparse'
]

build_mode = os.environ.get('BUILD_MODE', 'onefile')
build_fast = os.environ.get('BUILD_FAST', '0') == '1'
build_debug = os.environ.get('BUILD_DEBUG', '0') == '1'

if build_fast:
    hiddenimports.extend([
        'numba', 'numba.core', 'numba.typed', 'numba.np', 'numba.np.ufunc',
        'llvmlite', 'llvmlite.binding'
    ])

datas = []

config_dir = PROJECT_ROOT / 'config'
if config_dir.exists():
    for f in ['presets.json', 'textures.json', 'skyboxes.json']:
        fp = config_dir / f
        if fp.exists():
            datas.append((str(fp), 'config'))

rules_file = PROJECT_ROOT / 'map_rules.json'
if rules_file.exists():
    datas.append((str(rules_file), '.'))

icons_dir = PROJECT_ROOT / 'icons'
if icons_dir.exists():
    datas.append((str(icons_dir), 'icons'))

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
    runtime_hooks=['hooks/rth_numba.py'],
    excludes=[
        'matplotlib',
        'numpy._core.tests',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
        console=build_debug,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
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
        a.datas,
        [],
        name='TerrainGenerator',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=build_debug,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
    )
