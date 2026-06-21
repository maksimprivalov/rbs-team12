# API Dokumentacija - Oblak

> Base URL: `http://localhost:8000`  
> Autentikacija: `Authorization: Bearer <JWT_TOKEN>`

---

## Autentikacija

### POST /auth/register
Registracija novog korisnika.

**Request:**
```json
{ "username": "alice", "password": "alice123" }
```
**Response 201:**
```json
{
  "id": 1,
  "username": "alice",
  "api_key": "a3f9...",
  "is_admin": false,
  "created_at": "2025-01-01T12:00:00"
}
```
**Greške:** `409` username zauzet, `422` validacija (username 3–64 alfanumerička, password min 6)

---

### POST /auth/login
Prijava i dobijanje JWT tokena.

**Request:**
```json
{ "username": "alice", "password": "alice123" }
```
**Response 200:**
```json
{ "access_token": "eyJ...", "token_type": "bearer" }
```
**Greške:** `401` pogrešni kredencijali

---

### GET /auth/me
Provera tokena i detalji trenutnog korisnika.

**Response 200:**
```json
{
  "id": 1,
  "username": "alice",
  "api_key": "a3f9...",
  "is_admin": false,
  "created_at": "2025-01-01T12:00:00"
}
```
**Greške:** `401` nevažeći/istekli token

---

## Funkcije

### POST /functions/upload
Upload Python funkcije. Automatski pokreće analizu u pozadini.

**Content-Type:** `multipart/form-data`

| Polje | Tip | Obavezno | Opis |
|---|---|----------|---|
| `name` | string (query) | DA       | Naziv funkcije |
| `file` | `.py` fajl | DA       | Python kod (max 10MB, mora se zvati `main.py` pri čuvanju) |
| `requirements` | `requirements.txt` | NE       | Zavisnosti |

**Response 201:**
```json
{
  "id": 5,
  "name": "moja-funkcija",
  "status": "PENDING",
  "invoke_url": null,
  "created_at": "2025-01-01T12:00:00"
}
```

**Status tok:**
```
PENDING → ANALYZING → READY      (analiza prošla, invoke_url generisan)
                     → REJECTED  (analiza odbila ili pip install pao)
```

**Greške:** `401` nije autentikovan, `413` fajl prevelik, `422` pogrešan tip fajla

---

### GET /functions/
Lista svih funkcija trenutnog korisnika.

**Response 200:**
```json
[
  { "id": 5, "name": "moja-funkcija", "status": "READY", "invoke_url": "/invoke/abc123...", "created_at": "..." },
  { "id": 6, "name": "druga", "status": "REJECTED", "invoke_url": null, "created_at": "..." }
]
```

---

### GET /functions/{id}
Detalji jedne funkcije.

**Response 200:** isto kao element liste gore  
**Greške:** `404` ne postoji ili nije vlasnik

---

### GET /functions/{id}/analysis
Rezultati analize koda (Bandit + pylint + LLM).

**Response 200:**
```json
{
  "function_id": 5,
  "final_verdict": "SAFE",
  "rejection_reason": null,
  "bandit_score": 0,
  "bandit_report": "{ \"high_severity_count\": 0, ... }",
  "pylint_score": 8.5,
  "pylint_report": "...",
  "llm_verdict": "SAFE",
  "llm_report": "{ \"verdict\": \"SAFE\", \"findings\": [], ... }",
  "analyzed_at": "2025-01-01T12:00:05"
}
```

**Response 202** (analiza još u toku):
```json
{ "detail": "Analiza je u toku (status=ANALYZING). Pokušaj ponovo za nekoliko sekundi." }
```

**Greške:** `404` nema rezultata analize

---

## Izvršavanje

### POST /invoke/{token}

Pokretanje funkcije. `token` može biti:
- Integer `function_id` (autentikovan korisnik, mora biti vlasnik)
- UUID hex string iz `invoke_url` polja funkcije (autentikovan korisnik)

Funkcija mora biti u statusu `READY`. Svaki poziv se beleži u `audit_log`.

**Response 200:**
```json
{
  "output": "Hello from Oblak!\n",
  "exit_code": 0,
  "duration_ms": 243
}
```

**Timeout response 200** (izvršavanje trajalo >30s):
```json
{
  "output": "Execution timed out after 30 seconds.",
  "exit_code": -1,
  "duration_ms": 30012
}
```

**Greške:** `401` nije autentikovan, `404` funkcija ne postoji, `409` status nije READY

---

## Admin

### GET /admin/audit

Lista svih audit log unosa, sortirana od najnovijeg ka najstarijem. Samo admin korisnici.

**Query parametri:**
| Parametar | Tip | Default | Opis |
|---|---|---|---|
| `limit` | int | 100 | Broj unosa (1–1000) |
| `offset` | int | 0 | Offset za paginaciju |

**Response 200:**
```json
[
  {
    "id": 42,
    "user_id": 1,
    "action": "FUNCTION_INVOKE",
    "details": "function_id=5 exit_code=0 duration_ms=132 timed_out=False",
    "timestamp": "2025-01-01T12:05:00"
  }
]
```

**Akcije koje se beleže:** `REGISTER`, `LOGIN`, `LOGIN_FAILED`, `FUNCTION_UPLOAD`, `FUNCTION_ANALYSIS_REJECTED`, `FUNCTION_READY`, `FUNCTION_INVOKE`, `FUNCTION_ANALYSIS_ERROR`

**Greške:** `401` nije autentikovan, `403` nije admin

---

## Statusi funkcija

| Status | Opis                                                  |
|---|-------------------------------------------------------|
| `PENDING` | Uploadovana, čeka analizu                             |
| `ANALYZING` | Analiza u toku (Bandit + pylint + LLM)                |
| `SAFE` | Analiza prošla, pip install u toku                    |
| `READY` | Spremna za izvršavanje, invoke_url dostupan           |
| `REJECTED` | Analiza odbila ili pip install pao - fajlovi obrisani |
