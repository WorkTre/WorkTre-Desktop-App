"""
src/utils/file_utils.py
Comprehensive file and resource utilities.
"""

import os
import sys
import shutil
import tempfile
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional, Union, Any, Dict, List
from datetime import datetime
import portalocker

from ..config import settings
from ..platform.utils import get_app_data_dir, get_temp_dir


# ==================== PATH RESOLUTION ====================

def resource_path(relative_path: Union[str, Path]) -> str:
    """
    Get absolute path to resource, works for dev and PyInstaller.

    Args:
        relative_path: Path relative to assets directory

    Returns:
        Absolute path to resource
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # Normal execution - navigate to src/assets
        # Try multiple possible base paths
        possible_paths = [
            Path(__file__).parent.parent.parent / "src" / "assets",  # Development
            Path(__file__).parent.parent / "assets",                 # Alternative
            Path.cwd() / "src" / "assets",                           # From CWD
            Path.cwd() / "assets",                                   # Direct assets
        ]

        base_path = None
        for path in possible_paths:
            if path.exists():
                base_path = path
                break

        if base_path is None:
            # Fallback to current directory
            base_path = Path.cwd()

    # Convert relative path to Path object
    if isinstance(relative_path, str):
        relative_path = Path(relative_path)

    full_path = base_path / relative_path

    # Try alternative paths if file doesn't exist
    if not full_path.exists():
        # Try without 'src/assets' prefix (for development)
        alt_path = Path(__file__).parent.parent.parent / relative_path
        if alt_path.exists():
            return str(alt_path)

    return str(full_path)


def get_asset_path(relative_path: Union[str, Path]) -> str:
    """
    Get path to asset file.

    Args:
        relative_path: Path relative to assets directory

    Returns:
        Absolute path to asset
    """
    return resource_path(relative_path)


def get_app_data_path(filename: str, app_name: str = "WorkTre") -> str:
    """
    Get path to file in application data directory.

    Args:
        filename: Name of the file
        app_name: Application name

    Returns:
        Absolute path to file in app data directory
    """
    base_dir = get_app_data_dir(app_name)
    return os.path.join(base_dir, filename)


def get_temp_file_path(filename: str, app_name: str = "WorkTre") -> str:
    """
    Get path to file in temporary directory.

    Args:
        filename: Name of the file
        app_name: Application name

    Returns:
        Absolute path to file in temp directory
    """
    temp_dir = get_temp_dir(app_name)
    return os.path.join(temp_dir, filename)


# ==================== DIRECTORY OPERATIONS ====================

def ensure_directory(path: Union[str, Path]) -> str:
    """
    Ensure directory exists, create if it doesn't.

    Args:
        path: Directory path

    Returns:
        The path as string
    """
    path_obj = Path(path)
    path_obj.mkdir(parents=True, exist_ok=True)
    return str(path_obj)


def ensure_parent_directory(filepath: Union[str, Path]) -> str:
    """
    Ensure parent directory of a file exists.

    Args:
        filepath: File path

    Returns:
        The filepath as string
    """
    path_obj = Path(filepath)
    path_obj.parent.mkdir(parents=True, exist_ok=True)
    return str(filepath)


def list_files(directory: Union[str, Path], pattern: str = "*",
               recursive: bool = False) -> List[str]:
    """
    List files in directory.

    Args:
        directory: Directory path
        pattern: Glob pattern
        recursive: Whether to search recursively

    Returns:
        List of file paths
    """
    directory = Path(directory)
    if not directory.exists():
        return []

    if recursive:
        files = list(directory.rglob(pattern))
    else:
        files = list(directory.glob(pattern))

    return [str(f) for f in files if f.is_file()]


def get_directory_size(directory: Union[str, Path]) -> int:
    """
    Get total size of directory in bytes.

    Args:
        directory: Directory path

    Returns:
        Total size in bytes
    """
    directory = Path(directory)
    if not directory.exists():
        return 0

    total = 0
    for item in directory.rglob('*'):
        if item.is_file():
            total += item.stat().st_size

    return total


def clean_directory(directory: Union[str, Path], max_age_days: int = 30) -> int:
    """
    Clean old files from directory.

    Args:
        directory: Directory path
        max_age_days: Maximum age of files in days

    Returns:
        Number of files removed
    """
    directory = Path(directory)
    if not directory.exists():
        return 0

    removed = 0
    current_time = datetime.now().timestamp()
    max_age_seconds = max_age_days * 24 * 3600

    for item in directory.iterdir():
        if item.is_file():
            mtime = item.stat().st_mtime
            if current_time - mtime > max_age_seconds:
                try:
                    item.unlink()
                    removed += 1
                except Exception:
                    pass

    return removed


# ==================== FILE OPERATIONS ====================

def read_text_file(filepath: Union[str, Path]) -> Optional[str]:
    """
    Read text file.

    Args:
        filepath: Path to file

    Returns:
        File content or None
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"Error reading text file {filepath}: {e}")
        return None


