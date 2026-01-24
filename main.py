from inactivity_manager import start_inactivity_timer, stop_inactivity_timer, reset_idle_timer
from connectivity_monitor import start_connectivity_monitor
from system_monitor import start_monitor
from tray_manager import TrayManager
from notification_manager import NotificationManager
import webview
import tkinter as tk
import subprocess
import sys
import os
import math
import ssl
import logging
import requests
import socket
import json
import portalocker
import tempfile
import base64
import time
import threading
import shutil
import xml.etree.ElementTree as ET
from PIL import ImageGrab
from io import BytesIO
from cryptography.fernet import Fernet
from packaging import version
from urllib.request import urlopen, Request
import queue

try:
    from plyer import notification

    WINDOWS_NOTIFICATIONS_AVAILABLE = True
except ImportError:
    WINDOWS_NOTIFICATIONS_AVAILABLE = False
    print("Windows notifications not available. Install plyer: pip install plyer")

# Global variables
is_updating = False
should_confirm_close = True
tray_manager = None
notification_manager = None
current_window = None
logged_in_user_info = None
interval_timer = None
interval_lock = threading.Lock()
repeat_interval_seconds = 0  # To store and reuse duration
is_running = False  # Track whether timer is active

RESTORE_REQUESTED = False

if len(sys.argv) > 1:
    for arg in sys.argv:
        if "worktre://restore" in arg:
            RESTORE_REQUESTED = True

# === Single Instance Lock ===
LOCK_FILE = os.path.join(tempfile.gettempdir(), "mywebviewapp.lock")
APPDATA = os.path.join(os.environ.get("APPDATA", "."), "WorkTre")
os.makedirs(APPDATA, exist_ok=True)

# Save important files inside APPDATA path
STORAGE_PATH = os.path.join(APPDATA, 'remember_me.json')
KEY_PATH = os.path.join(APPDATA, 'remember_me.key')

# Logging setup
log_path = os.path.join(APPDATA, "log.txt")
logging.basicConfig(
    filename=log_path,
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    filemode="a"
)
logger = logging.getLogger(__name__)
logger.info("🚀 App started")

# URLs
UPDATE_URL = "https://raw.githubusercontent.com/WorkTre/WorkTre-Desktop-App/main/version.json"
SOAP_BASE_URL = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def get_local_version():
    try:
        version_path = resource_path("version.txt")
        if os.path.exists(version_path):
            with open(resource_path("version.txt")) as f:
                version_text = f.read().strip()
                print("version_text:", version_text)
                return version_text;
        else:
            logger.warning("version.txt not found, using default version")
            return "1.0.1"  # Default fallback
    except Exception as e:
        logger.error(f"Error reading version: {e}")
        return "1.0.1"  # Default fallback


def install_update(installer_path):
    subprocess.Popen(installer_path)
    sys.exit()


def check_for_updates():
    try:
        response = requests.get(UPDATE_URL, timeout=5)
        response.raise_for_status()

        data = response.json()
        remote_version = data["version"]
        download_url = data["download_url"]

        if version.parse(remote_version) > version.parse(APP_VERSION):
            return {
                "update": True,
                "latest_version": remote_version,
                "download_url": download_url
            }

    except Exception as e:
        print("Update check failed:", e)

    return {"update": False}


# format: major.minor.build.revision
APP_VERSION = get_local_version()
UPDATE_INFO = check_for_updates()

# Import after APP_VERSION is defined
from soap_actions import SOAPActionBuilder

soap_actions = SOAPActionBuilder(SOAP_BASE_URL)

if UPDATE_INFO["update"]:
    print("Update available:", UPDATE_INFO["latest_version"])


def download_file_with_progress(SOAP_BASE_URL, filepath, window, latest_version):
    """Download file with progress tracking"""
    try:
        # Disable SSL verification for simplicity (adjust as needed)
        ssl_context = ssl._create_unverified_context()

        # Open the URL
        req = Request(SOAP_BASE_URL, headers={'User-Agent': 'Mozilla/5.0'})
        response = urlopen(req, context=ssl_context)

        # Get file size
        total_size = int(response.headers.get('Content-Length', 0))
        block_size = 8192  # 8KB chunks

        logger.info(f"Downloading {SOAP_BASE_URL} (Size: {total_size} bytes)")

        downloaded = 0
        with open(filepath, 'wb') as file:
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break

                file.write(buffer)
                downloaded += len(buffer)

                # Calculate progress percentage
                if total_size > 0:
                    percentage = (downloaded / total_size) * 100
                else:
                    percentage = 0

                # Update progress in the UI
                try:
                    window.evaluate_js(f"""
                        updateDownloadProgress({percentage:.2f});
                    """)
                except:
                    pass

                logger.debug(f"Downloaded: {downloaded}/{total_size} bytes ({percentage:.1f}%)")

        logger.info(f"Download complete: {downloaded} bytes")
        return True

    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def download_and_install_update(download_url, latest_version):
    """Download the installer with progress and run it"""
    global is_updating

    try:
        if not webview.windows:
            return

        window = webview.windows[0]
        is_updating = True  # Set flag

        # Create a temporary directory for the installer
        temp_dir = tempfile.mkdtemp()
        installer_path = os.path.join(temp_dir, "WorkTreInstaller.exe")

        # Download the installer with progress tracking
        logger.info(f"Downloading update from {download_url}")

        success = download_file_with_progress(
            download_url,
            installer_path,
            window,
            latest_version
        )

        if not success:
            is_updating = False  # Reset flag on error
            raise Exception("Download failed. Please check your internet connection.")

        # Download complete - show 100%
        window.evaluate_js("""
            updateDownloadProgress(100);
        """)

        logger.info(f"Download complete. Installing version {latest_version}")

        # Give user a moment to see completion
        time.sleep(2)

        # Now close the window - should bypass confirmation
        window.destroy()

        # Run the installer
        subprocess.Popen([installer_path], shell=True)

        # Exit the application
        sys.exit(0)

    except Exception as e:
        is_updating = False  # Reset flag on error
        logger.error(f"Update failed: {e}")
        # Show error message
        if webview.windows:
            show_update_error(str(e))
        # Clean up temp directory
        try:
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass


