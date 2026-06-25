# Bezbednosni zahtevi - Oblak platforma

> Metodologija: threat-driven security requirements
> Komponenta: Execution engine (Firecracker MicroVM + subprocess sandbox)
> Odgovornost: Clan 3

---

## 1. Uvod i kontekst

Oblak platforma prima i izvrsava **proizvoljni Python kod** od nepouzdanih korisnika. Ovaj kod je po definiciji nepouzdani unos i moze da sadrzi:

- pokusaje citanja osetljivih fajlova na hostu (`/etc/passwd`, baza, storage ostalih korisnika)
- shell injection (`os.system`, `subprocess`, `eval`)
- mrezne napade (skeniranje portova, eksfiltracija podataka)
- namerno trosenje resursa (fork bomb, beskonacna petlja, memorijska eksplozija)
- pokusaje eskalacije privilegija ili bekstva iz sandbox-a

Execution engine mora spreciti sve navedene klase napada, **nezavisno od toga da li je verifikator (Bandit/LLM) propustio maliciozan kod**.

### 1.1 Arhitektura izvrsavanja

```
POST /invoke/{id}
    |
    +-- firecracker.is_available() == True?
    |       |
    |       \-- firecracker.py  ->  Firecracker MicroVM  (primarni runtime)
    |
    \-- False
            |
            \-- sandbox.py     ->  subprocess sandbox    (fallback / razvoj)
```

Primarni runtime je **Firecracker MicroVM** - hardverska izolacija na nivou KVM. Subprocess sandbox se koristi kao fallback tamo gde KVM nije dostupan (Windows, CI, development).

---

## 2. Izolovanost procesa u Firecrackeru

### 2.1 Sta je Firecracker MicroVM

Firecracker je AWS-ov open-source VMM (Virtual Machine Monitor) koji koristi Linux KVM za pokretanje ultra-lakih virtualnih masina (microVM). Svaka funkcija se izvrsava u **zasebnom MicroVM-u koji zivi tacno onoliko dugo koliko traje izvrsavanje**, a zatim se unistava.

Za razliku od Docker kontejnera, koji dele kernel sa hostom, Firecracker MicroVM ima:
- **sopstveni kernel** (ne vidi host kernel procese)
- **sopstveni virtuelni hardver** (virtio-blk drive, nema pristupa host `/dev`)
- **KVM VM boundary** - bekstvo iz VM-a zahteva KVM exploit, sto je neuporedivo teze od bekstva iz Docker kontejnera

### 2.2 Sta VM moze, a sta ne moze

| Akcija | Dozvoljeno | Objasnjenje |
|---|:---:|---|
| Citati korisnikov `main.py` | DA | Montira se read-only sa `/dev/vdb` (code drive) |
| Pisati na rootfs | NE | Rootfs je montiran sa `is_read_only: true` |
| Citati fajlove host OS-a | NE | VM boundary - host fajlsistem nije vidljiv unutar VM-a |
| Videti storage ostalih korisnika | NE | VM nema pristup host `/dev`, `/proc`, `/sys` |
| Ostvariti mrezne konekcije | NE | Mrezni interfejs nije konfigurisan (videti sekciju 3) |
| Komunicirati sa serverskim procesom | NE | Nema shared memorije, nema socketa izmedju hosta i VM-a |
| Pokrenuti novi proces unutar VM-a | DA | Dozvoljeno unutar VM-a, izolovan od hosta |
| Eskalirati privilegije na hostu | NE | KVM VM boundary + Firecracker seccomp profil |
| Prekoraciti RAM limit | NE | MEM_SIZE_MIB = 128 - OOM kill unutar VM-a |

### 2.3 Code injection mehanizam

Korisnikov kod ne ulazi u VM kroz mrezu niti kroz environment - koristi se **virtio-blk drive**:

```
1. dd if=/dev/zero  ->  prazan ext4 fajl (8 MB, temp direktorijum)
2. mkfs.ext4        ->  formatiran ext4 filesystem
3. debugfs -w       ->  write main.py /main.py  (bez montiranja, bez root-a)
4. Firecracker      ->  /drives/code montira ext4 kao /dev/vdb, is_read_only: true
5. /init (guest)    ->  mount /dev/vdb /code && python3 /code/main.py 2>&1
6. Cleanup          ->  kill VM, rm -rf /tmp/fc_*
```

Svaki invoke kreira **novu, svezu** ext4 sliku - nema deljenja izmedju funkcija ni korisnika.

### 2.4 Guest init skripta

Rootfs sadrzi custom `/init` koji:

```sh
#!/bin/sh
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /tmp

mkdir -p /code
mount /dev/vdb /code -o ro    # code drive, read-only

python3 /code/main.py 2>&1    # output ide na serial (ttyS0)
echo "EXIT_CODE:$?"

echo o > /proc/sysrq-trigger  # cleanly shutdown VM
```

Orkestrator cita serial output (Firecracker stdout), parsira `EXIT_CODE:N` i vraca rezultat korisniku. VM se gasi sam posle izvrsavanja - nema "idle" VM-ova koji trose resurse.

