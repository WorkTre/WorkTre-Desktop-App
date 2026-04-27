import urllib.request
import xml.etree.ElementTree as ET

url = "https://worktre.com/webservices/worktre_soap_2.1.1/services.php?wsdl"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    xml_data = response.read()

root = ET.fromstring(xml_data)
ns = {'wsdl': 'http://schemas.xmlsoap.org/wsdl/', 's': 'http://www.w3.org/2001/XMLSchema'}

messages = {}
for msg in root.findall('wsdl:message', ns):
    msg_name = msg.attrib['name']
    parts = []
    for part in msg.findall('wsdl:part', ns):
        parts.append(part.attrib['name'])
    messages[msg_name] = parts

for portType in root.findall('wsdl:portType', ns):
    for op in portType.findall('wsdl:operation', ns):
        op_name = op.attrib['name']
        input_msg = op.find('wsdl:input', ns)
        if input_msg is not None:
            msg_name = input_msg.attrib.get('message', '').split(':')[-1]
            params = messages.get(msg_name, [])
            print(f"{op_name}: {params}")
