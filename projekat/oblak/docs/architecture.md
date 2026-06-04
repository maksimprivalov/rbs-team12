# Arhitektura sistema - Oblak

## Pregled

Oblak je serverless platforma za izvršavanje Python koda. Korisnik putem CLI-ja uploaduje Python funkciju, platforma je analizira, priprema okruženje i izvršava u izolovanom Firecracker mikroVM-u.

## Dijagram

```
┌─────────────┐   HTTP/JSON    ┌──────────────────────────────────────────┐
│  oblak CLI  │ ─────────────► │              FastAPI Server               │
│ (~/.oblak/) │ ◄───────────── │                                          │
└─────────────┘                │  /auth/*     /functions/*     /invoke/*  │
                               └───────┬──────────────┬───────────────────┘
                                       │              │
                               ┌───────▼──────┐  ┌───▼──────────────────┐
                               │   SQLite /   │  │   storage/            │
                               │  PostgreSQL  │  │   <user>/<func>/      │
                               │              │  │   main.py             │
                               │  users       │  │   requirements.txt    │
                               │  functions   │  └──────────┬────────────┘
                               │  func_files  │             │
                               │  audit_log   │  ┌──────────▼────────────┐
                               └──────────────┘  │   Code Verifier       │
                                                 │   (Bandit + LLM)      │
                                                 │   → SAFE / REJECTED   │
                                                 └──────────┬────────────┘
                                                            │  SAFE
                                                 ┌──────────▼────────────┐
                                                 │  Firecracker MicroVM  │
                                                 │  - Python runtime     │
                                                 │  - Isolated network   │
                                                 │  - 30s timeout        │
                                                 │  → stdout/stderr      │
                                                 └───────────────────────┘
```

## Komponente

### CLI (`cli/`)
- Typer-bazirani alat instaliran lokalno
- Token se čuva u `~/.oblak/config.json` (chmod 600)
- Komunicira sa serverom isključivo preko HTTP/JSON

### Server (`server/`)
- **FastAPI** - async HTTP framework
- **SQLAlchemy + Alembic** - ORM i migracije
- **JWT Bearer** - autentikacija (HS256, 60 min expiry)
- **passlib/bcrypt** - hash lozinki

### Baza podataka

| Tabela | Opis |
|--------|------|
| `users` | Korisnici, hashed_password, api_key, is_admin |
| `functions` | Deployovane funkcije, status, invoke_url |
| `function_files` | Fajlovi po funkciji (main.py, requirements.txt) |
| `audit_log` | Append-only log svih akcija |

### Storage (`storage/`)
- Fajlovi se čuvaju na disku: `storage/<user_id>/<function_id>/`
- Git-ignored, u Dockeru montiran kao volume
- Validacija: samo `.py` i `requirements.txt`, max 10MB

### Code Verifier
- Bandit - statička analiza bezbednosti
- LLM analiza - detekcija malicioznih obrazaca
- Status funkcije: `PENDING → ANALYZING → SAFE / REJECTED`

### Firecracker Orchestrator 
- Svako izvršavanje = novi MicroVM
- Inject koda u VM filesystem
- Network izolacija, CPU/RAM/timeout limiti
- Po završetku: VM se uništava

## Tok zahteva - deploy i invoke

```
1. oblak deploy hello.py
      ↓
2. POST /functions/upload  (JWT auth)
      ↓
3. Fajl se čuva na disk, status = PENDING
      ↓
4. Code Verifier se poziva automatski
      ↓
5a. REJECTED → fajlovi se brišu, korisnik obavešten
5b. SAFE     → status = READY, invoke_url generisan
      ↓
6. POST /invoke/<uuid>
      ↓
7. Firecracker MicroVM se pokreće, kod se izvršava
      ↓
8. { "output": "...", "exit_code": 0, "duration_ms": 123 }
```
