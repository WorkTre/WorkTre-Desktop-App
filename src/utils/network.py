"""
src/utils/network.py
Network utilities.
"""

import socket
import requests
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

from ..config import constants


def get_dynamic_ip() -> Optional[str]:
    """
    Get the machine's dynamic IP address.

    Returns:
        IP address string or None
    """
    try:
        # Method 1: Connect to external service
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # This doesn't actually establish a connection
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return ip
    except Exception:
        pass

    try:
        # Method 2: Use socket.gethostname()
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass

    try:
        # Method 3: Try external service
        response = requests.get("https://api.ipify.org", timeout=5)
        if response.status_code == 200:
            return response.text.strip()
    except Exception:
        pass

    return None


def check_internet_connection(timeout: int = 5) -> Tuple[bool, Optional[str]]:
    """
    Check internet connectivity.

    Args:
        timeout: Timeout in seconds

    Returns:
        Tuple of (is_connected, error_message)
    """
    test_urls = [
        "https://www.google.com",
        "https://www.cloudflare.com",
        "https://www.apple.com",
    ]

    for url in test_urls:
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code < 400:
                return True, None
        except requests.exceptions.RequestException as e:
            last_error = str(e)
            continue

    return False, last_error or "No internet connection"


def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid.

    Args:
        url: URL to check

    Returns:
        True if URL is valid
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def download_file(url: str, destination: str, timeout: int = 30) -> Tuple[bool, Optional[str]]:
    """
    Download a file from URL.

    Args:
        url: File URL
        destination: Destination path
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, error_message)
    """
    try:
        response = requests.get(url, stream=True, timeout=timeout)
        response.raise_for_status()

        with open(destination, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return True, None

    except requests.exceptions.RequestException as e:
        return False, str(e)
    except IOError as e:
        return False, f"File write error: {e}"
    except Exception as e:
        return False, str(e)


def get_network_info() -> dict:
    """
    Get network information.

    Returns:
        Dictionary with network info
    """
    info = {
        "hostname": socket.gethostname(),
        "ip_address": get_dynamic_ip(),
        "timestamp": time.time(),
    }

    try:
        # Get network interfaces
        import psutil
        net_io = psutil.net_io_counters()
        info.update({
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            "packets_sent": net_io.packets_sent,
            "packets_recv": net_io.packets_recv,
        })
    except ImportError:
        pass

    return info


def test_connection_to_server(server_url: str, timeout: int = 10) -> Tuple[bool, float, Optional[str]]:
    """
    Test connection to a specific server.

    Args:
        server_url: Server URL
        timeout: Timeout in seconds

    Returns:
        Tuple of (success, response_time_ms, error_message)
    """
    start_time = time.time()

    try:
        response = requests.get(server_url, timeout=timeout)
        response_time = (time.time() - start_time) * 1000  # Convert to ms

        if response.status_code < 400:
            return True, response_time, None
        else:
            return False, response_time, f"HTTP {response.status_code}"

    except requests.exceptions.Timeout:
        response_time = (time.time() - start_time) * 1000
        return False, response_time, "Timeout"
    except requests.exceptions.RequestException as e:
        response_time = (time.time() - start_time) * 1000
        return False, response_time, str(e)