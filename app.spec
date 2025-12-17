# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

def collect_assets():
    assets = []

    # Main HTML file
    assets.append(('index.html', '.'))

    # CSS assets
    css_files = [
        'assets/css/style.css',
        # Add other CSS files if needed
    ]

    # JS assets
    js_files = [
        'assets/js/custom.js',
        # Add other JS files if needed
    ]

    # Image assets
    image_files = [
        'assets/images/loginScreen.png',
        'assets/images/loginFormBg.png',
        'assets/images/logo/email.png',
        'assets/images/logo/lock.png',
        # Add other image files if needed
    ]

    # Add all files to datas
    for file in css_files + js_files + image_files:
        if os.path.exists(file):
            dest_dir = os.path.dirname(file)
            assets.append((file, dest_dir))

    return assets

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=collect_assets(),
    hiddenimports=[
        'webview.platforms.win32',
        'webview.platforms.edgechromium'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='LoginApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console visible for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico',
)