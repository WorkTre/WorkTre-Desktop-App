"""SOAP envelope values are escaped; ordinary text is left unchanged."""

import xml.etree.ElementTree as ET

from src.api.soap_client import SOAPClient

PASSWORD = "a&b<c>d\"e'f"
NAMESPACES = {
    "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
    "web": "https://worktre.com/",
}


def _envelope(method, parameters):
    """Previous interpolation, used to prove safe values are byte-identical."""
    param_xml = ""
    for key, value in parameters.items():
        param_xml += f"<{key}>{value}</{key}>\n"
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


def test_login_password_with_markup_is_well_formed():
    client = SOAPClient(base_url="https://worktre.com/soap")
    parameters = {
        "employeeaccount": "ada",
        "password": PASSWORD,
        "ComputerName": "TEST-PC",
        "wtversion": "2.2.3",
        "ipaddress": "10.1.2.3",
    }
    payload = client._build_soap_envelope("login", parameters)

    root = ET.fromstring(payload)
    login = root.find("soapenv:Body/web:login", NAMESPACES)
    assert login is not None
    password = login.find("password")
    assert password is not None
    assert password.text == PASSWORD
    assert login.find("employeeaccount").text == "ada"
    assert "&amp;" in payload
    assert "&lt;" in payload
    assert "&gt;" in payload
    assert "<password>a&b<" not in payload


def test_ordinary_values_are_unchanged_byte_for_byte():
    client = SOAPClient(base_url="https://worktre.com/soap")
    parameters = {
        "employeeaccount": "ada",
        "password": "plain-password",
        "ComputerName": "TEST-PC",
        "wtversion": "2.2.3",
        "ipaddress": "10.1.2.3",
    }
    payload = client._build_soap_envelope("login", parameters)
    assert payload == _envelope("login", parameters)
    assert "&amp;" not in payload
    assert "&lt;" not in payload
    assert "&gt;" not in payload
