# Oblak

Serverless platforma za izvršavanje Python koda (AWS Lambda-like).

## Pokretanje (lokalno)

### Preduslovi

- Docker & Docker Compose
- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) ili `pip`

### Start

```bash
docker-compose up --build
```

Server je dostupan na `http://localhost:8000`.

### CLI setup

```bash
cd cli
pip install -e .
```

### CLI upotreba

```bash
oblak login                                          # prijava
oblak deploy hello.py                                # deploy funkcije
oblak deploy hello.py --requirements requirements.txt
oblak list                                           # lista funkcija
oblak status <id>                                    # status funkcije
```

## Struktura projekta

```
oblak/
├── server/          # FastAPI backend
├── cli/             # oblak CLI alat
├── docs/            # Dokumentacija
├── scripts/         # SQL seed skripte
├── storage/         # Upload fajlovi (git-ignored)
├── docker-compose.yml
└── README.md
```

## Dokumentacija

- `docs/architecture.md` — dijagram i opis sistema
- `docs/threat-model.md` — STRIDE analiza (Član 2)
- `docs/security-requirements.md` — bezbednosni zahtevi (Član 3)
- `docs/api.md` — opis API ruta

## Tim

| Član | Oblast |
|------|--------|
| Član 1 | Arhitektura, auth, CLI, server skeleton |
| Član 2 | Code analiza, verifikacija, URL generisanje, threat modeling |
| Član 3 | Firecracker izvršavanje, audit, bezbednost, testovi |
