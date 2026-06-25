# Pokretanje i testiranje cele aplikacije

Vodič kako da pokreneš **Firecracker + server + CLI** zajedno i istestiraš ih
benignim i malicioznim primerima. Sve se izvršava u **WSL2/Linux-u** (zbog KVM-a).

## Preduslovi (jednom)

```bash
# 1. Firecracker okruženje (binarka + kernel + rootfs u oblak/fc-assets/)
cd oblak/scripts/firecracker
./setup.sh
./build-rootfs.sh
python smoke_test.py        # mora da prođe pre dalje (vidi docs/firecracker.md)
```

Ako `smoke_test.py` javi problem sa `/dev/kvm`, reši pristup pre nego što kreneš
(vidi „WSL caveat" u [firecracker.md](firecracker.md)).

## 1. Pokreni server (terminal A)

```bash
cd oblak
./scripts/run_server.sh
```

Skripta napravi `.venv`, instalira server + CLI, seed-uje korisnike
(`admin/alice/bob`) i pokrene server na `http://localhost:8000`. Ostavi ga da radi.

## 2. End-to-end demo (terminal B)

```bash
cd oblak
. .venv/bin/activate          # isti venv kao server (ima httpx)
python scripts/demo.py
```

Demo deploy-uje sve primere iz `tests/examples/`, sačeka analizu i pozove one koji
prođu. Očekivani ishod:

| Primer | Ishod | Zašto |
|---|---|---|
| `benign/hello.py` | READY → izvršen | čist kod, ispiše poruku |
| `benign/compute.py` | READY → izvršen | CPU posao (prosti brojevi) |
| `benign/with_deps.py` | READY → izvršen | `cowsay` instaliran u venv, radi u VM-u |
| `malicious/exfil.py` | **REJECTED** | Bandit B602 (shell=True) HIGH |
| `malicious/reverse_shell.py` | **REJECTED** | Bandit B602 HIGH |
| `malicious/destroy.py` | **REJECTED** | Bandit B602 HIGH |
| `isolation/infinite_loop.py` | READY → **timed_out=true** | VM timeout obuzda petlju |
| `isolation/no_network.py` | READY → "mreža izolovana" | VM nema mrežu |

> Maliciozni primeri su pisani da grade komandu iz **promenljive** (`shell=True` +
> varijabla), jer baš to Bandit ocenjuje kao HIGH; `shell=True` sa string literalom
> je LOW i ne bi bio odbijen. Ako postaviš `ANTHROPIC_API_KEY`, LLM sloj hvata i
> šire obrasce (i tada `isolation/*` mogu biti odbijeni pre izvršavanja).

## 3. Ručno preko CLI-ja (alternativa demou)

```bash
. .venv/bin/activate
oblak login                       # alice / alice123
oblak deploy tests/examples/benign/hello.py
oblak list                        # vidi ID i status (sačekaj READY)
oblak invoke <ID>                 # pokreni u microVM-u
oblak analysis <ID>               # zašto je nešto SAFE/REJECTED

# primer sa zavisnostima
oblak deploy tests/examples/benign/with_deps.py \
  -r tests/examples/benign/requirements.txt -n cowsay-demo

# maliciozni (biće REJECTED)
oblak deploy tests/examples/malicious/exfil.py
oblak analysis <ID>               # videće se Bandit razlog
```

## Šta koji sloj radi

```
oblak CLI ──upload──► server ──analiza (Bandit/pylint/LLM)──► READY/REJECTED
                                  └─ READY ──invoke──► Firecracker microVM ──► output
```

- **Analiza** odbija očigledno opasan kod pre nego što se ikad pokrene.
- **microVM** je druga linija odbrane: i kod koji prođe analizu izvršava se izolovano
  (bez mreže, sa CPU/RAM/timeout limitom, read-only rootfs, pa se VM uništi).
