"""
Prolazi statičku analizu, ali NAMERNO troši CPU (beskonačna petlja).
Demonstrira da microVM ograničava izvršavanje TIMEOUT-om -> rezultat ima
timed_out=true, a VM se prinudno gasi (ne može da zaglavi host).

Napomena: ako je LLM analiza uključena (ANTHROPIC_API_KEY postavljen), može biti
označen kao SUSPICIOUS i odbijen pre izvršavanja. Bez LLM ključa -> stiže do VM-a.
"""
i = 0
while True:
    i += 1
