# scripts/firecracker

Pomoćne skripte za postavljanje Firecracker izvršnog okruženja.
Pune detalje vidi u [`docs/firecracker.md`](../../docs/firecracker.md).

| Skripta | Šta radi | Zahteva |
|---|---|---|
| `setup.sh` | Instalira `firecracker` binarku + gostujući kernel, podešava `/dev/kvm` | Linux + KVM, `curl` |
| `build-rootfs.sh` | Pravi ext4 rootfs (Python 3.11 glibc) + ubacuje guest agenta kao init | `docker`, `mkfs.ext4` |
| `smoke_test.py` | Pokreće jedan microVM bez servera (provera da sve radi) | gotov setup |

## Brzi start (Arch Linux / WSL2)

```bash
cd oblak/scripts/firecracker
./setup.sh
./build-rootfs.sh
python smoke_test.py        # očekivani exit_code: 7
```

Ako `smoke_test.py` ispiše `[NEDOSTUPNO] ...`, host nije spreman — poruka kaže
šta nedostaje (binarka, kernel, rootfs ili `/dev/kvm`).
