# Benigni test 3: Koristi 'requests' biblioteku
# Potreban requirements.txt: requests==2.31.0
# Očekivano: SAFE, status READY (nakon pip install)

import requests

response = requests.get("https://httpbin.org/get", timeout=5)
print(f"Status: {response.status_code}")
print(f"IP: {response.json().get('origin', 'unknown')}")
