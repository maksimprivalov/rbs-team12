# Maliciozni test 1: Shell injection
# Očekivano: REJECTED (Bandit HIGH: B602/B605, LLM: MALICIOUS)

import os
import subprocess

os.system("rm -rf /tmp/test")
subprocess.call(["ls", "/etc"], shell=True)
eval("print('injected')")
