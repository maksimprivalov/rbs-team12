"""
MALICIOZAN: destruktivna komanda (rm -rf) sastavljena iz promenljive.
Treba da bude ODBIJEN u analizi (Bandit B602: shell=True sa promenljivom -> HIGH).
"""
import os
import subprocess

target = os.environ.get("HOME", "/") + "/important_data"
subprocess.call("rm -rf " + target, shell=True)