def write_text_file(filepath: Union[str, Path], content: str,
                   append: bool = False) -> bool:
    """
    Write text file.

    Args:
        filepath: Path to file
        content: Content to write
        append: Whether to append to existing file

    Returns:
        True if successful
    """
    try:
        ensure_parent_directory(filepath)
        mode = 'a' if append else 'w'
        with open(filepath, mode, encoding='utf-8') as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"Error writing text file {filepath}: {e}")
        return False


def read_json_file(filepath: Union[str, Path]) -> Optional[Any]:
    """
    Read JSON file.

    Args:
        filepath: Path to file

    Returns:
        Parsed JSON or None
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {filepath}: {e}")
        return None
    except Exception as e:
        print(f"Error reading JSON file {filepath}: {e}")
        return None


def write_json_file(filepath: Union[str, Path], data: Any,
                   indent: int = 2, **kwargs) -> bool:
    """
    Write JSON file.

    Args:
        filepath: Path to file
        data: Data to write
        indent: JSON indentation
        **kwargs: Additional arguments for json.dump

    Returns:
        True if successful
    """
    try:
        ensure_parent_directory(filepath)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False, **kwargs)
        return True
    except Exception as e:
        print(f"Error writing JSON file {filepath}: {e}")
        return False


def read_binary_file(filepath: Union[str, Path]) -> Optional[bytes]:
    """
    Read binary file.

    Args:
        filepath: Path to file

    Returns:
        File content as bytes or None
    """
    try:
        with open(filepath, 'rb') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading binary file {filepath}: {e}")
        return None


def write_binary_file(filepath: Union[str, Path], data: bytes) -> bool:
    """
    Write binary file.

    Args:
        filepath: Path to file
        data: Data to write

    Returns:
        True if successful
    """
    try:
        ensure_parent_directory(filepath)
        with open(filepath, 'wb') as f:
            f.write(data)
        return True
    except Exception as e:
        print(f"Error writing binary file {filepath}: {e}")
        return False


def copy_file(source: Union[str, Path], destination: Union[str, Path],
             overwrite: bool = True) -> bool:
    """
    Copy file.

    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing file

    Returns:
        True if successful
    """
    try:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            print(f"Source file not found: {source}")
            return False

        if dest_path.exists() and not overwrite:
            return False

        ensure_parent_directory(dest_path)
        shutil.copy2(source_path, dest_path)
        return True
    except Exception as e:
        print(f"Error copying file: {e}")
        return False


def move_file(source: Union[str, Path], destination: Union[str, Path],
             overwrite: bool = True) -> bool:
    """
    Move file.

    Args:
        source: Source file path
        destination: Destination file path
        overwrite: Whether to overwrite existing file

    Returns:
        True if successful
    """
    try:
        source_path = Path(source)
        dest_path = Path(destination)

        if not source_path.exists():
            print(f"Source file not found: {source}")
            return False

        if dest_path.exists() and not overwrite:
            return False

        ensure_parent_directory(dest_path)
        shutil.move(str(source_path), str(dest_path))
        return True
    except Exception as e:
        print(f"Error moving file: {e}")
        return False


def delete_file(filepath: Union[str, Path]) -> bool:
    """
    Delete file.

    Args:
        filepath: Path to file

    Returns:
        True if successful
    """
    try:
        path = Path(filepath)
        if path.exists():
            path.unlink()
        return True
    except Exception as e:
        print(f"Error deleting file {filepath}: {e}")
        return False


def get_file_size(filepath: Union[str, Path]) -> int:
    """
    Get file size in bytes.

    Args:
        filepath: Path to file

    Returns:
        File size in bytes, 0 if file doesn't exist
    """
    try:
        return Path(filepath).stat().st_size
    except Exception:
        return 0


def get_file_modified_time(filepath: Union[str, Path]) -> Optional[datetime]:
    """
    Get file last modified time.

    Args:
        filepath: Path to file

    Returns:
        Datetime object or None
    """
    try:
        timestamp = Path(filepath).stat().st_mtime
        return datetime.fromtimestamp(timestamp)
    except Exception:
        return None


def file_exists(filepath: Union[str, Path]) -> bool:
    """
    Check if file exists.

    Args:
        filepath: Path to file

    Returns:
        True if file exists
    """
    return Path(filepath).exists()


def get_file_hash(filepath: Union[str, Path], algorithm: str = 'md5') -> Optional[str]:
    """
    Get file hash.

    Args:
        filepath: Path to file
        algorithm: Hash algorithm (md5, sha1, sha256)

    Returns:
        Hash string or None
    """
    try:
        hash_func = getattr(hashlib, algorithm)()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_func.update(chunk)
        return hash_func.hexdigest()
    except Exception as e:
        print(f"Error calculating file hash: {e}")
        return None


# ==================== LOCKING ====================

class FileLock:
    """Cross-platform file lock."""

    def __init__(self, filepath: Union[str, Path], timeout: int = 10):
        self.filepath = str(filepath)
        self.timeout = timeout
        self._handle = None
        self._acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def acquire(self) -> bool:
        """Acquire lock."""
        try:
            ensure_parent_directory(self.filepath)
            self._handle = open(self.filepath, 'w')
            portalocker.lock(
                self._handle,
                portalocker.LOCK_EX | portalocker.LOCK_NB
            )
            self._acquired = True
            return True
        except portalocker.exceptions.LockException:
            return False
        except Exception as e:
            print(f"Error acquiring lock: {e}")
            return False

    def release(self) -> None:
        """Release lock."""
        if self._handle:
            try:
                portalocker.unlock(self._handle)
                self._handle.close()
            except Exception:
                pass
            self._handle = None
        self._acquired = False

    @property
    def is_locked(self) -> bool:
        """Check if lock is acquired."""
        return self._acquired


# ==================== TEMP FILES ====================

class TempFile:
    """Context manager for temporary file."""

    def __init__(self, suffix: str = None, prefix: str = None,
                 directory: str = None, content: Any = None):
        self.suffix = suffix or '.tmp'
        self.prefix = prefix or 'worktre_'
        self.directory = directory
        self.content = content
        self.filepath = None

    def __enter__(self):
        fd, self.filepath = tempfile.mkstemp(
            suffix=self.suffix,
            prefix=self.prefix,
            dir=self.directory
        )
        os.close(fd)

        if self.content is not None:
            if isinstance(self.content, str):
                write_text_file(self.filepath, self.content)
            elif isinstance(self.content, bytes):
                write_binary_file(self.filepath, self.content)
            elif isinstance(self.content, (dict, list)):
                write_json_file(self.filepath, self.content)

        return self.filepath

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.filepath and os.path.exists(self.filepath):
            try:
                os.unlink(self.filepath)
            except Exception:
                pass


def create_temp_file(content: Any = None, suffix: str = '.tmp',
                    prefix: str = 'worktre_') -> str:
    """
    Create a temporary file.

    Args:
        content: Content to write to file
        suffix: File suffix
        prefix: File prefix

    Returns:
        Path to temporary file
    """
    with TempFile(suffix=suffix, prefix=prefix, content=content) as temp_path:
        # Copy the file since it will be deleted
        dest_path = get_temp_file_path(os.path.basename(temp_path))
        copy_file(temp_path, dest_path, overwrite=True)
        return dest_path


def cleanup_temp_files(app_name: str = "WorkTre", max_age_hours: int = 24) -> int:
    """
    Clean up old temporary files.

    Args:
        app_name: Application name
        max_age_hours: Maximum age of files in hours

    Returns:
        Number of files removed
    """
    temp_dir = get_temp_dir(app_name)
    if not os.path.exists(temp_dir):
        return 0

    return clean_directory(temp_dir, max_age_days=max_age_hours / 24)


# ==================== APP DATA ====================

def save_to_app_data(filename: str, content: Any,
                    app_name: str = "WorkTre") -> Optional[str]:
    """
    Save file to application data directory.

    Args:
        filename: Name of the file
        content: Content to save
        app_name: Application name

    Returns:
        Path where file was saved, or None on error
    """
    filepath = get_app_data_path(filename, app_name)

    if isinstance(content, (dict, list)):
        success = write_json_file(filepath, content)
    elif isinstance(content, str):
        success = write_text_file(filepath, content)
    elif isinstance(content, bytes):
        success = write_binary_file(filepath, content)
    else:
        success = write_text_file(filepath, str(content))

    return filepath if success else None


def load_from_app_data(filename: str, app_name: str = "WorkTre",
                      default: Any = None) -> Any:
    """
    Load file from application data directory.

    Args:
        filename: Name of the file
        app_name: Application name
        default: Default value if file doesn't exist

    Returns:
        Loaded content or default
    """
    filepath = get_app_data_path(filename, app_name)

    if not os.path.exists(filepath):
        return default

    if filename.endswith('.json'):
        return read_json_file(filepath) or default
    elif filename.endswith(('.txt', '.log', '.md')):
        return read_text_file(filepath) or default
    else:
        return read_binary_file(filepath) or default


def delete_from_app_data(filename: str, app_name: str = "WorkTre") -> bool:
    """
    Delete file from application data directory.

    Args:
        filename: Name of the file
        app_name: Application name

    Returns:
        True if successful
    """
    filepath = get_app_data_path(filename, app_name)
    return delete_file(filepath)


def list_app_data_files(pattern: str = "*", app_name: str = "WorkTre") -> List[str]:
    """
    List files in application data directory.

    Args:
        pattern: Glob pattern
        app_name: Application name

    Returns:
        List of file paths
    """
    app_data_dir = get_app_data_dir(app_name)
    return list_files(app_data_dir, pattern)


# ==================== VERSION ====================

def get_local_version(version_file: str = "version.txt") -> str:
    """
    Read version from version.txt file with comprehensive path resolution.

    Args:
        version_file: Version file name

    Returns:
        Version string or default
    """
    # Setup logger
    logger = logging.getLogger(__name__)

    # Get current file location for debugging
    current_file = Path(__file__).absolute()
    logger.debug(f"Current file: {current_file}")

    # Try multiple possible paths
    possible_paths = []

    # 1. Resource path (assets folder via resource_path)
    try:
        res_path = resource_path(version_file)
        possible_paths.append(("resource_path", res_path))
    except Exception as e:
        logger.debug(f"resource_path error: {e}")

    # 2. Direct path to src/assets from utils location
    src_assets = Path(__file__).parent.parent / "assets" / version_file
    possible_paths.append(("src/assets (relative to utils)", str(src_assets)))

    # 3. Current working directory + src/assets
    cwd_src = Path.cwd() / "src" / "assets" / version_file
    possible_paths.append(("cwd/src/assets", str(cwd_src)))

    # 4. Current working directory + assets
    cwd_assets = Path.cwd() / "assets" / version_file
    possible_paths.append(("cwd/assets", str(cwd_assets)))

    # 5. Parent of parent of this file (project root)
    project_root = Path(__file__).parent.parent.parent / version_file
    possible_paths.append(("project_root", str(project_root)))

    # 6. One level up from utils
    parent_dir = Path(__file__).parent.parent / version_file
    possible_paths.append(("parent_dir", str(parent_dir)))

    # 7. Same directory as this file
    same_dir = Path(__file__).parent / version_file
    possible_paths.append(("same_dir", str(same_dir)))

    logger.debug("Searching for version.txt in following locations:")
    for source, path in possible_paths:
        logger.debug(f"  {source}: {path}")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        logger.info(f"✅ Loaded version {content} from {source}: {path}")
                        return content
                    else:
                        logger.warning(f"⚠️ Version file empty: {path}")
            except Exception as e:
                logger.error(f"❌ Error reading {path}: {e}")

    # If we get here, no version file was found
    logger.warning("⚠️ No version.txt found, using default 1.0.1")

    # Try to create a default version.txt in the most likely location
    try:
        # Try to create in src/assets
        default_path = Path(__file__).parent.parent / "assets" / version_file
        default_path.parent.mkdir(parents=True, exist_ok=True)
        with open(default_path, 'w') as f:
            f.write("2.2.1")
        logger.info(f"✅ Created default version.txt at {default_path} with version 2.2.1")
        return "2.2.1"
    except Exception as e:
        logger.error(f"❌ Failed to create default version.txt: {e}")

    return "1.0.1"  # Final fallback


# ==================== EXPORTS ====================

__all__ = [
    # Path resolution
    'resource_path',
    'get_asset_path',
    'get_app_data_path',
    'get_temp_file_path',

    # Directory operations
    'ensure_directory',
    'ensure_parent_directory',
    'list_files',
    'get_directory_size',
    'clean_directory',

    # File operations
    'read_text_file',
    'write_text_file',
    'read_json_file',
    'write_json_file',
    'read_binary_file',
    'write_binary_file',
    'copy_file',
    'move_file',
    'delete_file',
    'get_file_size',
    'get_file_modified_time',
    'file_exists',
    'get_file_hash',

    # Locking
    'FileLock',

    # Temp files
    'TempFile',
    'create_temp_file',
    'cleanup_temp_files',

    # App data
    'save_to_app_data',
    'load_from_app_data',
    'delete_from_app_data',
    'list_app_data_files',

    # Version
    'get_local_version',
]