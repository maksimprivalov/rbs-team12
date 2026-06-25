# Izveštaj statičke analize - Oblak platforma

> Alati: Bandit 1.9.4, Safety  
> Analiza pokrenuta: 2026-06-21  
> Obuhvat: `server/`, `cli/`  
> Odgovornost: Član 3

---

## 1. Bandit - bezbednosna analiza

### Pokretanje

```bash
python -m bandit -r server/ cli/ -f txt
```

### Rezime

| Metrika | Vrednost |
|---|---|
| Ukupno linija koda | 1214 |
| HIGH severity | **0** |
| MEDIUM severity | **0** |
| LOW severity | 11 |
| Skipped fajlovi | 0 |

**Nema HIGH ni MEDIUM nalaza.** Svi nalazi su LOW severity, visoke pouzdanosti (High confidence), i svi se odnose na namerno korišćenje `subprocess` modula.

---

### Detaljan pregled nalaza

#### B404 - `import subprocess` (3 nalaza)

| Fajl | Linija | Opis |
|---|---|---|
| `server/services/pipeline.py` | 11 | Import subprocess modula |
| `server/services/sandbox.py` | 20 | Import subprocess modula |
| `server/services/verifier.py` | 14 | Import subprocess modula |

**Procena rizika:** PRIHVATLJIVO - `subprocess` se koristi namerno za pokretanje izoliranih procesa (sandbox executor, Bandit analiza, pip install). Svi pozivi koriste **list formu** (ne string + `shell=True`), što eliminiše shell injection rizik.

---

#### B603 - `subprocess call without shell=True` (4 nalaza)

| Fajl | Linija | Poziv |
|---|---|---|
| `server/services/pipeline.py` | 40 | `pip install -r requirements.txt` |
| `server/services/sandbox.py` | 89 | `python main.py` (sandbox exec) |
| `server/services/verifier.py` | 50 | `bandit -r <target>` |
| `server/services/verifier.py` | 97 | `pylint <file>` |

**Procena rizika:** PRIHVATLJIVO - Bandit upozorava kad god se koristi `subprocess` bez `shell=True`, ali to je zapravo sigurniji pristup. Svi argumenti su interno kontrolisani stringovi (putanje iz baze, konstantne komande) - nema korisničkog unosa koji se direktno prosleđuje kao argument.

**Napomena za `pipeline.py:40` (`pip install`):** Putanja do `requirements.txt` dolazi iz internog storage path-a (konstruiše je server), ne iz direktnog korisničkog unosa. Prihvatljivo.

**Napomena za `sandbox.py:89` (`python main.py`):** Ovo je srž sandbox izvršavanja - korisnikov kod se **ne prosleđuje kao argument** već se pokreće kao fajl u kopiranom direktorijumu. Nema injection vektora.

---

#### B607 - `start_process_with_partial_path` (3 nalaza)

| Fajl | Linija | Komanda |
|---|---|---|
| `server/services/pipeline.py` | 40 | `pip` |
| `server/services/verifier.py` | 50 | `bandit` |
| `server/services/verifier.py` | 97 | `pylint` |

**Procena rizika:** PRIHVATLJIVO u Docker kontekstu - `pip`, `bandit`, i `pylint` su instalirani u Docker image i dostupni na poznatom PATH-u. U produkciji preporučeno koristiti apsolutne putanje (`/usr/local/bin/pip` itd.) ili `sys.executable + "-m"` formu.

**Rešenje (otvorena stavka):**
```python
# Umesto:  ["pip", ...]
# Koristiti: [sys.executable, "-m", "pip", ...]

# Umesto:  ["bandit", ...]
# Koristiti: [sys.executable, "-m", "bandit", ...]
```

---

#### B110 - `try/except/pass` (1 nalaz)

| Fajl | Linija | Opis |
|---|---|---|
| `server/services/sandbox.py` | 51 | Tiho ignorisanje greške pri postavljanju resource limita |

**Procena rizika:** PRIHVATLJIVO - `resource` modul nije dostupan na Windows-u (lokalni razvoj). `pass` je svestan fallback: ako resource limiti nisu dostupni, timeout mehanizam (`subprocess timeout=30s`) preuzima ulogu. Komentar u kodu objašnjava razlog.

---

### Ukupna Bandit ocena

> Codebase nema HIGH ni MEDIUM ranjivosti. Svih 11 LOW nalaza su pregledani i procenjeni kao prihvatljivi uz dokumentovane razloge. Preporučene popravke (apsolutne putanje za subprocesse) navedene su u sekciji otvorenih stavki.

---

## 2. Safety - poznate ranjivosti u zavisnostima

### Pokretanje

```bash
python -m safety check -r server/requirements.txt
```

### Rezultati - originalne verzije (pre popravke)

Safety v3.8.1 pronašao je **6 ranjivosti u 2 paketa** u originalnim verzijama (`python-multipart==0.0.9`, `python-jose==3.3.0`).

