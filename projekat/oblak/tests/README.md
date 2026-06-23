# Testni primeri - Oblak platforma

Ovaj folder sadrži testne Python funkcije za verifikaciju bezbednosnog ponašanja platforme.  
Testovi su podeljeni u dve kategorije: **benigni** (treba da prođu) i **maliciozni** (treba da budu odbijeni ili sandboxovani).

---

## Struktura

```
tests/
+-- benign/
|   +-- hello_world.py        # Hello World - osnovni test
|   +-- math_compute.py       # Računanje prostih brojeva
|   +-- with_requirements.py  # Koristi 'requests' biblioteku
|   +-- requirements.txt      # requests==2.31.0
+-- malicious/
    +-- shell_exec.py         # Shell injection (os.system, subprocess, eval)
    +-- read_host_files.py    # Čitanje /etc/passwd, /etc/shadow
    +-- network_scan.py       # Skeniranje portova
    +-- infinite_loop.py      # Beskonačna petlja (timeout test)
    +-- fork_bomb.py          # Fork bomb / resource exhaustion
```

---

## Kako pokrenuti testove

```bash
# Login
oblak login

# Deploy i provjera statusa
oblak deploy tests/benign/hello_world.py --name hello-test
oblak status <id>

# Deploy sa requirements.txt
oblak deploy tests/benign/with_requirements.py \
    --requirements tests/benign/requirements.txt \
    --name requests-test

# Invoke funkcije (kada status bude READY)
curl -X POST http://localhost:8000/invoke/<id> \
    -H "Authorization: Bearer <token>"
```

---

## Benigni testovi

### 1. `hello_world.py` - Hello World

```python
def main():
    print("Hello from Oblak!")
main()
```

| Faza | Očekivani rezultat |
|---|---|
| Bandit | 0 HIGH nalaza |
| LLM | SAFE |
| Status | READY |
| Invoke | `output: "Hello from Oblak!\n"`, `exit_code: 0` |

---

### 2. `math_compute.py` - Sieve of Eratosthenes

```python
def sieve(n):
    ...
primes = sieve(100)
print(f"Prvih {len(primes)} prostih brojeva do 100: {primes}")
```

| Faza | Očekivani rezultat |
|---|---|
| Bandit | 0 HIGH nalaza |
| LLM | SAFE |
| Status | READY |
| Invoke | Lista prostih do 100, `exit_code: 0` |

---

### 3. `with_requirements.py` - HTTP zahtev sa `requests`

```python
import requests
response = requests.get("https://httpbin.org/get", timeout=5)
print(f"Status: {response.status_code}")
```

**Napomena:** Zahteva `requirements.txt` sa `requests==2.31.0`.

| Faza | Očekivani rezultat |
|---|---|
| Bandit | 0 HIGH nalaza |
| LLM | SAFE (HTTP GET ne smatra se malicioznim) |
| pip install | requests instaliran u `venv/` |
| Status | READY |
| Invoke | `Status: 200`, `exit_code: 0` |

**Napomena o sandboxu:** Ovaj test demonstrira da sandbox ne blokira mrežni pristup na procesnom nivou - to je otvorena stavka (SR-01). Zaštita dolazi od verifikatora koji odbija kod sa jasnim malicioznim mrežnim obrascima.

---

## Maliciozni testovi

### 4. `shell_exec.py` - Shell injection

```python
import os, subprocess
os.system("rm -rf /tmp/test")
subprocess.call(["ls", "/etc"], shell=True)
eval("print('injected')")
```

| Faza | Očekivani rezultat | Razlog |
|---|---|---|
| Bandit | HIGH: B602 (shell=True), B605 (os.system) | Shell injection |
| LLM | MALICIOUS | Jasni shell execution obrasci |
| Status | **REJECTED** | Bandit HIGH nalaz |
| Invoke | N/A - funkcija odbačena pre READY statusa | - |

---

