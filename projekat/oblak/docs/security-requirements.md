# Bezbednosni zahtevi — Oblak platforma

> Oblast: Sandbox izvršavanje korisničkog koda  
> Odgovornost: Član 3

---

## 1. Kontekst izvršavanja

Oblak platforma izvršava proizvoljni Python kod koji su korisnici uploadovali. Ovaj kod je po definiciji **nepouzdani unos** i mora biti izolovan od:

- Host fajlsistema (server podaci, baza, storage)
- Mrežnih resursa kojima server ima pristup
- Okruženja (environment varijable sa kredencijalima)
- Procesa ostalih korisnika i samog servera
- Hardverskih resursa (CPU, RAM, disk) u neograničenim količinama

---

## 2. Runtime strategija

Oblak koristi **dva runtime nivoa**, biraju se automatski pri svakom invoke pozivu:

| Runtime | Kada se koristi | Izolacija |
|---|---|---|
| **Firecracker MicroVM** | Linux host sa `/dev/kvm` + kernel + rootfs | Hardverska VM izolacija (KVM/vKVM) |
| **Subprocess sandbox** | Fallback — Windows, CI, Docker bez KVM | OS-level: resource limits, session izolacija |

`invoke.py` poziva `firecracker.is_available()` i automatski bira runtime. Audit log beleži koji runtime je korišćen za svaki poziv.

---

## 3. Firecracker MicroVM izolacija

### 3.1 Arhitektura

```
invoke.py
    └── firecracker.py
          ├── _create_code_drive()   → ext4 slika sa main.py
          ├── Firecracker proces     → API socket + serial konzola
          │     └── KVM MicroVM
          │           ├── /init      → montira code drive, pokreće python3
          │           └── /dev/vdb   → code drive (read-only)
          └── cleanup                → kill VM + rm temp fajlovi
```

### 3.2 Šta VM može/ne može

| Akcija | Dostupno u VM | Razlog |
|---|---|---|
| Čitati korisnikov `main.py` | DA | Montira se read-only sa `/dev/vdb` |
| Pisati na rootfs | NE | Rootfs je read-only (`is_read_only: true`) |
| Pristupiti host fajlsistemu | NE | VM izolacija na nivou KVM |
| Ostvariti mrežne konekcije | NE | Mrežni interfejs NIJE konfigurisan |
| Pristupiti storage ostalih korisnika | NE | VM nema ni /dev ni network pristup host-u |
| Eskalirati privilegije na hostu | NE | KVM VM boundary + Firecracker seccomp |

### 3.3 Mrežna izolacija VM-a

Firecracker VM **nema konfigurisan mrežni interfejs** — jedini drive je read-only code drive. Guest kernel nema `eth0` ni `lo` vidljive (osim loopback-a koji je interni VM-u).

Za buduću implementaciju mrežnog pristupa (za `with_requirements.py` scenario): TAP device sa `iptables FORWARD DROP` policy, dozvoliti samo odabrane destinacije.

### 3.4 Code injection mehanizam

```
1. dd          → prazan ext4 fajl (8MB)
2. mkfs.ext4   → formatiran ext4 filesystem
3. debugfs -w  → write main.py /main.py (bez montiranja, bez root-a)
4. Firecracker → montira ext4 kao /dev/vdb (read-only drive)
5. /init       → mount /dev/vdb /code && python3 /code/main.py
6. Cleanup     → rm -rf /tmp/fc_*
```

---

## 4. Izolacija procesa u subprocess sandbox okruženju

### 2.1 Procesna izolacija

| Mehanizam | Implementacija | Efekat |
|---|---|---|
| Novi process session | `start_new_session=True` | Korisnikov kod ne može da šalje signale parent procesu niti procesnoj grupi servera |
| Odvojen working directory | `tempfile.mkdtemp()` | Sandbox radi u privremenom direktorijumu, izolovan od storage fajlova |
| Kopiranje koda | `shutil.copy2` pre pokretanja | Originalni fajlovi u storage-u nisu dostupni iz sandbox direktorijuma |
| Cleanup po završetku | `shutil.rmtree` u `finally` bloku | Privremeni direktorijum se uvek briše, čak i pri crash-u |

### 2.2 Ograničen environment

Sandbox proces prima **minimalan skup environment varijabli**:

```
PATH=/usr/local/bin:/usr/bin:/bin
HOME=<tmp_dir>
TMPDIR=<tmp_dir>
PYTHONPATH=<venv_dir>  # samo ako postoji requirements.txt
```

**Eksplicitno isključeno:**
- `DATABASE_URL`, `SECRET_KEY`, `ANTHROPIC_API_KEY` — server kredencijali
- `STORAGE_PATH` — putanja do korisničkih fajlova
- Sve ostale env varijable servera

---

## 3. Resource limits

### 3.1 CPU i memorija (Linux — `resource` modul)

| Limit | Vrednost | Mehanizam |
|---|---|---|
| CPU vreme | 30 sekundi | `RLIMIT_CPU` — kernel šalje SIGKILL pri prekoračenju |
| Virtuelna memorija | 128 MB | `RLIMIT_AS` — OOM kill pri prekoračenju |
| Broj procesa/threadova | 50 | `RLIMIT_NPROC` — sprečava fork bomb |