# Add this function for showing error dialogs
def show_update_error(error_message):
    """Show professional error dialog"""
    try:
        if webview.windows:
            window = webview.windows[0]
            window.evaluate_js(f"""
                (function() {{
                    // Remove existing modal if present
                    const existingModal = document.getElementById('updateErrorModal');
                    if (existingModal) {{
                        document.body.removeChild(existingModal);
                    }}

                    // Create error modal
                    const modal = document.createElement('div');
                    modal.id = 'updateErrorModal';
                    modal.style.cssText = `
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(231, 76, 60, 0.1);
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        z-index: 99999;
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    `;

                    const dialog = document.createElement('div');
                    dialog.style.cssText = `
                        background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                        padding: 2px;
                        border-radius: 12px;
                        box-shadow: 0 10px 40px rgba(231, 76, 60, 0.3);
                        max-width: 450px;
                        width: 90%;
                        overflow: hidden;
                    `;

                    const content = document.createElement('div');
                    content.style.cssText = `
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        text-align: center;
                    `;

                    content.innerHTML = `
                        <!-- Error Icon -->
                        <div style="
                            width: 70px;
                            height: 70px;
                            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                            border-radius: 50%;
                            margin: 0 auto 20px auto;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                        ">
                            <svg width="35" height="35" viewBox="0 0 24 24" fill="white">
                                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                            </svg>
                        </div>

                        <!-- Title -->
                        <h3 style="margin: 0 0 15px 0; color: #2c3e50; font-size: 22px; font-weight: 600;">
                            Update Failed
                        </h3>

                        <!-- Error Message -->
                        <div style="
                            background: #ffeaea;
                            border-radius: 8px;
                            padding: 15px;
                            margin: 20px 0;
                            text-align: left;
                            border-left: 4px solid #e74c3c;
                        ">
                            <p style="margin: 0; color: #c0392b; font-size: 14px; line-height: 1.5;">
                                {error_message}
                            </p>
                        </div>

                        <!-- Action Button -->
                        <button onclick="document.body.removeChild(this.parentElement.parentElement.parentElement)" 
                                style="
                                    background: #e74c3c;
                                    color: white;
                                    border: none;
                                    padding: 12px 30px;
                                    border-radius: 6px;
                                    cursor: pointer;
                                    font-size: 15px;
                                    font-weight: 600;
                                    transition: all 0.3s ease;
                                    margin-top: 10px;
                                ">
                            Close
                        </button>

                        <!-- Try Again Suggestion -->
                        <div style="margin-top: 20px; color: #95a5a6; font-size: 13px;">
                            You can try updating again from the Help menu
                        </div>
                    `;

                    dialog.appendChild(content);
                    modal.appendChild(dialog);
                    document.body.appendChild(modal);

                    // Add hover effect
                    const style = document.createElement('style');
                    style.textContent = `
                        button:hover {{
                            background: #c0392b;
                            transform: translateY(-2px);
                            box-shadow: 0 4px 15px rgba(231, 76, 60, 0.4);
                        }}
                        button:active {{
                            transform: translateY(1px);
                        }}
                    `;
                    document.head.appendChild(style);
                }})();
            """)
    except Exception as e:
        logger.error(f"Error showing error dialog: {e}")


def restore_main_window():
    global current_window

    if not current_window:
        return

    current_window.show()
    current_window.restore()

    try:
        current_window.bring_to_front()
        current_window.focus()
    except:
        pass


try:
    lock_handle = open(LOCK_FILE, 'w')
    # Try to acquire a non-blocking exclusive lock
    portalocker.lock(lock_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
except portalocker.exceptions.LockException:
    sys.exit(0)


def cleanup_temp_dir():
    temp_path = os.path.join(os.getcwd(), 'webview_temp')
    try:
        shutil.rmtree(temp_path, ignore_errors=True)
    except Exception:
        pass


cleanup_temp_dir()


def get_dynamic_ip():
    try:
        # Connect to an external host to determine the IP address
        # This does not establish an actual connection
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # Google's public DNS server
            ip = s.getsockname()[0]

        return ip
    except Exception as e:
        print(f"Error getting IP address: {e}")
        return None


# ---------------------- Your JS API ----------------------

def get_key_path():
    # Get a safe writable directory
    base_dir = os.path.expanduser("~\\AppData\\Roaming\\WorkTre")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "remember_me.key")


def load_key():
    try:
        key_path = get_key_path()  # ✅ This ensures we use AppData path

        if not os.path.exists(key_path):
            key = Fernet.generate_key()
            with open(key_path, 'wb') as f:
                f.write(key)
        else:
            with open(key_path, 'rb') as f:
                key = f.read()

        return Fernet(key)

    except Exception as e:
        print("[ERROR] Failed to load or create key:", e)
        return None


# Load it on start
fernet = load_key()


def save_remembered_user(email, password):
    try:
        if email and password:
            encrypted = fernet.encrypt(password.encode()).decode()

            # Ensure the directory exists (safe if called multiple times)
            os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)

            # Save encrypted data
            with open(STORAGE_PATH, 'w') as f:
                json.dump({"email": email, "password": encrypted}, f)
            logger.info("Remembered user saved successfully.")
        elif os.path.exists(STORAGE_PATH):
            os.remove(STORAGE_PATH)
            logger.info("Remembered user file deleted.")
    except Exception as e:
        logger.error(f"Error saving remembered user: {e}")


def get_remembered_user():
    try:
        if os.path.exists(STORAGE_PATH):
            with open(STORAGE_PATH, 'r') as f:
                data = json.load(f)
                data['password'] = fernet.decrypt(data['password'].encode()).decode()
                logger.info("Remembered user loaded successfully.")
                return data
    except Exception as e:
        logger.error(f"Error reading remembered user: {e}")
    return {}


def on_warning():
    try:
        if webview.windows:
            webview.windows[0].evaluate_js("showInactivityWarningModal();")
            # Show combined notification
            notification_manager.show_professional_notification(
                "⏰ Inactivity Warning",
                f"You will be logged out soon due to inactivity",
                "warning",
                5
            )
    except Exception as e:
        with open("warn.log", "a", encoding="utf-8") as f:
            f.write(f"Error showing modal: {e}\n")


def on_exit():
    if webview.windows:
        webview.windows[0].evaluate_js("inactivityTimeExceed()")
        # Show Windows notification for logout
        notification_manager.show_professional_notification(
            "🔒 Logged Out Due to Inactivity",
            "You have been logged out due to inactivity",
            "info",
            10
        )
        API.clear_app_data()


# ************************** crash inactivity timer *************************

def on_interval_complete():
    global interval_timer, is_running, logged_in_user_info

    with interval_lock:
        interval_timer = None
        if is_running and repeat_interval_seconds > 0:

            if logged_in_user_info is not None:
                API.lastactivitydate(logged_in_user_info["EID"], "False", "", "")

                if logged_in_user_info["ScreenShotStatus"] == "1":
                    API.take_screenshot_with_pillow(logged_in_user_info["EID"])

            interval_timer = threading.Timer(repeat_interval_seconds, on_interval_complete)
            interval_timer.start()


def start_get_service_interval(duration=300):
    """
    Start the repeating interval.
    :param duration: Duration in seconds. If 0 or less, timer won't start.
    """
    global interval_timer, repeat_interval_seconds, is_running

    with interval_lock:
        if duration <= 0:
            return

        if is_running:
            return

        repeat_interval_seconds = duration
        is_running = True
        interval_timer = threading.Timer(duration, on_interval_complete)
        interval_timer.start()

        # Human-friendly message
        minutes = duration / 60
        if minutes >= 1:
            print(f"Repeating interval started for {minutes:.2f} minutes.")
        else:
            print(f"Repeating interval started for {duration:.0f} seconds.")


def stop_interval():
    global interval_timer, is_running

    with interval_lock:
        if interval_timer is not None:
            interval_timer.cancel()
            interval_timer = None
        is_running = False


