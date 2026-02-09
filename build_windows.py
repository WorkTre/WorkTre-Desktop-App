import PyInstaller.__main__
import os

PyInstaller.__main__.run([
    'main.py',
    '--name=WorkTre',
    '--onefile',
    '--windowed',
    '--add-data=index.html:.',
    '--add-data=icon.ico:.',
    '--icon=icon.ico',
    '--hidden-import=plyer.platforms.win.notification',
])