Resource limiti se postavljaju u `preexec_fn` (pre `exec()` u child procesu) i važe samo za sandbox child i sve procese koje on pokrene.

### 3.2 Execution timeout

Hard timeout od **30 sekundi** implementiran kroz `subprocess.run(..., timeout=30)`. Ako proces ne završi na vreme:
- Python podiže `subprocess.TimeoutExpired`
- Sandbox hvata izuzetak i vraća `{"exit_code": -1, "timed_out": true}`
- Privremeni direktorijum se briše u `finally`

### 3.3 Output limit

Izlaz (stdout + stderr) se truncuje na **64 KB** pre vraćanja korisniku. Ovo sprečava:
- DoS napadima koji generišu gigabajte output-a
- Memory exhaustion u server procesu

---

## 4. Network policy

### 4.1 Trenutno stanje

Sandbox subprocess **nema eksplicitnu network izolaciju** na nivou OS-a. Python kod unutar sandboxa može pokušati da otvori mrežne konekcije.

**Mitigacije u trenutnoj implementaciji:**
- Code Verifier (Bandit + LLM) odbija kod koji sadrži mrežne operacije pre izvršavanja
- Restricted environment ne sadrži proxy podešavanja

### 4.2 Preporučena produkcijska rešenja

| Rešenje | Opis | Složenost |
|---|---|---|
| **Firecracker MicroVM** | Potpuna VM izolacija sa KVM, sopstveni network namespace | Visoka |
| Network namespace (`unshare`) | `ip netns` ili `unshare --net` pre pokretanja | Srednja |
| seccomp-bpf profil | Filtriranje `socket()` syscall-a | Srednja |
| iptables/nftables | Blokiraj outbound saobraćaj za sandbox UID | Srednja |

---

## 5. Privilegije pod kojima se sandbox pokreće

Sandbox subprocess se pokreće pod **istim korisnikom kao FastAPI server**.

**Zahtevi za produkcijsko okruženje:**
- Server MORA da radi pod neprivilegovanim korisnikom (nije `root`)
- `Dockerfile` treba da sadrži `USER oblak` direktivu
- Preporučeno: zasebni `sandbox` korisnik sa minimalnim privilegijama
- Storage direktorijum treba biti vlasništvo `oblak` korisnika, bez `execute` bita na direktorijumu

---

## 6. Šta se dešava pri crash-u sandbox procesa

| Scenario | Posledica | Zaštita |
|---|---|---|
| Process exit code != 0 | Vraća se grešan exit code korisniku, beleži se u audit_log | Normalno rukovanje |
| Timeout (30s) | `TimeoutExpired` izuzetak, cleanup temp dir, exit_code = -1 | `try/finally` blok |
| OOM kill (SIGKILL) | Returncode = -9, normalno rukovanje | `try/finally` blok |
| Exception u sandbox kodu | Vraća se stderr stack trace korisniku | Normalno rukovanje |
| Exception u orchestratoru | HTTP 500, audit log, temp dir se čisti u `finally` | Global error handler |
| Disk pun (temp dir) | `TemporaryDirectory` greška → HTTP 500 | Server monitoring |

U svim scenarijima, privremeni radni direktorijum se briše u `finally` bloku — **nikad ne ostaje "leaky" state**.

---

## 7. Pre-execution verifikacija

Svaka funkcija prolazi kroz trojeslojnu analizu **pre** nego što uopšte može biti pozvana:

```
Upload → PENDING → ANALYZING → SAFE/REJECTED → READY
                     │
                     ├── Bandit (statička analiza, HIGH nalaz → REJECTED)
                     ├── pylint (kvalitet koda, informativan)
                     └── LLM (Anthropic API, MALICIOUS/SUSPICIOUS → REJECTED)
```

Samo funkcije sa statusom `READY` mogu biti izvršene. Ovo je prva linija odbrane.

---

## 8. Audit i monitoring

Svaki invoke poziv se upisuje u `audit_log` tabelu sa:
- `user_id` — ko je pozvao
- `function_id` — koja funkcija
- `exit_code` — rezultat izvršavanja
- `duration_ms` — vreme izvršavanja
- `timed_out` — da li je timeout nastao
- `timestamp` — UTC timestamp

Audit log je **append-only** — nema DELETE ni UPDATE endpoint-a za `audit_log`. Admin može čitati logove putem `GET /admin/audit`.

---

## 9. Otvorene stavke (nije implementirano)

| ID | Opis | Prioritet |
|---|---|---|
| SR-01 | Network namespace izolacija za sandbox process | HIGH |
| SR-02 | seccomp-bpf profil (blokiranje opasnih syscall-a: `ptrace`, `mount`, `mknod`) | HIGH |
| SR-03 | Pokretanje sandbox procesa pod zasebnim neprivilegovanim korisnikom | HIGH |
| SR-04 | Zamena subprocess sandbox-a sa Firecracker MicroVM u produkciji | MEDIUM |
| SR-05 | Disk quota po korisniku za storage direktorijum | MEDIUM |
| SR-06 | Rate limiting invoke endpoint-a po korisniku i IP-u | MEDIUM |
| SR-07 | Hash verifikacija koda između analize i izvršavanja (T-05 iz threat model-a) | HIGH |
