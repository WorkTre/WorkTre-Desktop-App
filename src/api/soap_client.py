"""
src/api/soap_client.py
Complete SOAP API client for WorkTre.
"""

import requests
import socket
import json
import xml.etree.ElementTree as ET
import time
import certifi
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urljoin
from datetime import datetime

from ..config import constants, settings
from ..utils.network import get_dynamic_ip, check_internet_connection
from ..utils.logging import log_operation
from .actions import SOAPActionBuilder


class SOAPError(Exception):
    """SOAP API error."""
    pass


class SOAPClient:
    """Complete SOAP API client for WorkTre services."""

    def __init__(self, base_url: str = None, logger=None):
        """
        Initialize SOAP client.

        Args:
            base_url: SOAP service base URL
            logger: Logger instance
        """
        self.base_url = base_url or constants.SOAP_BASE_URL
        self.logger = logger or self._get_default_logger()
        self.action_builder = SOAPActionBuilder(self.base_url)

        # Session for connection pooling
        self.session = requests.Session()
        # Prefer system proxy settings when present (common in corporate networks)
        # and keep behavior consistent between "python -m" and frozen builds.
        self.session.trust_env = True
        self.session.headers.update({
            "Content-Type": "text/xml; charset=utf-8",
            "Accept": "text/xml",
            "User-Agent": f"WorkTre-Desktop/{settings.APP_VERSION}"
        })

        # Timeout settings
        self.timeout = constants.REQUEST_TIMEOUT
        self.retry_count = 3
        self.retry_delay = 2

        # State
        self._user_info: Optional[Dict[str, Any]] = None
        self._logged_in = False
        self._last_request_time = None
        self._request_count = 0

        # Namespaces for XML parsing
        self.namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

    def _get_default_logger(self):
        """Get default logger."""
        import logging
        return logging.getLogger(__name__)

    def _make_request(self, action: str, payload: str,
                     headers: Dict[str, str] = None) -> Optional[str]:
        """
        Make SOAP request with retry logic.

        Args:
            action: SOAP action name
            payload: SOAP request payload
            headers: Additional headers

        Returns:
            Response text or None on failure
        """
        if headers is None:
            headers = {}

        # Add SOAPAction header
        headers["SOAPAction"] = action

        # Merge with session headers
        request_headers = self.session.headers.copy()
        request_headers.update(headers)

        for attempt in range(self.retry_count):
            try:
                self._last_request_time = datetime.now()
                self._request_count += 1

                self.logger.debug(
                    f"SOAP POST base_url={self.base_url} action={action} attempt={attempt + 1}/{self.retry_count}"
                )

                response = self.session.post(
                    self.base_url,
                    data=payload,
                    headers=request_headers,
                    timeout=self.timeout,
                    verify=False  # SSL verification disabled for simplicity
                )

                self.logger.debug(f"SOAP request to {action} - Status: {response.status_code}")

                if response.status_code == 200:
                    return response.text
                elif response.status_code == 500:
                    # Server error - might be recoverable
                    self.logger.warning(f"Server error (500) for {action}, attempt {attempt + 1}")
                else:
                    self.logger.error(f"HTTP {response.status_code} for {action}")

            except requests.exceptions.Timeout:
                self.logger.warning(f"Timeout for {action}, attempt {attempt + 1}")
            except requests.exceptions.ConnectionError as e:
                self.logger.warning(f"Connection error for {action}, attempt {attempt + 1}: {e}")
            except Exception as e:
                self.logger.error(f"Request failed for {action}: {e}", exc_info=True)

            # Wait before retry
            if attempt < self.retry_count - 1:
                time.sleep(self.retry_delay * (attempt + 1))

        return None

    def _parse_soap_response(self, soap_response: str, response_tag: str) -> Optional[Dict[str, Any]]:
        """
        Parse SOAP response.

        Args:
            soap_response: SOAP response XML
            response_tag: Response tag name

        Returns:
            Parsed dictionary or None
        """
        if not soap_response:
            return None

        try:
            root = ET.fromstring(soap_response)

            # Find the response element
            return_element = root.find(f'.//ns1:{response_tag}Response/return', self.namespaces)

            if return_element is None:
                # Try without namespace
                return_element = root.find(f'.//{response_tag}Response/return')

            if return_element is None:
                self.logger.warning(f"No return element found for {response_tag}")
                return None

            # Parse items
            items = return_element.findall('item', self.namespaces)
            if not items:
                # Try without namespace
                items = return_element.findall('item')

            if not items:
                # Single value response
                return {'message': return_element.text or 'Success'}

            if response_tag == "getBreakTypes":
                return {"break_types": [item.text or '' for item in items]}

            # Key-value response
            # First item contains comma-separated keys
            keys_text = items[0].text or ''
            keys = [k.strip() for k in keys_text.split(',') if k.strip()]

            # Remaining items are values
            values = [item.text or '' for item in items[1:]]

            result = {}
            for i in range(min(len(keys), len(values))):
                result[keys[i]] = values[i]

            return result

        except ET.ParseError as e:
            self.logger.error(f"XML parse error for {response_tag}: {e}")
            self.logger.debug(f"Response preview: {soap_response[:200]}...")
            return None
        except Exception as e:
            self.logger.error(f"Error parsing {response_tag} response: {e}")
            return None

    def _build_soap_envelope(self, method: str, parameters: Dict[str, str]) -> str:
        """
        Build SOAP envelope.

        Args:
            method: SOAP method name
            parameters: Method parameters

        Returns:
            SOAP envelope XML
        """
        param_xml = ''
        for key, value in parameters.items():
            param_xml += f'<{key}>{value}</{key}>\n'

        return f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope 
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:web="https://worktre.com/">
   <soapenv:Header/>
   <soapenv:Body>
      <web:{method}>
         {param_xml}
      </web:{method}>
   </soapenv:Body>