---

## 3. Network policy za VM

### 3.1 Trenutna implementacija - bez mreze

Firecracker VM **nema konfigurisan mrezni interfejs**. U konfiguraciji se ne poziva `PUT /network-interfaces/...`, pa guest kernel ne vidi `eth0`. Jedini uredjaj vidljiv unutar VM-a je virtio-blk code drive (`/dev/vdb`).

Posledica: korisnikov kod ne moze da:
- otvori TCP/UDP socket prema spoljnom svetu
- skenira portove
- eksfiltrira podatke
- preuzme malware

### 3.2 Mrezna izolacija na nivou hosta

Cak i bez konfiguracije mreznog interfejsa u Firecrackeru, host-level odbrana ostaje aktivna:

| Sloj | Mehanizam | Status |
|---|---|---|
| VM level | Nema `eth0` u guestu | Implementirano |
| Host iptables | Blokirati outbound sa KVM bridge interfejsa | Otvorena stavka |
| Seccomp | Blokirati `socket()` syscall unutar Firecracker procesa | Otvorena stavka |

### 3.3 Buduca implementacija sa TAP device-om

Za scenarije gde je potreban mrezni pristup unutar VM-a (npr. `pip install` u runtime-u), preporucena arhitektura:

```
VM (eth0) <-> TAP device (fc_tap0) <-> host bridge
                                           |
                                      iptables FORWARD:
                                      - DROP all by default
                                      - ACCEPT tcp dport 443 (PyPI, HTTPS)
                                      - ACCEPT udp dport 53  (DNS)
                                      - DROP sve ostalo
```

---

## 4. Resource limits

Svaki MicroVM ima fiksirane resource limite koji se ne mogu prekoraciti:

### 4.1 Firecracker resource limits (VM level)

| Resurs | Limit | Mehanizam |
|---|---|---|
| vCPU broj | 1 | `vcpu_count: 1` u machine-config |
| RAM | 128 MB | `mem_size_mib: 128` - OOM kill unutar VM-a ako se prekoraci |
| Vreme izvrsavanja | 30 sekundi | `fc_proc.wait(timeout=30)` -> `SendCtrlAltDel` -> kill |
| Output velicina | 64 KB | Truncuje se u orkestratorsu pre vracanja korisniku |
| Disk (rootfs) | ~512 MB | Fiksna velicina slike, read-only |
| Disk (code drive) | 8 MB | Fiksna velicina ext4 slike |

### 4.2 Subprocess sandbox resource limits (fallback, Linux)

Kada Firecracker nije dostupan, sandbox koristi OS-level limite:

| Resurs | Limit | Mehanizam |
|---|---|---|
| CPU vreme | 30 sekundi | `resource.RLIMIT_CPU` - kernel salje SIGKILL |
| Virtuelna memorija | 128 MB | `resource.RLIMIT_AS` - OOM kill |
| Broj procesa | 50 | `resource.RLIMIT_NPROC` - sprecava fork bomb |
| Vreme izvrsavanja | 30 sekundi | `subprocess.run(..., timeout=30)` |
| Output velicina | 64 KB | Truncuje se pre vracanja |

### 4.3 Ponasanje pri prekoracenju limita

| Scenario | Firecracker | Sandbox |
|---|---|---|
| Prekoracen RAM | OOM kill unutar VM-a, VM exituje | SIGKILL od kernel-a, exit_code=-9 |
| Prekoracen CPU (vreme) | Timeout handler ubija VM | SIGKILL od kernel-a |
| Timeout 30s | SendCtrlAltDel -> wait(2s) -> kill() | TimeoutExpired -> kill subprocess |
| Fork bomb | Izolovano unutar VM-a | RLIMIT_NPROC=50 ogranicava procese |

---

## 5. Privilegije pod kojima se Firecracker pokrce

### 5.1 Firecracker proces

Firecracker proces se pokrce kao **isti korisnik pod kojim radi FastAPI server** (unutar Docker kontejnera). Korisnik nije `root`.

Za pristup `/dev/kvm` dovoljno je da korisnik bude u `kvm` grupi:

```bash
# setup-firecracker.sh:
sudo usermod -aG kvm $USER
sudo chmod 660 /dev/kvm
```

### 5.2 Docker kontejner

| Podesavanje | Vrednost | Znacaj |
|---|---|---|
| `USER` u Dockerfile | root (trenutno, otvorena stavka) | Server radi kao root u kontejneru - videti SR-01 |
| `--privileged` | NE | Kontejner nije privilegovan |
| `devices: /dev/kvm` | DA | Samo KVM uredjaj je eksponiran, ne ceo `/dev` |
| Volumes | `./storage` i `/opt/firecracker` (read-only) | Minimalan skup mount-ova |

### 5.3 Firecracker seccomp profil

Firecracker podrazumevano primenjuje **vlastiti seccomp-bpf profil** koji blokira syscall-e koje VMM ne treba. Guest kernel unutar VM-a ima sopstveni syscall prostor i ne moze direktno pozvati host syscall-e.

