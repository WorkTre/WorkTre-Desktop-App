from inactivity_manager import start_inactivity_timer, stop_inactivity_timer, reset_idle_timer
from connectivity_monitor import start_connectivity_monitor
import webview
import tkinter as tk
import sys
import os
import logging
import requests
import socket
import json
import portalocker
import tempfile
from PIL import ImageGrab
from io import BytesIO
import base64
import time
import threading
import shutil
import xml.etree.ElementTree as ET
from cryptography.fernet import Fernet
from system_monitor import start_monitor


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

current_window = None
logged_in_user_info = None

interval_timer = None
interval_lock = threading.Lock()
repeat_interval_seconds = 0  # To store and reuse duration
is_running = False           # Track whether timer is active
app_version = None


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


url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"
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
    except Exception as e:
        with open("warn.log", "a", encoding="utf-8") as f:
            f.write(f"Error showing modal: {e}\n")

def on_exit():
    if webview.windows:
        webview.windows[0].evaluate_js("inactivityTimeExceed()")
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
        self.app_version = None



        self.maximum_inactivity_logoutTime = 60  # minutes

    def notify_no_connection(self):
        if webview.windows:
            webview.windows[0].evaluate_js("onInternetDisconnectedTimeExceed();")

    def notify_online(self):
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

    def login(self, username, password, max_retries=2, delay=2):
        global logged_in_user_info, app_version
        logging.info("login")
        computer_name = socket.gethostname()
        ip = get_dynamic_ip()
        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/login",
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
                 <wtversion>{app_version}</wtversion>
                 <ipaddress>{ip}</ipaddress>
              </web:login>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        try:
            # Send the POST request
            response = requests.post(url, data=payload, headers=headers, timeout=10)  # Timeout set to 10 seconds

            if response.status_code == 200:
                soap_response = response.text
                user_info = self.process_soap_response(soap_response)

                parsed = json.loads(user_info)

                self.user_info = parsed["data"]
                logged_in_user_info = parsed["data"]

                data = parsed["data"]

                if data and isinstance(data, dict):
                    if data.get("SystemChangeStatus") == "1":
                        resp = {"status": False, "data": data}
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
                    resp = {"status": False, "error": "ip", "msg": "[color=#0000FF][u]Click here[/u][/color]", "data": result}
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
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/breakout/inactivity",
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
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php/breakout"

        # Send the POST request
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)

            soap_response = response.text

        except requests.exceptions.RequestException as e:
            return json.dumps({"status": False, "msg": "Request failed", "data": {"error": str(e)}})



        try:
            # Parse the SOAP response
            root = ET.fromstring(soap_response)
        except ET.ParseError:
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
            return json.dumps({"status": True, "data": result})
        else:
            return json.dumps({"status": False, "msg": "No response data", "data": {}})


    def logoutinactivity(self, userid, breaktype="inactivity"):
        if not self.is_user_logged_in():
            return
        # Endpoint URL
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/logoutinactivity",
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
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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
        global app_version

        computer_name = socket.gethostname()
        ip = get_dynamic_ip()
        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/crashlogin",
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
                 <wtversion>{app_version}</wtversion>
                 <ipaddress>{ip}</ipaddress>
              </web:crashlogin>
           </soapenv:Body>
        </soapenv:Envelope>
        """

        # Send the POST request
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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

        # Headers
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/logout",
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
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/lastactivitydate",
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
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/getservice",
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
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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

    def breakin(self, userid, breaktype, comments, training_type_id="", trainer_id="", website="", ticket_no="", expected_duration=""):
        if not self.is_user_logged_in():
            return

        computer_name = socket.gethostname()
        self.break_type = breaktype

        # Headers for the SOAP request
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/breakin",
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
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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
            except Exception as e:
                resp = {"status": False, "msg": "Error parsing response", "data": {"error": str(e)}}
        else:
            resp = {"status": False, "msg": "No response data", "data": {}}

        json_response = json.dumps(resp)
        return json_response

    def breakout(self, userid, breaktype, comments="", inactivity=False):
        if not self.is_user_logged_in():
            return

        # Headers for the SOAP request
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/breakout",
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
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(url, data=payload, headers=headers, timeout=10)



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
            except Exception as e:
                resp = {"status": False, "msg": "Error parsing response", "data": {"error": str(e)}}
        else:
            resp = {"status": False, "msg": "No response data", "data": {}}

        json_response = json.dumps(resp)
        return json_response



    def version_check(self):
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/versioncheck",
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

        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php/versioncheck"

        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)
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
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/getBreakTypes",
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
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"

        # Send the POST request
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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
            "SOAPAction": "https://worktre.com/webservices/worktre_soap_2.0/services.php/requestforaccess",
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
        url = "https://worktre.com:443/webservices/worktre_soap_2.0/services.php"
        response = requests.post(url, data=payload, headers=headers, timeout=10)

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
        if not self.is_user_logged_in():
            return

        threading.Thread(
            target=start_inactivity_timer,
            args=(int(self.user_info.get("InactivityBreakTime")), int(self.user_info.get("InactivityBreakLogoutTime"))),
            # args=(0.3, 1),
            kwargs={"on_warn": on_warning, "on_exit": on_exit},
            daemon=True
        ).start()

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

        # Only works for tkinter GUI
        if window.gui == 'tkinter':
            tk_window = window.gui.window
            icon_path = resource_path('icon.ico')

            if os.path.exists(icon_path):
                tk_window.iconbitmap(icon_path)

            # Set fixed window size
            tk_window.resizable(False, False)
            tk_window.maxsize(1092, 650)
            tk_window.minsize(1092, 650)

        else:
            logger.info(f"Skipping icon/resizing: GUI backend '{window.gui}' doesn't support it.")

    except Exception as e:
        logger.warning(f"Unable to set icon or disable maximize: {e}")



# ---------------------- Webview Loader ----------------------
def start_app(api, html_file):
    global current_window

    html_path = resource_path(html_file)
    if not os.path.exists(html_path):
        logger.error(f"{html_file} not found!")
        sys.exit(1)

    start_monitor()

    # Get screen dimensions for centering
    root = tk.Tk()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()  # Close the temporary tkinter window

    # Set your fixed window dimensions
    window_width = 1092
    window_height = 650

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
        resizable=False,
        confirm_close=True
    )

    logging.info("started")

    webview.start(debug=False, gui='edgechromium', func=set_window_icon)

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