</soapenv:Envelope>'''

    # ==================== AUTHENTICATION ====================

    @log_operation("User Login")
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        Login to WorkTre.

        Args:
            username: Employee account/username
            password: Password

        Returns:
            Response dictionary with status and data
        """
        try:
            computer_name = socket.gethostname()
            ip_address = get_dynamic_ip() or ""

            parameters = {
                "employeeaccount": username,
                "password": password,
                "ComputerName": computer_name,
                "wtversion": settings.APP_VERSION,
                "ipaddress": ip_address
            }

            payload = self._build_soap_envelope("login", parameters)
            response = self._make_request(self.action_builder.login(), payload)

            if not response:
                return {
                    "status": False,
                    "msg": constants.ERROR_NETWORK,
                    "data": {}
                }

            result = self._parse_soap_response(response, "login")
            if not result:
                return {
                    "status": False,
                    "msg": constants.ERROR_SERVER,
                    "data": {}
                }

            # Check for specific errors
            if result.get("invalidCredentials") == "0":
                return {
                    "status": False,
                    "msg": constants.ERROR_CREDENTIALS,
                    "data": {}
                }

            if result.get("IPAddresNotFound") == "Invalid IP Address":
                return {
                    "status": False,
                    "error": "ip",
                    "msg": "Invalid IP Address. Please contact administrator.",
                    "data": result
                }

            # Check system change status
            if result.get("SystemChangeStatus") == "1":
                return {
                    "status": False,
                    "msg": "System configuration change detected. Please restart.",
                    "data": result
                }

            # Success
            self._user_info = result
            self._logged_in = True

            self.logger.info(f"Login successful for user: {username}")
            return {
                "status": True,
                "data": result,
                "msg": constants.SUCCESS_LOGIN
            }

        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            return {
                "status": False,
                "msg": constants.ERROR_UNKNOWN,
                "data": {"error": str(e)}
            }

    @log_operation("User Logout")
    def logout(self, user_id: str, eod: str = "0",
               total_chats: str = "0", total_billable_chats: str = "0") -> Dict[str, Any]:
        """
        Logout from WorkTre.

        Args:
            user_id: User ID
            eod: End of day flag (0/1)
            total_chats: Total chats count
            total_billable_chats: Total billable chats count

        Returns:
            Response dictionary
        """
        parameters = {
            "userid": user_id,
            "eod": eod,
            "totalchats": total_chats,
            "totalbillablechats": total_billable_chats
        }

        payload = self._build_soap_envelope("logout", parameters)
        response = self._make_request(self.action_builder.logout(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "logout")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        self._user_info = None
        self._logged_in = False

        self.logger.info(f"Logout successful for user: {user_id}")
        return {"status": True, "data": result, "msg": constants.SUCCESS_LOGOUT}

    # ==================== BREAK MANAGEMENT ====================

    @log_operation("Start Break")
    def breakin(self, user_id: str, break_type: str, comments: str = "",
                training_type_id: str = "", trainer_id: str = "",
                website: str = "", ticket_no: str = "",
                expected_duration: str = "") -> Dict[str, Any]:
        """
        Start a break.

        Args:
            user_id: User ID
            break_type: Type of break
            comments: Comments
            training_type_id: Training type ID (for training breaks)
            trainer_id: Trainer ID (for training breaks)
            website: Website (for web-related breaks)
            ticket_no: Ticket number
            expected_duration: Expected duration

        Returns:
            Response dictionary
        """
        computer_name = socket.gethostname()

        parameters = {
            "userid": user_id,
            "breaktype": break_type,
            "comments": comments,
            "system_name": computer_name,
            "training_type_id": training_type_id,
            "trainer_id": trainer_id,
            "website": website,
            "ticket_no": ticket_no,
            "expected_duration": expected_duration
        }

        payload = self._build_soap_envelope("breakin", parameters)
        response = self._make_request(self.action_builder.breakin(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "breakin")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        self.logger.info(f"Break started: {break_type} for user {user_id}")
        return {"status": True, "data": result, "msg": constants.SUCCESS_BREAK_START}

    @log_operation("End Break")
    def breakout(self, user_id: str, break_type: str, comments: str = "") -> Dict[str, Any]:
        """
        End a break.

        Args:
            user_id: User ID
            break_type: Type of break
            comments: Comments

        Returns:
            Response dictionary
        """
        parameters = {
            "userid": user_id,
            "breaktype": break_type,
            "comments": comments
        }

        payload = self._build_soap_envelope("breakout", parameters)
        response = self._make_request(self.action_builder.breakout(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "breakout")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        self.logger.info(f"Break ended: {break_type} for user {user_id}")
        return {"status": True, "data": result, "msg": constants.SUCCESS_BREAK_END}

    # ==================== INACTIVITY MANAGEMENT ====================

    @log_operation("Report Inactivity")
    def inactivity(self, user_id: str, break_type: str = constants.BREAK_TYPE_INACTIVITY) -> Dict[str, Any]:
        """
        Report inactivity.

        Args:
            user_id: User ID
            break_type: Break type (default: inactivity)

        Returns:
            Response dictionary
        """
        parameters = {
            "userid": user_id,
            "breaktype": break_type
        }

        payload = self._build_soap_envelope("inactivity", parameters)
        response = self._make_request(self.action_builder.inactivity(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "inactivity")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        return {"status": True, "data": result}

    @log_operation("Logout Inactivity")
    def logout_inactivity(self, user_id: str, break_type: str = constants.BREAK_TYPE_INACTIVITY) -> Dict[str, Any]:
        """
        Logout due to inactivity.

        Args:
            user_id: User ID
            break_type: Break type

        Returns:
            Response dictionary
        """
        parameters = {
            "userid": user_id,
            "breaktype": break_type
        }

        payload = self._build_soap_envelope("logoutinactivity", parameters)
        response = self._make_request(self.action_builder.logoutinactivity(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "logoutinactivity")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        self._logged_in = False
        self._user_info = None

        return {"status": True, "data": result}

    @log_operation("Crash Login")
    def crash_login(self, user_id: str, break_type: str, on_break: str) -> Dict[str, Any]:
        """
        Handle crash login.

        Args:
            user_id: User ID
            break_type: Break type
            on_break: On break status

        Returns:
            Response dictionary
        """
        computer_name = socket.gethostname()
        ip_address = get_dynamic_ip() or ""

        parameters = {
            "userid": user_id,
            "breaktype": break_type,
            "onbreak": on_break,
            "ComputerName": computer_name,
            "wtversion": settings.APP_VERSION,
            "ipaddress": ip_address
        }

        payload = self._build_soap_envelope("crashlogin", parameters)
        response = self._make_request(self.action_builder.crashlogin(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "crashlogin")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        return {"status": True, "data": result}

    @log_operation("Update Last Activity")
    def last_activity_date(self, user_id: str, break_flag: str = "False",
                           idle_time_start: str = "", idle_time_end: str = "") -> Dict[str, Any]:
        """
        Update last activity date with debounce to prevent duplicate calls.

        Args:
            user_id: User ID
            break_flag: Break flag
            idle_time_start: Idle time start
            idle_time_end: Idle time end

        Returns:
            Response dictionary
        """

        # Add debounce - don't call if called very recently
        current_time = time.time()
        debounce_seconds = 10  # Minimum seconds between calls

        # Create a unique key for this user to track per-user last call time
        if not hasattr(self, '_last_activity_calls'):
            self._last_activity_calls = {}

        last_call = self._last_activity_calls.get(user_id, 0)
        time_since_last = current_time - last_call

        if time_since_last < debounce_seconds:
            print(f"⚠️ LAST ACTIVITY SKIPPED - EID: {user_id}, Only {time_since_last:.1f}s since last call (debounce)")
            return {
                "status": True,
                "msg": "Skipped (debounce)",
                "skipped": True,
                "time_since_last": time_since_last
            }

        # Update last call time
        self._last_activity_calls[user_id] = current_time

        # Log the call with timestamp
        print(f"📞 LAST ACTIVITY CALLED - EID: {user_id}, Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Optional: Log call stack for debugging (uncomment if needed)
        # import traceback
        # print(f"📞 Call stack: {''.join(traceback.format_stack()[:-2])}")

        try:
            parameters = {
                "userid": user_id,
                "breakflag": break_flag,
                "idle_time_start": idle_time_start,
                "idle_time_end": idle_time_end
            }

            self.logger.debug(f"Last activity date parameters: {parameters}")

            payload = self._build_soap_envelope("lastactivitydate", parameters)
            response = self._make_request(self.action_builder.lastactivitydate(), payload)

            if not response:
                self.logger.error("Last activity date failed: No response from server")
                return {"status": False, "msg": constants.ERROR_NETWORK}

            result = self._parse_soap_response(response, "lastactivitydate")
            if not result:
                self.logger.error("Last activity date failed: Failed to parse response")
                return {"status": False, "msg": constants.ERROR_SERVER}

            self.logger.debug(f"Last activity date successful for user {user_id}")
            return {"status": True, "data": result}

        except socket.error as e:
            self.logger.error(f"Network error in last_activity_date: {e}")
            return {"status": False, "msg": f"Network error: {str(e)}"}

        except Exception as e:
            self.logger.error(f"Unexpected error in last_activity_date: {e}")
            import traceback
            traceback.print_exc()
            return {"status": False, "msg": str(e)}

    # ==================== SERVICE MANAGEMENT ====================

    @log_operation("Get Service")
    def get_service(self, user_id: str) -> Dict[str, Any]:
        """
        Get service configuration.

        Args:
            user_id: User ID

        Returns:
            Response dictionary
        """
        parameters = {
            "userid": user_id
        }

        payload = self._build_soap_envelope("getservice", parameters)
        response = self._make_request(self.action_builder.getservice(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "getservice")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        return {"status": True, "data": result}

    # ==================== BREAK TYPES ====================

    @log_operation("Get Break Types")
    def get_break_types(self, user_id: str) -> Dict[str, Any]:
        """
        Get available break types.

        Args:
            user_id: User ID

        Returns:
            Response dictionary with formatted break types
        """
        parameters = {
            "id": user_id
        }

        payload = self._build_soap_envelope("getBreakTypes", parameters)
        response = self._make_request(self.action_builder.getBreakTypes(), payload)

        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        result = self._parse_soap_response(response, "getBreakTypes")
        if not result:
            return {"status": False, "msg": constants.ERROR_SERVER}

        # Format break types
        break_types = result.get("break_types", [])
        formatted_breaks = []

        # Skip first element (usually header)
        for i in range(1, len(break_types), 3):
            if i + 2 < len(break_types):
                formatted_breaks.append({
                    "id": break_types[i],
                    "break_type": break_types[i + 1],
                    "status": break_types[i + 2]
                })

        return {
            "status": True,
            "data": {"break_types": formatted_breaks}
        }

    # ==================== ACCESS REQUEST ====================

    @log_operation("Request Access")
    def request_access(self, user_id: str) -> Dict[str, Any]:
        """
        Request access.

        Args:
            user_id: User ID

        Returns:
            Response dictionary
        """
        ip_address = get_dynamic_ip() or ""

        parameters = {
            "userid": user_id,
            "ipaddress": ip_address
        }

        payload = self._build_soap_envelope("requestforaccess", parameters)
        response = self._make_request(self.action_builder.requestforaccess(), payload)

        if not response:
            # Return IP address even if request fails
            return {"status": True, "data": {"ip": ip_address}}

        result = self._parse_soap_response(response, "requestforaccess")
        if not result:
            return {"status": True, "data": {"ip": ip_address}}

        return {"status": True, "data": result}

    # ==================== VERSION CHECK ====================

    @log_operation("Check Version")
    def version_check(self) -> Dict[str, Any]:
        """
        Check for updates.

        Returns:
            Response dictionary with version information
        """
        headers = {
            "SOAPAction": self.action_builder.versioncheck(),
        }

        payload = '''<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope 
            xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
            xmlns:xsd="http://www.w3.org/2001/XMLSchema">
           <soapenv:Body>
              <ns1:versioncheck 
                  soapenv:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"
                  xmlns:ns1="https://worktre.com/"/>
           </soapenv:Body>
        </soapenv:Envelope>'''

        response = self._make_request(self.action_builder.versioncheck(), payload, headers)
        if not response:
            return {"status": False, "msg": constants.ERROR_NETWORK}

        try:
            root = ET.fromstring(response)

            # Try different paths for items
            items = root.findall(".//{https://worktre.com/}versioncheckResponse/return/item")
            if not items:
                items = root.findall(".//return/item")
            if not items:
                items = root.findall(".//item")

            values = [item.text for item in items if item.text]

            if len(values) >= 7:
                version_info = {
                    "id": values[0],
                    "version": values[1],
                    "platform": values[2],
                    "download_url": values[3],
                    "active": values[4],
                    "description": values[5],
                    "release_date": values[6],
                }
                return {"status": True, "data": version_info}
            else:
                return {
                    "status": False,
                    "msg": "Incomplete version data",
                    "data": {"raw_items": values}
                }

        except ET.ParseError as e:
            self.logger.error(f"Failed to parse version check response: {e}")
            return {"status": False, "msg": constants.ERROR_SERVER}
        except Exception as e:
            self.logger.error(f"Version check error: {e}")
            return {"status": False, "msg": constants.ERROR_UNKNOWN}

    # ==================== UTILITY METHODS ====================

    def is_logged_in(self) -> bool:
        """Check if user is logged in."""
        return self._logged_in and self._user_info is not None

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """Get current user info."""
        return self._user_info.copy() if self._user_info else None

    def get_user_id(self) -> Optional[str]:
        """Get current user ID."""
        if self._user_info:
            return self._user_info.get("EID") or self._user_info.get("user_id")
        return None

    def clear_user_info(self):
        """Clear user info."""
        self._user_info = None
        self._logged_in = False

    def test_connection(self) -> Tuple[bool, float]:
        """
        Test connection to SOAP server.

        Returns:
            Tuple of (success, response_time_ms)
        """
        start_time = time.time()

        try:
            response = self.session.get(self.base_url, timeout=5)
            response_time = (time.time() - start_time) * 1000
            return response.status_code < 500, response_time
        except Exception:
            response_time = (time.time() - start_time) * 1000
            return False, response_time

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "logged_in": self._logged_in,
            "user_id": self.get_user_id(),
            "base_url": self.base_url,
            "request_count": self._request_count,
            "last_request": self._last_request_time.isoformat() if self._last_request_time else None,
            "timeout": self.timeout,
            "retry_count": self.retry_count
        }