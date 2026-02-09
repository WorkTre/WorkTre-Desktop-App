# setup.py
from setuptools import setup, find_packages
import sys

requirements = [
    'pywebview>=4.0',
    'pystray>=0.19',
    'Pillow>=10.0',
    'plyer>=2.0',
    'requests>=2.31',
    'cryptography>=41.0',
    'packaging>=23.0',
    'portalocker>=2.0',
]

# Platform-specific requirements
if sys.platform == 'win32':
    requirements.append('pywin32>=306')  # For Windows notifications
elif sys.platform == 'darwin':
    requirements.append('pyobjc-framework-Cocoa>=10.0')  # For macOS notifications

setup(
    name="WorkTre",
    version="1.0.0",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'worktre=main:main',
        ],
    },
    include_package_data=True,
    package_data={
        '': ['*.html', '*.js', '*.css', '*.ico', '*.icns', '*.png'],
    },
)