# Oblak

Serverless platforma za izvršavanje Python koda (AWS Lambda-like).

## Pokretanje (lokalno)

### Preduslovi

- Docker & Docker Compose
- Python 3.11+ (za CLI)

### 1. Klonirati repo i ući u folder

```bash
git clone <repo-url>
cd oblak
```

### 2. Podesiti environment varijable

```bash
cp .env.example .env
# Po potrebi izmeniti vrednosti u .env
```

### 3. Pokrenuti server

```bash
docker-compose up --build
```

Server je dostupan na `http://localhost:8000`.  
Swagger dokumentacija: `http://localhost:8000/docs`

### 4. Seed test korisnika (opciono)

```bash
docker-compose exec server python ../scripts/seed.py
```

Kreira korisnike: `admin / admin123`, `alice / alice123`, `bob / bob123`.

---

## CLI — instalacija

```bash
cd cli
pip install -e .
```

## CLI — upotreba

```bash
# Prijava (default server: http://localhost:8000)
oblak login
oblak login --server http://moj-server.com

# Provjera ko si prijavljen
oblak whoami

# Deploy funkcije
oblak deploy hello.py
oblak deploy hello.py --name moja-funkcija
oblak deploy hello.py --requirements requirements.txt

# Lista deployovanih funkcija
oblak list

# Status jedne funkcije
oblak status <id>

# Odjava
oblak logout
```

---

## Struktura projekta

```
oblak/
├── server/                  # FastAPI backend
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── security.py
│   ├── storage.py
│   ├── routes/
│   │   ├── auth.py          # /auth/register, /auth/login, /auth/me
│   │   ├── functions.py     # /functions/upload, /functions/, /functions/{id}
│   │   └── invoke.py        # /invoke/{id}  (stub — implementuje Član 3)
│   ├── models/
│   │   ├── user.py
│   │   ├── function.py
│   │   └── audit_log.py
│   ├── alembic/             # Migracije
│   ├── alembic.ini
│   ├── requirements.txt
│   └── Dockerfile
├── cli/                     # oblak CLI alat
│   ├── pyproject.toml
│   └── oblak/
│       ├── main.py          # typer komande
│       ├── api.py           # httpx klijent
│       └── config.py        # ~/.oblak/config.json
├── docs/
│   ├── architecture.md
│   ├── threat-model.md      # Član 2
│   ├── security-requirements.md  # Član 3
│   └── api.md               # Član 2
├── scripts/
│   └── seed.py
├── storage/                 # Upload fajlovi (git-ignored)
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## API pregled

| Metoda | Ruta | Opis |
|--------|------|------|
| POST | `/auth/register` | Registracija korisnika |
| POST | `/auth/login` | Prijava, vraća JWT token |
| GET | `/auth/me` | Podaci o trenutnom korisniku |
| POST | `/functions/upload` | Upload `.py` fajla |
| GET | `/functions/` | Lista funkcija korisnika |
| GET | `/functions/{id}` | Detalji funkcije |
| POST | `/invoke/{id}` | Izvršavanje funkcije u Firecracker microVM-u |
| GET | `/audit/` | Svi audit logovi (admin), sa filtrima i paginacijom |
| GET | `/audit/me` | Audit logovi trenutnog korisnika |

Puna dokumentacija: `http://localhost:8000/docs`

---

## Tim

| Član | Oblast |
|------|--------|
| Član 1 | Arhitektura, auth, CLI, server skeleton |
| Član 2 | Code analiza, verifikacija, URL generisanje, threat modeling |
| Član 3 | Firecracker izvršavanje, audit, bezbednost, testovi |
