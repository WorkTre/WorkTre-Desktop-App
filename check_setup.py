"""
check_setup.py
Verify your WorkTre setup is correct.
"""

import os
import sys

print("🔍 Checking WorkTre setup...")
print("=" * 50)

# Check Python version
print(f"📌 Python version: {sys.version}")
print()

# Check current directory
project_root = os.getcwd()
print(f"📁 Project root: {project_root}")
print()

# Check for src folder
src_path = os.path.join(project_root, 'src')
if os.path.exists(src_path):
    print("✅ src folder exists")
else:
    print("❌ src folder not found!")
print()

# Check for version.txt
version_paths = [
    os.path.join(project_root, 'src', 'assets', 'version.txt'),
    os.path.join(project_root, 'assets', 'version.txt'),
]
for path in version_paths:
    if os.path.exists(path):
        with open(path, 'r') as f:
            version = f.read().strip()
        print(f"✅ Version file found at {path}")
        print(f"   Version: {version}")
        break
else:
    print("❌ version.txt not found!")
print()

# Check for __init__.py files
init_files = [
    'src/__init__.py',
    'src/config/__init__.py',
    'src/platform/__init__.py',
    'src/platform/tray/__init__.py',
    'src/managers/__init__.py',
    'src/api/__init__.py',
    'src/ui/__init__.py',
    'src/utils/__init__.py',
]

for init_file in init_files:
    full_path = os.path.join(project_root, init_file)
    if os.path.exists(full_path):
        print(f"✅ {init_file}")
    else:
        print(f"❌ {init_file} - MISSING!")
print()

# Test import
print("🧪 Testing imports...")
try:
    sys.path.insert(0, project_root)
    from src.utils.file_utils import get_local_version
    version = get_local_version()
    print(f"✅ Successfully imported get_local_version()")
    print(f"   Version: {version}")
    
    from src.config import settings
    settings.set_version(version)
    print(f"✅ Successfully imported settings")
    
    print("\n🎯 All systems go! You can now run: python -m src.main")
    
except Exception as e:
    print(f"❌ Import test failed: {e}")

print("=" * 50)