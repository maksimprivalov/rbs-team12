"""
Prolazi statičku analizu, ali pokušava da pristupi mreži.
Demonstrira MREŽNU IZOLACIJU microVM-a: VM nema network interfejs, pa poziv
pada. Kod uhvati grešku i ispiše je -> dokaz da spoljni pristup ne radi.

Napomena: ako je LLM analiza uključena, može biti označen kao network abuse i
odbijen. Bez LLM ključa -> stiže do VM-a i pokaže da mreže nema.
"""
import urllib.request

try:
    resp = urllib.request.urlopen("http://example.com", timeout=5)
    print(f"NEOČEKIVANO: dobijen odgovor {resp.status} - mreža NIJE izolovana!")
except Exception as exc:  # noqa: BLE001
    print(f"OČEKIVANO: mrežni pristup nije uspeo (VM je izolovan): {type(exc).__name__}: {exc}")
