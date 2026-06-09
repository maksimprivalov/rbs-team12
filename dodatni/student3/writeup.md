# Penetration testing - CVE-2007-4559 (Python `tarfile` path traversal)

## 1. Šta je CVE-2007-4559?

CVE-2007-4559 je ranjivost u standardnom Python modulu **`tarfile`**. Metoda
`TarFile.extractall()` (kao i `extract()`) raspakuje članove arhive na disk,
ali **ne proverava** da li ime člana arhive izlazi iz ciljnog direktorijuma.

Ako napadač ubaci člana čije ime sadrži `../` (ili apsolutnu putanju `/...`),
fajl će prilikom raspakivanja biti zapisan **izvan** foldera u koji se navodno raspakuje.

Posledica zavisi od toga gde web proces ima pravo pisanja - u najgorem slučaju
(naš slučaj) vodi do **udaljenog izvršavanja koda (RCE)**.

## 2. Ranjiva aplikacija

Aplikacija ima jednu `submission` formu i jedan ranjivi
endpoint.

```
dodatni/student3/
├── app/
│   ├── app.py            # ranjivi Flask server
│   ├── requirements.txt
│   └── Dockerfile
├── exploit/
│   ├── poc_write.py      # PoC #1: dokaz arbitrary file write
│   ├── exploit.py        # PoC #2: eskalacija u RCE
│   └── requirements.txt
└── writeup.md
```

Ključni (ranjivi) deo servera u [`app/app.py`](app/app.py):

```python
@app.route("/upload", methods=["POST"])
def upload():
    uploaded = request.files["file"]
    archive_path = os.path.join(UPLOAD_DIR, uploaded.filename)
    uploaded.save(archive_path)

    if not tarfile.is_tarfile(archive_path):
        return "Poslati fajl nije validna tar arhiva.", 400

    with tarfile.open(archive_path) as tar:
        tar.extractall(EXTRACT_DIR)   # <-- RANJIVA LINIJA (CVE-2007-4559)
        names = tar.getnames()
    return render_template_string(INDEX_HTML, names=names)
```

Server raspakuje u `app/uploads/extracted/`, a pokreće se sa `debug=True`
(uključen auto-reloader, sto se moze iskoristiti za RCE).

### Pokretanje servera

**Docker:**

```bash
cd dodatni/student3/app
docker build -t cve-2007-4559 .
docker run --rm -p 5000:5000 cve-2007-4559
```

**Ili lokalno:**

```bash
cd dodatni/student3/app
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
python app.py
```

Aplikacija je dostupna na `http://127.0.0.1:5000`.

---

## 3. Eksploatacija

### Korak 1 — Mapiranje aplikacije

Na početnoj strani je formoa koja prima `.tar.gz`.
Upload šalje `POST /upload`.

### Korak 2 — Dokaz path traversal-a (arbitrary file write)

Pravimo `.tar.gz` u kome se ime člana zove `../../PWNED.txt`. Pošto server
raspakuje u `app/uploads/extracted/`, dva nivoa naviše vode u `app/`, pa će
fajl završiti kao `app/PWNED.txt` — **izvan** ciljnog foldera.

Pokretanje:

```bash
cd dodatni/student3
python exploit/poc_write.py http://127.0.0.1:5000
```

Rezultat — fajl je nastao **van** `extracted/` foldera:

Time je potvrđeno da možemo pisati proizvoljan fajl na proizvoljnu putanju
(u granicama dozvola web procesa).

### Korak 3 — Eskalacija u RCE preko Flask debug auto-reload-a

Pošto server radi u **debug modu**, auto reloader stalno prati
izmene `.py` fajlova i **restartuje aplikaciju** čim se neki promeni.

Iskorišćavamo to tako što istom traversal tehnikom **prepišemo sam izvorni
fajl servera** — članom imena `../../app.py`. Novi `app.py` zadržava postojeće
ponašanje, ali dodaje skriveni endpoint.

Čim upload prepiše `app.py`, reloader detektuje izmenu, restartuje proces i
učita naš kod.