### 5. `read_host_files.py` - Čitanje osetljivih fajlova

```python
with open("/etc/passwd", "r") as f:
    print(f.read())
with open("/etc/shadow", "r") as f:
    print(f.read())
```

| Faza | Očekivani rezultat | Razlog |
|---|---|---|
| Bandit | 0 HIGH nalaza (Bandit ne detektuje ovo) | Nema shell poziva |
| LLM | MALICIOUS / SUSPICIOUS | Eksplicitni pokušaj čitanja sistemskih fajlova |
| Status | **REJECTED** | LLM verdict |
| Invoke | N/A | - |

**Napomena:** Ovaj test pokazuje važnost LLM sloja - Bandit sam ne bi uhvatio ovaj obrazac. Sandbox kao fallback: čak i da prođe analizu, `/etc/shadow` je čitljiv samo od root-a i koda koji se pokrene u Docker kontekstu nema pristupa.

---

### 6. `network_scan.py` - Skeniranje portova

```python
import socket
def scan_ports(host, start, end):
    for port in range(start, end + 1):
        sock = socket.socket(...)
        sock.connect_ex((host, port))
```

| Faza | Očekivani rezultat | Razlog |
|---|---|---|
| Bandit | 0 HIGH nalaza | socket API nije po sebi HIGH |
| LLM | MALICIOUS | Pattern skeniranja portova je jasan |
| Status | **REJECTED** | LLM verdict |
| Invoke | N/A | - |

---

### 7. `infinite_loop.py` - Timeout test

```python
while True:
    pass
```

| Faza | Očekivani rezultat | Razlog |
|---|---|---|
| Bandit | 0 HIGH nalaza | Nema opasnih API poziva |
| LLM | SAFE ili SUSPICIOUS | Beskonačna petlja je ambivalentna |
| Status | **READY** (ako LLM ne odbaci) ili REJECTED | Zavisi od LLM verdikta |
| Invoke | `exit_code: -1`, `timed_out: true`, `duration_ms ~ 30000` | Hard timeout od 30s |

**Napomena:** Ovaj test verifikuje da sandbox timeout mehanizam radi ispravno. Čak i ako kod prođe analizu, izvršavanje se prekida posle 30 sekundi.

---

### 8. `fork_bomb.py` - Resource exhaustion

```python
import os, subprocess
while True:
    subprocess.Popen(["python3", __file__])
    os.fork()
```

| Faza | Očekivani rezultat | Razlog |
|---|---|---|
| Bandit | HIGH: B603 (`subprocess.Popen`) | subprocess poziv |
| LLM | MALICIOUS | Fork bomb pattern je prepoznatljiv |
| Status | **REJECTED** | Bandit HIGH + LLM MALICIOUS |
| Invoke | N/A | - |

**Napomena:** Ako bi hipotetički prošao analizu, `RLIMIT_NPROC=50` u sandboxu ograničava broj procesa i štiti host od fork bomb napada.

---

## Rezime

| Test | Prolazi analizu? | Može se invokati? | Sandbox zaštita |
|---|---|---|---|
| `hello_world.py` | DA | DA | N/A |
| `math_compute.py` | DA | DA | N/A |
| `with_requirements.py` | DA | DA | N/A |
| `shell_exec.py` | **NE** (Bandit HIGH) | **NE** | N/A |
| `read_host_files.py` | **NE** (LLM) | **NE** | Filesystem perms |
| `network_scan.py` | **NE** (LLM) | **NE** | N/A |
| `infinite_loop.py` | Možda | Timeout 30s | Timeout |
| `fork_bomb.py` | **NE** (Bandit HIGH + LLM) | **NE** | RLIMIT_NPROC |

Sistem implementira **odbranu u dubini** (defense-in-depth):
1. **Verifikator** kao prva linija - odbija većinu malicioznog koda pre izvršavanja
2. **Sandbox** kao fallback - resource limiti i timeout štite host čak i ako verifikator promaši
