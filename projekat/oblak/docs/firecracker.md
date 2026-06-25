# Firecracker izvršavanje koda

Ovaj dokument opisuje kako Oblak izvršava korisnički Python kod u izolovanim
[Firecracker](https://firecracker-microvm.github.io/) microVM-ovima.

> **Važno:** Firecracker radi isključivo na **Linux-u sa KVM-om** (`/dev/kvm`).
> Ne radi na Windows-u/macOS-u direktno, niti u običnom Docker kontejneru bez
> privilegija. Razvojno okruženje: WSL2 (nested virtualizacija), produkcija:
> Arch Linux bare-metal.

## Arhitektura izvršavanja

Svaki poziv `POST /invoke/{id}` pokreće **nov, jednokratan microVM**:

```
            host (FastAPI server)                    guest (microVM)
  ┌─────────────────────────────────────┐   ┌──────────────────────────────┐
  │ run_microvm(function_dir)           │   │ PID1 = /usr/local/bin/        │
  │  1. mkfs.ext4 -d  → job.ext4        │   │        oblak-run.py           │
  │     (main.py + venv/)               │   │  - mount /proc,/sys,/dev,/tmp │
  │  2. firecracker --api-sock          │   │  - mount /dev/vdb (ro) → /job │
  │  3. PUT /boot-source /drives        │──▶│  - subprocess: python main.py │
  │     /machine-config /actions        │   │    (timeout, bez mreže)       │
  │  4. čita serijsku konzolu           │◀──│  - JSON rezultat na ttyS0     │
  │  5. parsira ===OBLAK-RESULT-...===  │   │  - reboot() → VM se gasi      │
  │  6. briše temp + vraća rezultat     │   └──────────────────────────────┘
  └─────────────────────────────────────┘
```

- **Ulaz (kod) →** ubacuje se preko zasebnog ext4 "job" drive-a (`/dev/vdb`),
  napravljenog bez root-a (`mkfs.ext4 -d`). Rootfs (`/dev/vda`) je deljen i
  **read-only** → bezbedno za paralelne VM-ove.
- **Izlaz (rezultat) →** guest agent štampa JSON (sa base64 stdout/stderr)
  između sentinela na serijsku konzolu; host hvata `stdout` Firecracker procesa
  i parsira ga. Ovo razdvaja korisnikov stdout od "omota" rezultata.

## Bezbednosna svojstva

| Mehanizam | Realizacija |
|---|---|
| Izolacija procesa | Zaseban microVM (KVM), poseban kernel + user-space |
| Mrežna izolacija | Nijedan network interfejs se ne konfiguriše → nema mreže |
| Read-only rootfs | `is_read_only: true`; upisi samo u tmpfs `/tmp` |
| Limit CPU/RAM | `vcpu_count`, `mem_size_mib` (machine-config) |
| Timeout | guest-side (`subprocess timeout`) + host-side (wall-clock kill) |
| Jednokratnost | Po izvršenju VM se gasi i `job.ext4` se briše |

**Otvorene stavke (TODO):**
- **Jailer**: pokretati Firecracker kroz `jailer` (chroot, cgroups, seccomp,
  user namespacing) umesto direktno. Trenutno se pokreće bez jailer-a.
- **cgroups limiti** na host strani (CPU quota, pids, I/O) preko jailer-a.
- **Konkurentni limit**: broj paralelnih VM-ova nije ograničen (pool/semafor).
- **Veliki output**: čitanje konzole je posle exit-a; vrlo velik stdout pre
  gašenja može popuniti pipe buffer. Rešenje: čitanje u zasebnom thread-u ili
  limit na veličinu izlaza.

## Postavljanje (Arch Linux / WSL2)

```bash
cd oblak/scripts/firecracker

# 1. Firecracker binarka + gostujući kernel + /dev/kvm dozvole
./setup.sh

# 2. rootfs sa Python 3.11 (glibc) + guest agentom (zahteva docker)
./build-rootfs.sh

# 3. (opciono) smoke test bez servera
python ../../scripts/firecracker/smoke_test.py
```

Skripte podrazumevano pišu artefakte u **`oblak/fc-assets/`** — isti folder koji
`server/config.py` čita (`firecracker_assets`). Ne treba ništa da podešavaš:

```
oblak/fc-assets/
├── vmlinux        # kernel (setup.sh)
└── rootfs.ext4    # rootfs sa Pythonom + agentom (build-rootfs.sh)
```

`firecracker` binarka ide na `PATH` (setup.sh je stavlja u `/usr/local/bin`);
`config.py` je traži po `PATH`-u. `fc-assets/` je u `.gitignore` (veliki binarni
fajlovi). Putanje se menjaju samo ako baš želiš — preko `FIRECRACKER_ASSETS`.

### WSL2 napomena

Potrebna je nested virtualizacija (Windows 11) i `kvm` modul. Ako `/dev/kvm`
ne postoji, `setup.sh` će to prijaviti. Server se u tom okruženju pokreće
direktno u WSL-u (ne kroz Windows Docker Desktop), da bi imao pristup `/dev/kvm`.

## Konfiguracija

| Env var | Default | Opis |
|---|---|---|
| `FIRECRACKER_ENABLED` | `true` | Globalni prekidač |
| `FIRECRACKER_BIN` | `firecracker` | Binarka (po `PATH`-u ili puna putanja) |
| `FIRECRACKER_ASSETS` | `oblak/fc-assets` | Folder sa `vmlinux` i `rootfs.ext4` |
| `FIRECRACKER_VCPU` | `1` | Broj vCPU po VM-u |
| `FIRECRACKER_MEM_MIB` | `256` | RAM po VM-u (MiB) |
| `FIRECRACKER_EXEC_TIMEOUT` | `30` | Timeout izvršavanja koda (s) |

## Ponašanje na nepodržanom hostu

Na Windows-u (ili bilo gde bez KVM-a/binarke) server se i dalje normalno pokreće.
`POST /invoke/{id}` vraća **503** sa jasnom porukom iz `preflight()`
(npr. „/dev/kvm ne postoji"). Tako je razvoj ostatka sistema moguć i bez
Firecracker-a, a sam invoke je dostupan tek na Linux+KVM hostu.
