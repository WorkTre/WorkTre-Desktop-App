"""
src/api/actions.py
SOAP action builder for WorkTre API.
"""

from urllib.parse import urljoin


class SOAPActionBuilder:
    """Build SOAP action URLs for WorkTre API."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def login(self) -> str:
        """Get login SOAP action."""
        return urljoin(self.base_url, "login")

    def logout(self) -> str:
        """Get logout SOAP action."""
        return urljoin(self.base_url, "logout")

    def breakin(self) -> str:
        """Get breakin SOAP action."""
        return urljoin(self.base_url, "breakin")

    def breakout(self) -> str:
        """Get breakout SOAP action."""
        return urljoin(self.base_url, "breakout")

    def inactivity(self) -> str:
        """Get inactivity SOAP action."""
        return urljoin(self.base_url, "inactivity")

    def logoutinactivity(self) -> str:
        """Get logoutinactivity SOAP action."""
        return urljoin(self.base_url, "logoutinactivity")

    def crashlogin(self) -> str:
        """Get crashlogin SOAP action."""
        return urljoin(self.base_url, "crashlogin")

    def lastactivitydate(self) -> str:
        """Get lastactivitydate SOAP action."""
        return urljoin(self.base_url, "lastactivitydate")

    def getservice(self) -> str:
        """Get getservice SOAP action."""
        return urljoin(self.base_url, "getservice")

    def versioncheck(self) -> str:
        """Get versioncheck SOAP action."""
        return urljoin(self.base_url, "versioncheck")

    def getBreakTypes(self) -> str:
        """Get getBreakTypes SOAP action."""
        return urljoin(self.base_url, "getBreakTypes")

    def requestforaccess(self) -> str:
        """Get requestforaccess SOAP action."""
        return urljoin(self.base_url, "requestforaccess")