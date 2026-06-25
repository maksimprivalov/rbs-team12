"""Najjednostavniji benigni primer - ispiše poruku i izađe sa kodom 0."""
import platform
import sys

print("Pozdrav iz Oblak microVM-a!")
print(f"Python {sys.version.split()[0]} na {platform.machine()}")