class API:
    def close_app(self):
        sys.exit()

    def __init__(self):
        self._monitor_thread = None
        self._stop_monitor = threading.Event()
        self._user_logged_in = False

        self.user_info = None
        self.break_type = ""

        # Timeouts (in seconds)
        self._warn_after = None
        self._kick_after = None
        self._warned = False
        self.app_version = APP_VERSION

        self.maximum_inactivity_logoutTime = 60  # minutes

    def get_app_version(self):
        try:
            version_text = get_local_version()
            return version_text
        except Exception as e:
            logger.error(f"Error reading version: {e}")
            return "1.0.1"  # Default fallback

    def downloadUpdate(self, download_url, latest_version):
        """Handle update download and installation"""
        try:
            # Start the update process in a separate thread
            import threading
            update_thread = threading.Thread(
                target=download_and_install_update,
                args=(download_url, latest_version),
                daemon=True
            )
            update_thread.start()
            return {"status": True, "message": "Update started"}
        except Exception as e:
            logger.error(f"Failed to start update: {e}")
            # Show error in UI
            try:
                if webview.windows:
                    webview.windows[0].evaluate_js(f"""
                        alert('Failed to start update: {str(e)}');
                    """)
            except:
                pass
            return {"status": False, "message": f"Update failed: {str(e)}"}

    def notify_no_connection(self):
        if webview.windows:
            webview.windows[0].evaluate_js("onInternetDisconnectedTimeExceed();")
            # Show Windows notification
            notification_manager.show_professional_notification(
                "🌐 Connection Lost",
                "Internet connection interrupted. Reconnecting...",
                "connection",
                8
            )

    def notify_online(self):
        # Show Windows notification for reconnection
        notification_manager.show_professional_notification(
            "🌐 Connection Restored",
            "Internet connection has been restored",
            "connection",
            5
        )
        # Also show in-app notification
        # show_notification("Connection Restored", "Internet connection has been restored", "success", 3000)
        pass

    def manually_call_lastInactivity(self, breakFlag):
        global logged_in_user_info
        if logged_in_user_info is not None:
            start_get_service_interval()
            self.start_inactivity()
            API.lastactivitydate(logged_in_user_info["EID"], breakFlag, "", "")

    def notify_offline(self):
        stop_interval()
        stop_inactivity_timer()

    def is_user_logged_in(self):
        return self.user_info is not None

    def get_remembered_user(self):
        return get_remembered_user()

    def save_remembered_user(self, email, password):
        save_remembered_user(email, password)

    def show_login_success_notification(self, username):
        """Show login success notification - called from JavaScript after crash reason is handled"""
        try:
            notification_manager.show_professional_notification(
                "✅ Login Successful",
                f"{username}, Welcome back! You are now logged in",
                "success",
                5
            )
            return {"status": True, "message": "Notification shown"}
        except Exception as e:
            logger.error(f"Error showing login success notification: {e}")
            return {"status": False, "message": str(e)}

    def login(self, username, password, max_retries=2, delay=2):
        global logged_in_user_info
        logging.info("login")

        # Show loading notification
        # show_notification("Logging In", "Please wait while we authenticate...", "info", 2000)

        computer_name = socket.gethostname()
        ip = get_dynamic_ip()
        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": soap_actions.login(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:login>
                 <employeeaccount>{username}</employeeaccount>
                 <password>{password}</password>
                 <ComputerName>{computer_name}</ComputerName>
                 <wtversion>{self.app_version}</wtversion>
                 <ipaddress>{ip}</ipaddress>
              </web:login>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        try:
            # Send the POST request
            response = requests.post(SOAP_BASE_URL, data=payload, headers=headers,
                                     timeout=10)  # Timeout set to 10 seconds

            if response.status_code == 200:
                soap_response = response.text
                user_info = self.process_soap_response(soap_response)
                parsed = json.loads(user_info)

                # Ensure user_info is properly set
                self.user_info = parsed.get("data", {})
                if not self.user_info:
                    logger.error("Login succeeded but user_info is empty")
                    return json.dumps({"status": False, "msg": "Invalid user data", "data": {}})

                logged_in_user_info = parsed["data"]
                data = parsed["data"]

                if data and isinstance(data, dict):
                    if data.get("SystemChangeStatus") == "1":
                        resp = {"status": False, "data": data}
                        # Show Windows error notification
                        notification_manager.show_professional_notification(
                            "❌ Login Failed",
                            "System configuration change detected",
                            "error",
                            5
                        )
                        return json.dumps(resp)

                return user_info
            else:
                raise requests.exceptions.RequestException(f"Unexpected status code: {response.status_code}")

        except (requests.exceptions.RequestException, requests.exceptions.Timeout) as e:
            # Print the error and wait before retrying
            time.sleep(delay)
            delay *= 2  # Exponential backoff (increase the delay after each attempt)

        # If we reach here, all retry attempts failed
        return json.dumps(
            {"status": False, "msg": "Unable to connect to the server. Network Error.", "data": {}})

    def start_app_intervals(self, data):
        if not self.is_user_logged_in():
            return

        start_get_service_interval()
        self.start_inactivity()

        start_connectivity_monitor(API(), int(data.get("DisconnectLogoutTime")) * 60)

        self.lastactivitydate(data.get("EID"), "False", "", "")

    @staticmethod
    def take_screenshot_with_pillow(user_id):
        """
        Take and upload a screenshot to the server.
        Used for activity monitoring.
        """
        try:
            # Take a screenshot silently
            screenshot = ImageGrab.grab()

            # Convert to Base64
            buffer = BytesIO()
            screenshot.save(buffer, format="PNG")
            base64_string = base64.b64encode(buffer.getvalue()).decode("utf-8")
            buffer.close()

            # Upload to server
            URL = f"https://worktre.com/ss_upload/index?userid={user_id}"
            payload = {
                "userid": user_id,
                "file": base64_string
            }
            requests.post(URL, data=payload, timeout=10)
        except:
            pass

    def process_soap_response(self, soap_response):
        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Find the 'return' element
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        return_element = root.find('.//ns1:loginResponse/return', namespaces)

        if return_element is not None:

            items = return_element.findall('item', namespaces)

            keys = items[0].text.split(",") if items[0].text else []

            keys = [key.strip() for key in keys]

            values = [item.text or "" for item in items[1:]]

            result = {}
            for i in range(len(keys)):
                key = keys[i]
                value = values[i]
                result[key] = value

            try:
                if result["invalidCredentials"] == "0":
                    resp = {"status": False, "msg": "Invalid Credentials", "data": {}}
            except:
                resp = {"status": True, "data": result}

            try:
                if result["IPAddresNotFound"] == "Invalid IP Address":
                    resp = {"status": False, "error": "ip", "msg": "[color=#0000FF][u]Click here[/u][/color]",
                            "data": result}
            except:
                resp = resp

            json_response = json.dumps(resp)

            return json_response
        else:
            resp = {"status": False, "data": {}}
            json_response = json.dumps(resp)
            return json_response

    def inactivity(self, userid, breaktype="inactivity"):
        if not self.is_user_logged_in():
            return

        computer_name = socket.gethostname()

        # Headers for the SOAP request
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/breakout/inactivity",
            "SOAPAction": soap_actions.inactivity(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:inactivity>
                 <userid>{userid}</userid>
                 <breaktype>{breaktype}</breaktype>
                 <system_name>{computer_name}</system_name>
              </web:inactivity>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Endpoint URL
        # url = f"{SOAP_BASE_URL}/breakout"

        # Send the POST request
        try:
            response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

            soap_response = response.text

        except requests.exceptions.RequestException as e:
            # Show error notification
            notification_manager.show_professional_notification(
                "❌ Inactivity Break Failed",
                "Could not mark inactivity break",
                "error",
                5
            )
            return json.dumps({"status": False, "msg": "Request failed", "data": {"error": str(e)}})

        try:
            # Parse the SOAP response
            root = ET.fromstring(soap_response)
        except ET.ParseError:
            notification_manager.show_professional_notification(
                "❌ Inactivity Break Failed",
                "Error processing server response",
                "error",
                5
            )
            return json.dumps({"status": False, "msg": "Error parsing XML response", "data": {}})

        # Define namespaces
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
        }

        # Find the response element
        return_element = root.find('.//ns1:inactivityResponse/return', namespaces)

        if return_element is not None:
            result = {
                "message": return_element.text or "Success"
            }
            # Show Windows notification for inactivity break
            notification_manager.show_professional_notification(
                "⏸️ Inactivity Break Marked",
                "Your inactivity has been recorded. You may be logged out soon.",
                "success",
                8
            )
            return json.dumps({"status": True, "data": result})
        else:
            notification_manager.show_professional_notification(
                "❌ Inactivity Break Failed",
                "No response from server",
                "error",
                5
            )
            return json.dumps({"status": False, "msg": "No response data", "data": {}})

    def logoutinactivity(self, userid, breaktype="inactivity"):
        if not self.is_user_logged_in():
            return
        # Endpoint URL
        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/logoutinactivity",
            "SOAPAction": soap_actions.logoutinactivity(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:logoutinactivity>
                 <userid>{userid}</userid>
                 <breaktype>{breaktype}</breaktype>
              </web:logoutinactivity>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text

        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Define namespaces
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        # Find the 'return' element
        return_element = root.find('.//ns1:logoutinactivityResponse/return', namespaces)

        if return_element is not None:
            items = return_element.findall('item', namespaces)

            # Get the keys (first element)
            keys = items[0].text.split(",") if items[0].text else []

            # Strip extra spaces in keys
            keys = [key.strip() for key in keys]

            # Get the values (remaining elements)
            values = [item.text or "" for item in items[1:]]

            result = {}
            for i in range(len(keys)):
                key = keys[i]
                value = values[i]
                result[key] = value

            resp = {"status": True, "data": result}
            json_response = json.dumps(resp)
            return json_response
        else:
            resp = {"status": True, "data": {}}
            json_response = json.dumps(resp)
            return json_response

    def crashlogin(self, userid, breaktype, onbreak):
        # global app_version

        computer_name = socket.gethostname()
        ip = get_dynamic_ip()
        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/crashlogin",
            "SOAPAction": soap_actions.crashlogin(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:crashlogin>
                 <userid>{userid}</userid>
                 <breaktype>{breaktype}</breaktype>
                 <onbreak>{onbreak}</onbreak>
                 <ComputerName>{computer_name}</ComputerName>
                 <wtversion>{self.app_version}</wtversion>
                 <ipaddress>{ip}</ipaddress>
              </web:crashlogin>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text

        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Find the 'return' element
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        return_element = root.find('.//ns1:crashloginResponse/return', namespaces)

        if return_element is not None:

            items = return_element.findall('item', namespaces)

            # Get the keys (first element)
            keys = items[0].text.split(",") if items[0].text else []

            # Strip extra spaces in keys
            keys = [key.strip() for key in keys]

            # Get the values (remaining elements)
            values = [item.text or "" for item in items[1:]]

            result = {}
            for i in range(len(keys)):
                try:
                    key = keys[i]
                    value = values[i]
                    result[key] = value
                except:
                    pass

            resp = {"status": True, "data": result}
            json_response = json.dumps(resp)
            return json_response
        else:
            resp = {"status": True, "data": {}}
            json_response = json.dumps(resp)
            return json_response

    def clear_app_data(self):
        global logged_in_user_info

        self._user_logged_in = False
        logged_in_user_info = None
        self.maximize()
        stop_interval()
        stop_inactivity_timer()

    def maximize(self):
        global current_window
        current_window.restore()

    def logout(self, userid, eod, total_chats, total_billable_chats):
        if not self.is_user_logged_in():
            return

        global logged_in_user_info

        self._user_logged_in = False
        logged_in_user_info = None

        # Show Windows notification for logout
        notification_manager.show_professional_notification(
            "👋 Logged Out",
            "You have been successfully logged out from WorkTre",
            "success",
            5
        )

        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/logout",
            "SOAPAction": soap_actions.logout(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:logout>
                 <userid>{userid}</userid>
                 <eod>{eod}</eod>
                 <totalchats>{total_chats}</totalchats>
                 <totalbillablechats>{total_billable_chats}</totalbillablechats>
              </web:logout>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text
        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Find the 'return' element
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        return_element = root.find('.//ns1:logoutResponse/return', namespaces)

        stop_interval()
        stop_inactivity_timer()
        if return_element is not None:
            items = return_element.findall('item', namespaces)

            # Get the keys (first element)
            keys = items[0].text.split(",") if items[0].text else []

            # Strip extra spaces in keys
            keys = [key.strip() for key in keys]

            # Get the values (remaining elements)
            values = [item.text or "" for item in items[1:]]

            result = {}
            for i in range(len(keys)):
                key = keys[i]
                value = values[i]
                result[key] = value

            resp = {"status": True, "data": result}
            json_response = json.dumps(resp)
            # logged_in_user_info = None

            return json_response
        else:
            resp = {"status": True, "data": {}}
            json_response = json.dumps(resp)
            return json_response

    @staticmethod
    def lastactivitydate(userid, breakflag, idle_time_start, idle_time_end):

        computer_name = socket.gethostname()

        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/lastactivitydate",
            "SOAPAction": soap_actions.lastactivitydate(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:lastactivitydate>
                 <userid>{userid}</userid>
                 <breakflag>{breakflag}</breakflag>
                 <idle_time_start>{idle_time_start}</idle_time_start>
                 <idle_time_end>{idle_time_end}</idle_time_end>
                 <ComputerName>{computer_name}</ComputerName>
              </web:lastactivitydate>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Endpoint URL
        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text

        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Define namespaces
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        return_element = root.find('.//ns1:lastactivitydateResponse/return', namespaces)

        if return_element is not None:
            items = return_element.findall('item', namespaces)

            # Extract the keys (first element)
            keys = items[0].text.split(",") if items[0].text else []
            keys = [key.strip() for key in keys]

            # Extract the values (remaining elements)
            values = [item.text or "" for item in items[1:]]

            result = {}
            for i in range(len(keys)):
                key = keys[i]
                value = values[i]
                result[key] = value

            try:

                resp = {"status": True, "data": result}
            except Exception as e:
                resp = {"status": False, "msg": "Error parsing response", "data": {"error": str(e)}}
        else:
            resp = {"status": False, "msg": "No response data", "data": {}}

        json_response = json.dumps(resp)
        return json_response

    def getservice(self, userid):

        computer_name = socket.gethostname()

        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/getservice",
            "SOAPAction": soap_actions.getservice(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:getservice>
                 <userid>{userid}</userid>
                 <ComputerName>{computer_name}</ComputerName>
              </web:getservice>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Endpoint URL
        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text

        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Define namespaces
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        return_element = root.find('.//ns1:getserviceResponse/return', namespaces)

        if return_element is not None:
            items = return_element.findall('item', namespaces)

            # Extract the keys (first element)
            keys = items[0].text.split(",") if items[0].text else []
            keys = [key.strip() for key in keys]

            # Extract the values (remaining elements)
            values = [item.text or "" for item in items[1:]]

            result = {}
            for i in range(len(keys)):
                key = keys[i]
                value = values[i]
                result[key] = value

            try:

                resp = {"status": True, "data": result}
            except Exception as e:
                resp = {"status": False, "msg": "Error parsing response", "data": {"error": str(e)}}
        else:
            resp = {"status": False, "msg": "No response data", "data": {}}

        json_response = json.dumps(resp)
        return json_response

    def breakin(self, userid, breaktype, comments, training_type_id="", trainer_id="", website="", ticket_no="",
                expected_duration=""):
        if not self.is_user_logged_in():
            return

        computer_name = socket.gethostname()
        self.break_type = breaktype

        # Show loading notification
        # show_notification("Starting Break", "Please wait...", "info", 2000)

        # Headers for the SOAP request
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/breakin",
            "SOAPAction": soap_actions.breakin(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:breakin>
                 <userid>{userid}</userid>
                 <breaktype>{breaktype}</breaktype>
                 <comments>{comments}</comments>
                 <system_name>{computer_name}</system_name>
                 <training_type_id>{training_type_id}</training_type_id>
                 <trainer_id>{trainer_id}</trainer_id>
                 <website>{website}</website>
                 <ticket_no>{ticket_no}</ticket_no>
                 <expected_duration>{expected_duration}</expected_duration>
              </web:breakin>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Endpoint URL
        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text

        try:
            # Parse the SOAP response
            root = ET.fromstring(soap_response)
        except:
            root = None

        # Define namespaces
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }
        stop_inactivity_timer()
        if root is not None:

            # Find the response element
            return_element = root.find('.//ns1:breakinResponse/return', namespaces)
        else:
            return_element = None

        if return_element is not None:
            result = {
                "message": return_element.text or "Success"
            }

            try:

                resp = {"status": True, "data": result}
                # Show combined notification
                notification_manager.show_professional_notification(
                    "☕ Break Started",
                    f"{breaktype} break has been started",
                    "break",
                    5
                )
            except Exception as e:
                resp = {"status": False, "msg": "Error parsing response", "data": {"error": str(e)}}
                notification_manager.show_professional_notification(
                    "❌ Break Failed",
                    "Could not start break",
                    "error",
                    5
                )
        else:
            resp = {"status": False, "msg": "No response data", "data": {}}
            notification_manager.show_professional_notification(
                "❌ Break Failed",
                "No response from server",
                "error",
                5
            )

        json_response = json.dumps(resp)
        return json_response

    def breakout(self, userid, breaktype, comments="", inactivity=False):
        if not self.is_user_logged_in():
            return

        # Show loading notification
        # show_notification("Ending Break", "Please wait...", "info", 2000)

        # Headers for the SOAP request
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/breakout",
            "SOAPAction": soap_actions.breakout(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:breakout>
                 <userid>{userid}</userid>
                 <breaktype>{breaktype}</breaktype>
                 <comments>{comments}</comments>
              </web:breakout>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Endpoint URL
        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text

        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Define namespaces
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        # Check for breakoutResponse
        return_element = root.find('.//ns1:breakoutResponse', namespaces)

        if not inactivity:
            self.start_inactivity()

        if return_element is not None:
            result = {
                "message": "Breakout successfully processed"
            }

            try:

                resp = {"status": True, "data": result}
                # Show combined notification
                notification_manager.show_professional_notification(
                    "✅ Break Ended",
                    "You are back to work",
                    "success",
                    5
                )
            except Exception as e:
                resp = {"status": False, "msg": "Error parsing response", "data": {"error": str(e)}}
                notification_manager.show_professional_notification(
                    "❌ Break End Failed",
                    "Could not end break",
                    "error",
                    5
                )
        else:
            resp = {"status": False, "msg": "No response data", "data": {}}
            notification_manager.show_professional_notification(
                "❌ Break End Failed",
                "No response from server",
                "error",
                5
            )

        json_response = json.dumps(resp)
        return json_response

    def version_check(self):
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/versioncheck",
            "SOAPAction": soap_actions.versioncheck(),
        }

        payload = """<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                          xmlns:xsd="http://www.w3.org/2001/XMLSchema">
           <soapenv:Body>
              <ns1:versioncheck soapenv:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"
                                xmlns:ns1="https://worktre.com/"/>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php/versioncheck"

        try:
            response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)
            soap_response = response.text

        except requests.exceptions.RequestException as e:
            return {
                "status": False,
                "msg": "Request failed",
                "data": {"error": str(e)}
            }

        try:
            root = ET.fromstring(soap_response)
        except ET.ParseError:
            return {
                "status": False,
                "msg": "Error parsing XML response",
                "data": {}
            }

        # Extract <item> values (no namespace)
        items = root.findall(".//{https://worktre.com/}versioncheckResponse/return/item")
        if not items:
            items = root.findall(".//return/item")

        values = [item.text for item in items]

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
            return {
                "status": True,
                "data": version_info
            }
        else:
            return {
                "status": False,
                "msg": "Incomplete version data",
                "data": {"raw_items": values}
            }

    def getBreakTypes(self, userid):

        # Headers for the SOAP request
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/getBreakTypes",
            "SOAPAction": soap_actions.getBreakTypes(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:getBreakTypes>
                 <id>{userid}</id>
              </web:getBreakTypes>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Endpoint URL
        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        soap_response = response.text

        # Parse the SOAP response
        root = ET.fromstring(soap_response)

        # Define namespaces
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        # Find the response element
        return_element = root.find('.//ns1:getBreakTypesResponse/return', namespaces)

        if return_element is not None:
            # Extract the Break Types
            break_types = return_element.findall('item', namespaces)

            # Assuming each item is a string value (adjust parsing as needed)
            break_types_list = [item.text or "" for item in break_types]

            result = {
                "break_types": break_types_list
            }

            try:

                resp = {"status": True, "data": result}
            except Exception as e:
                resp = {"status": False, "msg": "Error parsing response", "data": {"error": str(e)}}
        else:
            resp = {"status": False, "msg": "No response data", "data": {}}

        json_response = json.dumps(resp)
        breaks = json.loads(json_response)
        formated_breaks = self.get_formated_break_types(breaks)
        return formated_breaks

    def requestforaccess(self, userid):
        # Get the computer name and IP address
        computer_name = socket.gethostname()
        ip = get_dynamic_ip()  # Assuming get_dynamic_ip() is a predefined method to get the IP address

        # Headers for the SOAP request
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            # "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/requestforaccess",
            "SOAPAction": soap_actions.requestforaccess(),
        }

        # SOAP request payload
        payload = f"""<?xml version="1.0" encoding="UTF-8"?>
        <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                          xmlns:web="https://worktre.com/">
           <soapenv:Header/>
           <soapenv:Body>
              <web:requestforaccess>
                 <userid>{userid}</userid>
                 <ipaddress>{ip}</ipaddress>
              </web:requestforaccess>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Send the POST request to the API
        # url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        response = requests.post(SOAP_BASE_URL, data=payload, headers=headers, timeout=10)

        # Print and parse the SOAP response
        soap_response = response.text

        # Parse the SOAP response XML
        root = ET.fromstring(soap_response)

        # Define the namespaces for XML parsing
        namespaces = {
            'SOAP-ENV': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns1': 'https://worktre.com/',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'SOAP-ENC': 'http://schemas.xmlsoap.org/soap/encoding/'
        }

        # Extract the 'return' element from the response
        return_element = root.find('.//ns1:requestforaccessResponse/return', namespaces)

        if return_element is not None:
            items = return_element.findall('item', namespaces)

            # Get the keys (first element)
            keys = items[0].text.split(",") if items[0].text else []

            # Strip extra spaces in keys
            keys = [key.strip() for key in keys]

            # Get the values (remaining elements)
            values = [item.text or "" for item in items[1:]]

            # Create a dictionary to hold the result
            result = {}
            for i in range(len(keys)):
                key = keys[i]
                value = values[i]
                result[key] = value

            # Return a structured JSON response
            resp = {"status": True, "data": result}
            json_response = json.dumps(resp)
            return json_response
        else:
            # Return an empty response if no 'return' element is found
            resp = {"status": True, "data": {"ip": f"{ip}"}}
            json_response = json.dumps(resp)
            return json_response

    def get_formated_break_types(self, breaks):
        break_types = breaks["data"]["break_types"][1:]

        formatted_data = []

        for i in range(0, len(break_types), 3):  # Iterate in steps of 3
            formatted_data.append({
                "id": break_types[i],
                "break_type": break_types[i + 1],
                "status": break_types[i + 2]
            })
        return formatted_data

    def startInterval(self):
        pass

    def stopInterval(self):
        pass

    def handleForgetPassword(self, email):
        print(f"Forgot Password requested for: {email}")

    def resetInactivityTimer(self):
        reset_idle_timer()

    def start_inactivity(self):
        logger.info(f"start_inactivity called. is_user_logged_in: {self.is_user_logged_in()}")
        logger.info(f"user_info type: {type(self.user_info)}, user_info: {self.user_info}")

        if not self.is_user_logged_in():
            logger.warning("Cannot start inactivity timer: User not logged in")
            return

        # Check if user_info exists and has required properties
        if not self.user_info or not isinstance(self.user_info, dict):
            logger.warning("Cannot start inactivity timer: user_info is missing or invalid")
            return

        try:
            # Safely get values with defaults
            inactivity_break_time = self.user_info.get("InactivityBreakTime")
            inactivity_logout_time = self.user_info.get("InactivityBreakLogoutTime")

            # Convert to integers with fallback defaults
            if inactivity_break_time is not None:
                inactivity_break_time = int(inactivity_break_time)
            else:
                inactivity_break_time = 5  # Default 5 minutes for warning
                logger.warning(f"InactivityBreakTime not found, using default: {inactivity_break_time}")

            if inactivity_logout_time is not None:
                inactivity_logout_time = int(inactivity_logout_time)
            else:
                inactivity_logout_time = 10  # Default 10 minutes for logout
                logger.warning(f"InactivityBreakLogoutTime not found, using default: {inactivity_logout_time}")

            logger.info(
                f"Starting inactivity timer - Warning after: {inactivity_break_time}m, Logout after: {inactivity_logout_time}m")

            threading.Thread(
                target=start_inactivity_timer,
                args=(inactivity_break_time, inactivity_logout_time),
                kwargs={"on_warn": on_warning, "on_exit": on_exit},
                daemon=True
            ).start()

        except (ValueError, TypeError) as e:
            logger.error(f"Error converting inactivity times to integers: {e}")
            # Start with safe defaults
            threading.Thread(
                target=start_inactivity_timer,
                args=(5, 10),  # Default values: 5 min warning, 10 min logout
                kwargs={"on_warn": on_warning, "on_exit": on_exit},
                daemon=True
            ).start()
        except Exception as e:
            logger.error(f"Error starting inactivity timer: {e}")

    def redirect_login(self):
        global logged_in_user_info
        logged_in_user_info = None
        self.user_info = None


# ---------------------- Path Helper ----------------------


def resource_path(relative_path):
    try:
        # For PyInstaller
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# ---------------------- Set App Window Icon ----------------------
def set_window_icon():
    try:
        window = webview.windows[0]

        def on_loaded():
            if UPDATE_INFO.get("update"):
                # Use f-string but properly escape JavaScript template literals
                latest_version = UPDATE_INFO['latest_version']
                download_url = UPDATE_INFO['download_url']
                current_version = APP_VERSION

                # Professional themed updater JavaScript
                js_code = f"""
                   (function() {{
                       const latestVersion = "{latest_version}";
                       const downloadUrl = "{download_url}";
                       const currentVersion = "{current_version}";

                       // Create professional modal with WorkTre theme
                       const modal = document.createElement('div');
                       modal.id = 'updateModal';
                       modal.style.cssText = `
                           position: fixed;
                           top: 0;
                           left: 0;
                           width: 100%;
                           height: 100%;
                           background: rgba(0, 0, 0, 0.7);
                           display: flex;
                           justify-content: center;
                           align-items: center;
                           z-index: 9999;
                           font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                       `;

                       const dialog = document.createElement('div');
                       dialog.style.cssText = `
                           background: linear-gradient(135deg, rgb(1 167 141) 0%, rgb(0 47 52) 100%);;
                           padding: 2px;
                           border-radius: 12px;
                           box-shadow: 0 10px 40px rgba(0, 0, 0, 0.3);
                           max-width: 500px;
                           width: 90%;
                           overflow: hidden;
                           /* height: 92%; */
                       `;

                       const content = document.createElement('div');
                       content.style.cssText = `
                           background: white;
                           padding: 25px 40px;
                           border-radius: 10px;
                           text-align: center;
                       `;

                       content.innerHTML = `
                           <!-- WorkTre Logo/Styling -->
                           <div style="margin-bottom: 25px;">
                               <div style="font-size: 28px; font-weight: 700; color: #2c3e50; margin-bottom: 5px;">
                                   <img alt="login-screen-img" class="ls-width" src="assets/images/logo.png" style="width: 50%;">
                               </div>
                           </div>

                           <!-- Title -->
                           <h2 style="margin: 0 0 15px 0; color: #1ea88e; font-size: 21px; font-weight: 600;">
                               Update Available
                           </h2>

                           <!-- Description -->
                           <p style="margin: 0 0 25px 0; color: #5d6d7e; font-size: 14px; line-height: 1.5;">
                               A new version is ready for installation
                           </p>

                           <!-- Version Info Box -->
                           <div style="
                               background: #f8f9fa;
                               border-radius: 8px;
                               padding: 12px;
                               margin: 25px 0;
                               text-align: left;
                               border-left: 4px solid #1ca990;
                               font-size: 14px;
                           ">
                               <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                                   <span style="color: #5d6d7e; font-weight: 500;">Current Version:</span>
                                   <span style="color: #e74c3c; font-weight: 600;">v${{currentVersion}}</span>
                               </div>
                               <div style="display: flex; justify-content: space-between;">
                                   <span style="color: #5d6d7e; font-weight: 500;">Latest Version:</span>
                                   <span style="color: #27ae60; font-weight: 600;">v${{latestVersion}}</span>
                               </div>
                           </div>

                           <!-- Update Notes -->
                           <div style="
                               background: #f0f7ff;
                               border-radius: 8px;
                               padding: 15px;
                               margin: 20px 0;
                               text-align: left;
                               border: 1px solid #d1e3ff;
                           ">
                               <div style="color: #1fa88f; font-weight: 600; margin-bottom: 8px;">
                                   What's New:
                               </div>
                               <ul style="
                                   margin: 0;
                                   padding-left: 20px;
                                   color: #5d6d7e;
                                   font-size: 14px;
                                   line-height: 1.5;
                               ">
                                   <li>Performance improvements</li>
                                   <li>Bug fixes and stability enhancements</li>
                                   <li>New features and optimizations</li>
                               </ul>
                           </div>

                           <!-- Buttons -->
                           <div style="margin-top: 30px; display: flex; gap: 15px;">
                               <button id="updateNow" style="
                                   flex: 1;
                                   background: linear-gradient(135deg, #032d35 0%, #1ea892 100%);
                                   color: white;
                                   border: none;
                                   padding: 12px;
                                   border-radius: 8px;
                                   height: fit-content;
                                   cursor: pointer;
                                   font-size: 14px;
                                   font-weight: 600;
                                   transition: all 0.3s ease;
                                   box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
                               ">
                                   <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                                       <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                                           <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                                       </svg>
                                       Update Now
                                   </div>
                               </button>

                               <button id="updateLater" style="
                                   flex: 1;
                                   background: transparent;
                                   color: #1baa90;
                                   border: 2px solid #1baa90;
                                   padding: 10px;
                                   border-radius: 8px;
                                   height: fit-content;
                                   cursor: pointer;
                                   font-size: 14px;
                                   font-weight: 600;
                                   transition: all 0.3s ease;
                               ">
                                   Later
                               </button>
                           </div>

                           <!-- Footer Note -->
                           <div style="margin-top: 25px; color: #95a5a6; font-size: 12px;">
                               The app will restart automatically after installation
                           </div>
                       `;

                       dialog.appendChild(content);
                       modal.appendChild(dialog);
                       document.body.appendChild(modal);

                       // Add hover effects via style tag
                       const style = document.createElement('style');
                       style.textContent = `
                           #updateNow:hover {{
                               transform: translateY(-2px);
                               box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
                           }}
                           #updateLater:hover {{
                               background: #667eea;
                               color: white;
                           }}
                           button:active {{
                               transform: translateY(1px);
                           }}
                       `;
                       document.head.appendChild(style);

                       // Handle Update Now button
                       document.getElementById('updateNow').onclick = function() {{
                           startDownloadProcess(downloadUrl, latestVersion);
                       }};

                       // Handle Later button
                       document.getElementById('updateLater').onclick = function() {{
                           document.body.removeChild(modal);
                       }};

                       function startDownloadProcess(url, version) {{
                           // Update to download view
                           content.innerHTML = `
                               <!-- WorkTre Logo -->
                               <!-- <div style="margin-bottom: 25px;">
                                   <div style="font-size: 28px; font-weight: 700; color: #2c3e50; margin-bottom: 5px;">
                                       <img alt="login-screen-img" class="ls-width" src="assets/images/logo.png" style="width: 50%;">
                                   </div>
                               </div> -->

                               <!-- Download Icon -->
                               <div style="
                                   /* width: 63px;
                                   height: 63px;
                                   background: linear-gradient(135deg, #02a88e 0%, #002f34 100%); */
                                   border-radius: 50%;
                                   margin: 0 auto 35px auto;
                                   display: flex;
                                   align-items: center;
                                   justify-content: center;
                                   animation: pulse 2s infinite;
                               ">
                                   <!-- <svg width="32" height="32" viewBox="0 0 24 24" fill="white">
                                       <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                                   </svg> -->
                                   <img alt="login-screen-img" class="ls-width" src="assets/images/setup.ico" style="width: 27%;">
                               </div>

                               <!-- Title -->
                               <h2 style="margin: 0 0 15px 0; color: #002f34; font-size: 24px; font-weight: 600;">
                                   Downloading Update
                               </h2>

                               <!-- Version Info -->
                               <p style="margin: 0 0 30px 0; color: #02a88e; font-size: 16px;">
                                   Installing version <span style="font-weight: 600; color: #002f34;">v${{version}}</span>
                               </p>

                               <!-- Progress Container -->
                               <div style="
                                   background: #f0f0f0;
                                   border-radius: 10px;
                                   height: 12px;
                                   width: 100%;
                                   margin: 30px 0 15px 0;
                                   overflow: hidden;
                                   box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
                               ">
                                   <div id="progressBar" style="
                                       background: linear-gradient(90deg, rgb(1 167 141) 0%, rgb(0 47 52) 100%);
                                       height: 100%;
                                       width: 0%;
                                       border-radius: 10px;
                                       transition: width 0.3s ease;
                                       position: relative;
                                   ">
                                       <!-- Progress shine effect -->
                                       <div style="
                                           position: absolute;
                                           top: 0;
                                           left: 0;
                                           right: 0;
                                           bottom: 0;
                                           background: linear-gradient(
                                               90deg,
                                               transparent 0%,
                                               rgba(255, 255, 255, 0.4) 50%,
                                               transparent 100%
                                           );
                                           animation: shine 2s infinite;
                                       "></div>
                                   </div>
                               </div>

                               <!-- Progress Text -->
                               <div style="display: flex; justify-content: space-between; margin: 10px 0 25px 0;">
                                   <span style="color: #032e33; font-size: 14px;">0%</span>
                                   <span id="progressPercentage" style="color: #667eea; font-weight: 600; font-size: 16px; display: none;">0%</span>
                                   <span style="color: #032e33; font-size: 14px;">100%</span>
                               </div>

                               <!-- Status Text -->
                               <div id="statusText" style="
                                   color: rgb(2 168 142);
                                   font-size: 14px;
                                   margin: 20px 0;
                                   min-height: 20px;
                               ">
                                   Preparing download...
                               </div>

                               <!-- Loading animation -->
                               <div id="loadingAnimation" style="margin: 20px 0;">
                                   <div style="
                                       border: 3px solid #f0f0f0;
                                       border-top: 3px solid #01a78d;
                                       border-radius: 50%;
                                       width: 40px;
                                       height: 40px;
                                       animation: spin 1s linear infinite;
                                       margin: 0 auto;
                                   "></div>
                               </div>

                               <!-- Styles -->
                               <style>
                                   @keyframes pulse {{
                                       0% {{ transform: scale(1); }}
                                       50% {{ transform: scale(1.05); }}
                                       100% {{ transform: scale(1); }}
                                   }}

                                   @keyframes spin {{
                                       0% {{ transform: rotate(0deg); }}
                                       100% {{ transform: rotate(360deg); }}
                                   }}

                                   @keyframes shine {{
                                       0% {{ transform: translateX(-100%); }}
                                       100% {{ transform: translateX(100%); }}
                                   }}
                               </style>
                           `;

                           // Show loading animation
                           document.getElementById('loadingAnimation').style.display = 'block';

                           // Call Python to handle the download
                           window.pywebview.api.downloadUpdate(url, version);
                       }}

                       // Expose progress update function to Python
                       window.updateDownloadProgress = function(percentage) {{
                           const progressBar = document.getElementById('progressBar');
                           const progressPercentage = document.getElementById('progressPercentage');
                           const statusText = document.getElementById('statusText');

                           if (progressBar && progressPercentage) {{
                               const percent = Math.min(100, Math.max(0, percentage));
                               progressBar.style.width = percent + '%';
                               progressPercentage.textContent = percent.toFixed(1) + '%';

                               // Update status text
                               if (percent < 100) {{
                                   statusText.innerHTML = `
                                       <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                                           <svg width="16" height="16" viewBox="0 0 24 24" fill="#02a88e">
                                               <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
                                           </svg>
                                           Downloading... ${{percent.toFixed(1)}}%
                                       </div>
                                   `;
                                   statusText.style.color = '#02a88e';
                               }} else {{
                                   statusText.innerHTML = `
                                       <div style="color: #27ae60; font-weight: 600; display: flex; align-items: center; justify-content: center; gap: 8px;">
                                           <svg width="20" height="20" viewBox="0 0 24 24" fill="#27ae60">
                                               <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/>
                                           </svg>
                                           Download complete! Preparing installation...
                                       </div>
                                   `;
                                   statusText.style.color = '#27ae60';

                                   // Hide loading animation when complete
                                   const loading = document.getElementById('loadingAnimation');
                                   if (loading) loading.style.display = 'none';
                               }}
                           }}
                       }};
                   }})();
                   """

                try:
                    # Execute the JavaScript
                    window.evaluate_js(js_code)
                    logger.info("Professional update modal shown")
                except Exception as js_error:
                    logger.error(f"Error executing update JS: {js_error}")
                    # Professional fallback
                    window.evaluate_js(f"""
                        if (confirm('✨ Update Available!\\n\\nCurrent: v{current_version}\\nLatest: v{latest_version}\\n\\nUpdate now?')) {{
                            window.pywebview.api.downloadUpdate('{download_url}', '{latest_version}');
                        }}
                    """)

        window.events.loaded += on_loaded

        if window.gui == 'tkinter':
            tk_window = window.gui.window
            icon_path = resource_path('icon.ico')

            if os.path.exists(icon_path):
                tk_window.iconbitmap(icon_path)

            tk_window.resizable(False, False)
            tk_window.maxsize(1092, 650)
            tk_window.minsize(1092, 650)

    except Exception as e:
        logger.warning(f"Unable to set icon or disable maximize: {e}")


# ---------------------- Webview Loader ----------------------
def start_app(api, html_file):
    global current_window, tray_manager, notification_manager

    html_path = resource_path(html_file)
    if not os.path.exists(html_path):
        logger.error(f"{html_file} not found!")
        sys.exit(1)

    start_monitor()

    # Get screen dimensions
    root = tk.Tk()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()

    window_width = 1092
    window_height = 650

    left = (screen_width - window_width) // 2
    top = (screen_height - window_height) // 2

    current_window = webview.create_window(
        title="WorkTre",
        url=f"file://{html_path}",
        width=window_width,
        height=window_height,
        x=left,
        y=top,
        js_api=api,
        resizable=False,
        confirm_close=False,
    )

    # Initialize notification manager
    notification_manager = NotificationManager(
        app_name="WorkTre",
        window_getter=lambda: current_window,
        logger=logger,
    )
    notification_manager.start()

    # Show startup notification
    notification_manager.show_professional_notification(
        "🚀 WorkTre Started",
        "Work timer is running in background",
        "info",
        4
    )

    # --------------------------------------------------
    # Webview ready → create tray
    # --------------------------------------------------
    def on_webview_ready():
        global tray_manager

        if RESTORE_REQUESTED:
            restore_main_window()

        if tray_manager is not None:
            return  # already created

        tray_manager = TrayManager(
            app_name="WorkTre",
            window_getter=lambda: current_window,
            icon_path=resource_path("icon.ico"),
            notifier=notification_manager,
            logger=logger,
            is_updating_checker=lambda: is_updating,
        )

        tray_manager.start()
        logger.info("TrayManager initialized on window load")

    current_window.events.loaded += on_webview_ready

    # --------------------------------------------------
    # Close button → minimize to tray
    # --------------------------------------------------
    def on_closing():
        global is_updating, tray_manager

        if is_updating:
            logger.info("Closing for update")
            return True

        # Tray not ready yet → create it now
        if tray_manager is None:
            tray_manager = TrayManager(
                app_name="WorkTre",
                window_getter=lambda: current_window,
                icon_path=resource_path("icon.ico"),
                notifier=notification_manager,
                logger=logger,
            )
            tray_manager.start()
            logger.info("TrayManager lazily initialized on close")

        tray_manager.minimize_to_tray()
        return False

    current_window.events.closing += on_closing

    logger.info("Application started")

    webview.start(
        debug=False,
        gui="edgechromium",
        func=set_window_icon,
    )

    # Fallback update prompt
    if UPDATE_INFO["update"]:
        try:
            show_simple_update_prompt()
        except Exception:
            pass


def inactivity_window(api, html_file):
    global current_window

    html_path = resource_path(html_file)

    if not os.path.exists(html_path):
        logger.error(f"{html_file} not found!")
        sys.exit(1)

    # Get screen dimensions for centering
    root = tk.Tk()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()  # Close the temporary tkinter window

    # Set your fixed window dimensions
    window_width = 600
    window_height = 500

    # Calculate center position
    left = (screen_width - window_width) // 2
    top = (screen_height - window_height) // 2

    current_window = webview.create_window(
        title='WorkTre',
        url=f'file://{html_path}',
        width=window_width,
        height=window_height,
        x=left,  # Add X position
        y=top,  # Add Y position
        js_api=api,
        minimized=False
    )

    # You can change 'edgechromium' to 'tkinter' here if needed
    webview.start(debug=False, gui='edgechromium', func=set_window_icon)


# ---------------------- Entry Point ----------------------
if __name__ == '__main__':
    start_app(API(), 'index.html')
