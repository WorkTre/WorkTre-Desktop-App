"""
src/utils/updater.py
Smart update checker with multiple sources.
"""

import requests
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from packaging import version

from ..config import constants
from .logging import get_logger


class UpdateChecker:
    """Smart update checker with multiple sources and caching."""

    def __init__(self, logger=None):
        self.logger = logger or get_logger(__name__)
        self.cache = {}
        self.last_check = {}

    def _should_check(self, source: str, cooldown_minutes: int = 60) -> bool:
        """Rate limiting - don't check too often."""
        if source not in self.last_check:
            return True

        elapsed = datetime.now() - self.last_check[source]
        return elapsed > timedelta(minutes=cooldown_minutes)

    def _check_github(self) -> Optional[Dict[str, Any]]:
        """Check GitHub for updates."""
        if not self._should_check('github'):
            self.logger.debug("GitHub check rate limited, using cache")
            return self.cache.get('github')

        try:
            self.logger.info("📡 Checking GitHub for updates...")
            response = requests.get(
                constants.UPDATE_URL,
                timeout=5,
                headers={'User-Agent': 'WorkTre-Desktop/2.2.0'}
            )

            if response.status_code == 200:
                data = response.json()
                version = data.get("version")
                download_url = data.get("download_url")

                if version and download_url:
                    result = {
                        "status": True,
                        "source": "github",
                        "version": version,
                        "download_url": download_url,
                        "release_notes": data.get("release_notes", ""),
                        "required": data.get("required", False),
                        "timestamp": datetime.now().isoformat()
                    }

                    # Cache the result
                    self.cache['github'] = result
                    self.last_check['github'] = datetime.now()

                    self.logger.info(f"✅ GitHub: version {version} available")
                    return result

        except requests.exceptions.Timeout:
            self.logger.warning("⚠️ GitHub timeout")
        except requests.exceptions.ConnectionError:
            self.logger.warning("⚠️ GitHub connection error")
        except Exception as e:
            self.logger.warning(f"⚠️ GitHub error: {e}")

        return None

    def _check_soap(self) -> Optional[Dict[str, Any]]:
        """Check SOAP API for updates."""
        if not self._should_check('soap', cooldown_minutes=30):
            self.logger.debug("SOAP check rate limited, using cache")
            return self.cache.get('soap')

        try:
            self.logger.info("📡 Checking SOAP API for updates...")

            # Import here to avoid circular imports
            from ..api.soap_client import SOAPClient

            client = SOAPClient()
            response = client.version_check()

            if response.get("status"):
                data = response.get("data", {})
                result = {
                    "status": True,
                    "source": "soap",
                    "version": data.get("version"),
                    "download_url": data.get("download_url"),
                    "release_notes": data.get("description", ""),
                    "required": data.get("required", False),
                    "timestamp": datetime.now().isoformat()
                }

                # Cache the result
                self.cache['soap'] = result
                self.last_check['soap'] = datetime.now()

                self.logger.info(f"✅ SOAP: version {result['version']} available")
                return result

        except Exception as e:
            self.logger.warning(f"⚠️ SOAP error: {e}")

        return None

    def check_for_updates(self, local_version: str, force: bool = False) -> Dict[str, Any]:
        """
        Check for updates using multiple sources.

        Args:
            local_version: Current local version
            force: Force check even if rate limited

        Returns:
            Update information dictionary
        """
        self.logger.info(f"🔍 Checking for updates (local: {local_version})")

        # Priority 1: GitHub (fastest, most reliable)
        github_result = self._check_github()
        if github_result:
            remote_version = github_result["version"]

            if version.parse(remote_version) > version.parse(local_version):
                return {
                    "update_available": True,
                    "source": "github",
                    "current_version": local_version,
                    "latest_version": remote_version,
                    "download_url": github_result["download_url"],
                    "release_notes": github_result["release_notes"],
                    "required": github_result.get("required", False)
                }

        # Priority 2: SOAP API (fallback)
        soap_result = self._check_soap()
        if soap_result:
            remote_version = soap_result["version"]

            if version.parse(remote_version) > version.parse(local_version):
                return {
                    "update_available": True,
                    "source": "soap",
                    "current_version": local_version,
                    "latest_version": remote_version,
                    "download_url": soap_result["download_url"],
                    "release_notes": soap_result["release_notes"],
                    "required": soap_result.get("required", False)
                }

        # No updates available
        return {
            "update_available": False,
            "current_version": local_version,
            "message": "You're running the latest version"
        }

    def get_cached_version(self) -> Optional[str]:
        """Get cached version without checking."""
        cached = self.cache.get('github') or self.cache.get('soap')
        return cached.get("version") if cached else None


# Singleton instance
_update_checker = None


def get_update_checker() -> UpdateChecker:
    """Get or create global update checker."""
    global _update_checker
    if _update_checker is None:
        _update_checker = UpdateChecker()
    return _update_checker