### 5.4 Preporucena produkcijska konfiguracija

```
[host] oblak korisnik (UID 1000, gid: oblak, kvm)
    \-- [docker] python:3.11-slim
          \-- USER oblak (ne root)
                \-- firecracker --api-sock /tmp/fc.sock
                      \-- KVM MicroVM (izolovan)
```

---

## 6. Sta se desava pri crash-u VM-a

Orkestrator (`firecracker.py`) koristi `try/finally` blok koji **garantuje cleanup** bez obzira na razlog zaustavljanja VM-a:

```python
try:
    fc_proc = subprocess.Popen([FIRECRACKER_BIN, ...])
    # ... konfiguracija i pokretanje VM-a ...
    fc_proc.wait(timeout=EXECUTION_TIMEOUT)
except subprocess.TimeoutExpired:
    # VM nije zavrsio na vreme
    _api_call(sock_path, "PUT", "/actions", {"action_type": "SendCtrlAltDel"})
    fc_proc.wait(timeout=2)
    fc_proc.kill()   # kill ako i dalje zivi
finally:
    if fc_proc.poll() is None:
        fc_proc.kill()
    shutil.rmtree(work_dir, ignore_errors=True)   # uvek se brise
```

### 6.1 Scenariji i posledice

| Scenario | Sta se desava | Zastita |
|---|---|---|
| Normalan zavrsetak | VM exituje, serial output citan, cleanup | finally brise temp dir |
| Timeout (>30s) | SendCtrlAltDel -> cekanje 2s -> kill() | TimeoutExpired + finally |
| OOM unutar VM-a | VM kernel salje OOM kill guestu, VM se gasi | Normalan VM exit, finally |
| VM kernel panic | Firecracker primecuje VM exit, returncode != 0 | finally hvata i cisti |
| Firecracker binarni crash | fc_proc.poll() vraca kod, finally se okida | finally brise temp dir |
| Exception u orkestratoruu | Python exception propagira kroz finally | finally garantuje cleanup |
| Disk pun (temp dir kreacija) | tempfile.mkdtemp() baca OSError | HTTP 500, global error handler |
| KVM nedostupan u runtime-u | firecracker.is_available() -> fallback na sandbox | Sandbox preuzima |

### 6.2 Garantovano ciscenje resursa

U **svim** scenarijima:
- Firecracker VM proces je ubijen (ne ostaje "zombie" VM)
- Privremeni direktorijum (`/tmp/fc_*`) je obrisan, ukljucujuci:
  - `fc.sock` - API socket
  - `code.ext4` - code drive sa korisnickim kodom
  - `serial.log` - serial output
  - `fc.log` - Firecracker interni log
- Nema "leaky" state izmedju invokacija

---

## 7. Pre-execution verifikacija (prva linija odbrane)

Bezbednost execution engine-a je **druga linija odbrane**. Prva je Code Verifier koji blokira maliciozne funkcije pre nego sto uopste dobiju status `READY`:

```
Upload -> PENDING -> ANALYZING -> REJECTED  (ne moze biti invokirana)
                              -> READY     (tek tada invoke postaje moguc)
                   |
                   +-- Bandit   -- HIGH severity nalaz -> REJECTED
                   +-- pylint   -- informativan, ne blokira
                   \-- LLM      -- MALICIOUS/SUSPICIOUS -> REJECTED
```

Execution engine je projektovan da bude siguran **cak i kada verifikator promasil** - defense in depth princip.

---

## 8. Audit trail

Svaki invoke poziv se belezi u `audit_log` tabelu (append-only):

| Polje | Vrednost |
|---|---|
| `action` | `FUNCTION_INVOKE` |
| `user_id` | ID korisnika koji je pozvao |
| `details` | function_id, runtime (firecracker/sandbox), exit_code, duration_ms, timed_out |
| `timestamp` | UTC timestamp |

Logovi nisu dostupni za brisanje kroz API - samo admin moze citati putem `GET /admin/audit`.

---

## 9. Otvorene stavke

| ID | Opis | Prioritet |
|---|---|---|
| SR-01 | Dodati `USER oblak` u Dockerfile - server ne treba da radi kao root | HIGH |
| SR-02 | Host-level iptables pravila za blokiranje outbound saobracaja sa KVM bridge-a | HIGH |
| SR-03 | Hash verifikacija koda izmedju analize i izvrsavanja (T-05 iz threat-model.md) | HIGH |
| SR-04 | Seccomp-bpf profil za Firecracker proces na hostu (dopunski uz Firecracker-ov interni) | MEDIUM |
| SR-05 | Rate limiting invoke endpoint-a po korisniku i IP-u | MEDIUM |
| SR-06 | Disk quota po korisniku za storage direktorijum | MEDIUM |
| SR-07 | Mrezni pristup unutar VM-a sa whitelist politikom (TAP + iptables) | LOW |
| SR-08 | Rotacija Firecracker rootfs slike - periodicno rebuild za security patch-eve | LOW |
