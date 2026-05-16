# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['src/main.py'],
    # Ensure project root is on the import path so `import src.*` works when frozen
    pathex=['.'],
    binaries=[],
    datas=[('src/assets/icons/setup.ico', '.'), ('src/assets/icons/icon.ico', '.'), ('src/assets/version.txt', '.'), ('src/assets', 'src/assets')],
    # Many modules are lazy-imported (importlib) so PyInstaller won't discover them automatically.
    # We include a "belt and suspenders" approach:
    # - explicit list for critical runtime modules
    # - plus collect_submodules('src') to catch everything else
    hiddenimports=[
        # Critical lazy imports (fail hard if missing)
        'src.api.soap_client',
        'src.api.actions',
        'src.managers.inactivity',
        'src.managers.connectivity',
        'src.managers.system',
        'src.managers.update_manager',
        'src.platform.notifications',
        'src.platform.tray',
        'src.platform.tray.base',
        'src.platform.tray.windows',
        'src.ui.dialogs',
        'src.ui.window',
        'src.utils.security',
        'src.utils.screenshot',
        'src.utils.update',
        'src.utils.updater',
        # Catch-all
        *collect_submodules('src'),
    ],
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
    name='WorkTre',
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
    icon=['src/assets/icons/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='WorkTre',
)