#### `python-multipart 0.0.9` - 4 ranjivosti

| CVE | Safety ID | Affected | Opis | Severity |
|---|---|---|---|---|
| CVE-2026-24486 | 85155 | <0.0.22 | Path Traversal - unsafe filesystem path construction | HIGH |
| CVE-2026-42561 | SFTY-20260506-35099 | <0.0.27 | DoS - absence of limits on uploaded content | MEDIUM |
| CVE-2024-53981 | 74427 | <0.0.18 | Resource exhaustion (CWE-770) - allocation without limits | MEDIUM |
| CVE-2026-40347 | SFTY-20260415-68235 | <0.0.26 | DoS - inefficient handling of preamble data | MEDIUM |

**Popravka:** Nadograđen na `python-multipart==0.0.27` u `requirements.txt`. [OK]

#### `python-jose 3.3.0` - 2 ranjivosti

| CVE | Safety ID | Affected | Opis | Severity |
|---|---|---|---|---|
| CVE-2024-33664 | 70716 | <3.4.0 | DoS - resource consumption during token decode | MEDIUM |
| CVE-2024-33663 | 70715 | <3.4.0 | Algorithm confusion sa OpenSSH ECDSA ključevima | HIGH |

**Popravka:** Nadograđen na `python-jose[cryptography]==3.4.0` u `requirements.txt`. [OK]

### Status nakon popravke

Nakon nadogradnje oba paketa, Safety ne prijavljuje ranjivosti.

### Pregled zavisnosti (finalne verzije)

| Paket | Verzija | Status |
|---|---|---|
| `fastapi` | 0.111.0 | [OK] Bez CVE |
| `uvicorn[standard]` | 0.29.0 | [OK] Bez CVE |
| `sqlalchemy` | 2.0.30 | [OK] Bez CVE |
| `alembic` | 1.13.1 | [OK] Bez CVE |
| `python-jose[cryptography]` | **3.4.0** | [OK] Nadograđen (bio 3.3.0) |
| `passlib[bcrypt]` | 1.7.4 | [OK] Bez CVE |
| `python-multipart` | **0.0.27** | [OK] Nadograđen (bio 0.0.9) |
| `pydantic` | 2.7.1 | [OK] Bez CVE |
| `pydantic-settings` | 2.2.1 | [OK] Bez CVE |
| `aiofiles` | 23.2.1 | [OK] Bez CVE |
| `bandit` | 1.7.9 | [OK] Bez CVE |
| `pylint` | 3.2.0 | [OK] Bez CVE |
| `httpx` | 0.27.0 | [OK] Bez CVE |
| `bcrypt` | 4.0.1 | [OK] Bez CVE |

---

## 3. Ručni pregled - dodatne napomene

### 3.1 JWT konfiguracija

- Algoritam: HS256 sa `SECRET_KEY` iz environment-a
- Token expiry: 60 minuta
- **Rizik:** `SECRET_KEY` u `.env.example` je placeholder (`dev-secret-change-in-prod`). Produkcija MORA koristiti dugačak nasumičan ključ.
- **Preporuka:** `SECRET_KEY=$(openssl rand -hex 32)` i vrtiti ključ periodično

### 3.2 Lozinke

- bcrypt hashing - ispravno, work factor 12 (passlib default)
- Minimalna dužina: 6 znakova - relativno slabo, preporučiti minimum 12

### 3.3 SQL injection

- SQLAlchemy ORM sa parametrizovanim upitima - bez SQL injection vektora
- Nema raw SQL stringa nigde u kodebaiji

### 3.4 Path traversal u storage

- `storage.py` prima filename od korisnika i čuva ga kao `main.py` (fiksno ime)
- `requirements.txt` je jedino alternativno ime
- Efikasno eliminiše path traversal jer korisnik ne kontroliše ime fajla na disku

### 3.5 Default admin korisnik

- Seed skripta kreira `admin / admin123` - MORA se promeniti pre produkcije
- Preporučeno: ukloniti seed u produkcijskom Dockerfile-u ili koristiti env varijable za admin lozinku

---

## 4. Otvorene stavke

| ID | Opis | Prioritet |
|---|---|---|
| SA-01 | Zamijeniti `["pip", ...]` sa `[sys.executable, "-m", "pip", ...]` u pipeline.py | LOW |
| SA-02 | Zamijeniti `["bandit", ...]` i `["pylint", ...]` sa `-m` formom u verifier.py | LOW |
| SA-03 | Povećati minimalnu dužinu lozinke na 12 znakova | MEDIUM |
| SA-04 | Dodati rotaciju SECRET_KEY i dokumentovati proceduru | MEDIUM |
| SA-05 | Ukloniti ili promeniti seed admin lozinku u produkcijskom setupu | HIGH |
| SA-06 | Pokrenuti Safety redovno u CI/CD pipelinu za praćenje novih CVE-a | MEDIUM |
