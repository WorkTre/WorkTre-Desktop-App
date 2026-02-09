import PyInstaller.__main__
import os

PyInstaller.__main__.run([
    'main.py',
    '--name=WorkTre',
    '--onefile',
    '--windowed',
    '--add-data=index.html:.',
    '--add-data=icon.png:.',
    '--hidden-import=plyer.platforms.linux.notification',
])