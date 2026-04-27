import sys
sys.path.append(r'd:\Projects\WorkTre Desktop\WorkTre-Desktop-App')
from src.api.soap_client import SOAPClient

client = SOAPClient()
client.base_url = 'https://worktre.com/DesktopAppApiServers/index.php'
xml = """<?xml version='1.0' encoding='UTF-8'?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="urn:DesktopAppApiServer">
<SOAP-ENV:Body>
<ns1:getBreakTypesResponse>
<return>
<item>Id,BreakType,Status</item>
<item>1</item>
<item>Tea</item>
<item>1</item>
<item>2</item>
<item>Lunch</item>
<item>1</item>
</return>
</ns1:getBreakTypesResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""
import xml.etree.ElementTree as ET
root = ET.fromstring(xml)
return_element = root.find('.//return')
items = return_element.findall('item')

keys_text = items[0].text or ''
keys = [k.strip() for k in keys_text.split(',') if k.strip()]
values = [item.text or '' for item in items[1:]]

result = {}
for i in range(min(len(keys), len(values))):
    result[keys[i]] = values[i]

# Store extra values under 'extra_values' if any
if len(values) > len(keys):
    result['extra_values'] = values[len(keys):]
print("Result dictionary:", result)

