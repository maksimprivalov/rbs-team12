# Threat Model - Oblak platforma

> Metodologija: STRIDE  

---

## 1. Pregled sistema

Oblak je serverless platforma za izvršavanje korisničkog Python koda. Sistem se sastoji od sledećih komponenti:

| Komponenta | Opis                                                       |
|---|------------------------------------------------------------|
| **CDK CLI** | Konzolna aplikacija korisnika - autentikacija, upload koda |
| **Server (FastAPI)** | REST API - auth, storage, analiza, invoke orchestracija    |
| **Code Storage** | Fajlsistem na serveru - čuva .py i requirements.txt        |
| **Code Verifier** | Bandit + pylint + LLM analiza uploadovanog koda            |
| **Firecracker Orchestrator** | Pokreće MicroVM, izvršava kod, vraća output                |
| **MicroVM (MVM)** | Izolovano okruženje za izvršavanje korisničkog koda        |
| **Baza podataka** | SQLite/PostgreSQL - korisnici, funkcije, audit log         |

### Dijagram toka podataka (DFD)

```
[Korisnik] --(HTTPS)--> [CDK CLI] --(HTTPS/JWT)--> [Server]
                                                        |
                                         +--------------+--------------+
                                         v              v              v
                                   [Code Storage] [Code Verifier] [Baza podataka]
                                         |              |
                                         +------+-------+
                                                v
                                    [Firecracker Orchestrator]
                                                |
                                         +------+------+
                                         v      v      v
                                       [MVM] [MVM] [MVM]
```

---

## 2. STRIDE analiza po komponentama

### 2.1 CDK CLI <-> Server komunikacija

#### S - Spoofing (Lažno predstavljanje)

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| S-01 | Napadač presreće JWT token i koristi ga za lažno predstavljanje korisnika | **HIGH** | Kratko vreme trajanja tokena (60 min), HTTPS obavezno |
| S-02 | Napadač šalje zahteve direktno na API zaobilazeći CLI | **LOW** | API je dizajniran da radi i bez CLI-ja; autentikacija štiti resurse |
| S-03 | Phishing CLI alat koji krade korisničke kredencijale | **MEDIUM** | Distribucija CLI-ja samo kroz zvanične kanale; verifikacija hash-a |

#### T - Tampering (Neovlašćena izmena)

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| T-01 | Modifikacija .py fajla u toku transfera (MITM) | **HIGH** | TLS/HTTPS; opciono checksum verifikacija po prijemu |
| T-02 | Zamena uploadovanog fajla u Code Storage nakon analize | **MEDIUM** | Analiza se radi odmah po uploadu; hash fajla čuvati u bazi |

#### R - Repudiation (Poricanje)

| ID | Pretnja | Rizik | Mitigacija                                                |
|---|---|---|-----------------------------------------------------------|
| R-01 | Korisnik poriče da je uploadovao maliciozan kod | **MEDIUM** | Audit log sa user_id, timestamp, hash fajla - append-only |

#### I - Information Disclosure (Curenje informacija)

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| I-01 | JWT token u logu aplikacije ili terminalu | **MEDIUM** | Nikad logovati Authorization header; token čuvati samo u `~/.oblak/config.json` (chmod 600) |
| I-02 | Stack trace u HTTP error response-u otkriva interne detalje | **MEDIUM** | Globalni error handler vraća generičke poruke u produkciji |

#### D - Denial of Service

| ID | Pretnja | Rizik | Mitigacija                                                                  |
|---|---|---|-----------------------------------------------------------------------------|
| D-01 | Flooding upload endpointa velikim fajlovima | **HIGH** | Limit veličine fajla (10MB), rate limiting (OUT OF SCOPE - otvorena stavka) |
| D-02 | Masovni upload zahtevi od jednog korisnika | **MEDIUM** | Rate limiting po korisniku (otvorena stavka)                                |

#### E - Elevation of Privilege (Eskalacija privilegija)

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| E-01 | Korisnik pokušava da pristupi funkcijama drugog korisnika kroz API | **HIGH** | Svaki query filtrira po `user_id` iz JWT tokena |
| E-02 | Regularni korisnik pokušava da pristupi `/admin/audit` endpointu | **HIGH** | `is_admin` provera u middleware-u za admin rute |

---

### 2.2 Code Storage

#### S - Spoofing

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| S-04 | Napadač pogodi putanju storage fajla drugog korisnika | **HIGH** | Putanja sadrži `user_id` iz JWT-a, ne iz URL parametra |

#### T - Tampering

| ID | Pretnja | Rizik | Mitigacija                                                                       |
|---|---|---|----------------------------------------------------------------------------------|
| T-03 | Path traversal napad pri kreiranju storage putanje (`../../etc/passwd`) | **HIGH** | Sanitizacija naziva fajla - dozvoliti samo alfanumeričke znakove i `.py`, `.txt` |
| T-04 | Direktna izmena fajlova na fajlsistemu od strane drugog procesa | **MEDIUM** | Minimalne Unix privilegije za server proces; storage van web root-a              |

#### I - Information Disclosure

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| I-03 | Direktan HTTP pristup storage direktorijumu | **HIGH** | Storage direktorijum nije serviran kao statički fajlovi |
| I-04 | Korisnici mogu da vide kod jedni drugima kroz API | **HIGH** | API endpoints uvek filtriraju po `user_id` |

#### D - Denial of Service

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| D-03 | Punjenje diska uploadovanjem velikog broja fajlova | **MEDIUM** | Kvota po korisniku (otvorena stavka); monitoring diska |

---

### 2.3 Code Verifier

#### S - Spoofing

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| S-05 | Napadač direktno pozove analyze endpoint zaobilazeći upload | **LOW** | Verifikacija se poziva interno iz pipeline-a, nije izložena kao javni API |

#### T - Tampering

| ID | Pretnja                                                                 | Rizik | Mitigacija |
|---|-------------------------------------------------------------------------|---|---|
| T-05 | Izmena koda između analize i izvršavanja u VM-u                         | **HIGH** | Hash koda čuvati pre analize; verifikovati pre pokretanja VM-a |
| T-06 | Prompt injection u LLM analizi - maliciozan kod pokušava da prevari LLM | **MEDIUM** | LLM prompt eksplicitno navodi da je sadržaj nepouzdani korisnički input; Bandit i pylint su deterministički |

#### I - Information Disclosure

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| I-05 | Korisnikov kod se šalje trećoj strani (Anthropic API) | **MEDIUM** | Dokumentovati u ToS; koristiti samo za analizu, ne čuvati na Anthropic strani |

#### D - Denial of Service

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| D-04 | Kod koji namerno usporava Bandit/pylint analizu (kompleksni regex, duboka rekurzija u AST) | **MEDIUM** | Timeout od 30s za svaki alat analize |

#### E - Elevation of Privilege

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| E-03 | Bandit/pylint se pokreću sa privilegijama servera i mogu čitati fajlsistem | **MEDIUM** | Pokretati verifier u ograničenom subprocess okruženju; razmotriti seccomp |

---

### 2.4 Firecracker Orchestrator

#### S - Spoofing

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| S-06 | Lažni invoke zahtev za funkciju koja nije prošla analizu | **HIGH** | Invoke endpoint proverava `status == READY` pre pokretanja VM-a |

#### T - Tampering

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| T-07 | Izmena fajlova unutar VM-a da utiče na host sistem | **HIGH** | Firecracker vKVM izolacija; rootfs montiran read-only gde god moguće |
| T-08 | Inject malicioznog koda kroz environment varijable ili stdin | **MEDIUM** | Kontrolisati sve ulaze u VM; nikad ne prosleđivati env varijable servera u VM |

#### I - Information Disclosure

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| I-06 | Kod unutar VM-a pokušava da čita host fajlove kroz /proc ili /sys | **HIGH** | Network i filesystem namespace izolacija; hidefile za `/proc/*/maps` |
| I-07 | stdout/stderr VM-a sadrži osetljive informacije sa hosta | **MEDIUM** | Sanitizacija output-a pre vraćanja korisniku |

#### D - Denial of Service

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| D-05 | Beskonačna petlja u kodu iscrpljuje CPU hosta | **HIGH** | Timeout od 30s za izvršavanje; CPU cgroup limit po VM-u |
| D-06 | Fork bomb ili memory exhaustion unutar VM-a | **HIGH** | RAM limit po VM-u (npr. 128MB); ulimit unutar VM-a |
| D-07 | Pokretanje velikog broja invoke zahteva paralelno | **MEDIUM** | Limit broja simultanih VM-ova (otvorena stavka) |

#### E - Elevation of Privilege

| ID | Pretnja                                                       | Rizik | Mitigacija |
|---|---------------------------------------------------------------|---|---|
| E-04 | VM escape - exploit Firecracker ranjivosti da pobegne iz VM-a | **HIGH** | Redovno ažuriranje Firecracker verzije; pokretati pod unprivileged korisnikom |
| E-05 | Orchestrator proces ima root privilegije                      | **HIGH** | Pokretati Firecracker pod zasebnim neprivilegovanim korisnikom (`firecracker` user) |

---

### 2.5 Invoke endpoint

#### S - Spoofing

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| S-07 | Napadač pogodi invoke URL druge funkcije | **MEDIUM** | UUID4 URL token je kriptografski nepredvidiv (122 bita entropije) |

#### T - Tampering

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| T-09 | Modifikacija invoke URL-a u bazi da preusmeri na drugi kod | **HIGH** | URL se generiše jednom i ne može se menjati; audit log za svaku izmenu |

#### D - Denial of Service

| ID | Pretnja | Rizik | Mitigacija |
|---|---|---|---|
| D-08 | Masovno pozivanje invoke URL-a | **HIGH** | Rate limiting po IP i per-function (otvorena stavka) |

---

## 3. Otvorene stavke (nije implementirano)

| ID | Opis                                                              | Prioritet |
|---|-------------------------------------------------------------------|---|
| OS-01 | Rate limiting po korisniku i IP adresi                            | HIGH |
| OS-02 | Kvota uploadovanih fajlova i storage po korisniku                 | MEDIUM |
| OS-03 | Anti-virus skeniranje (ClamAV) uploadovanih fajlova               | MEDIUM |
| OS-04 | Horizontalno skaliranje - više Firecracker VM-ova                 | LOW |
| OS-05 | Verifikacija integriteta koda (hash) između analize i izvršavanja | HIGH |
| OS-06 | Seccomp profil za verifier subprocess                             | MEDIUM |
| OS-07 | mTLS između internih komponenti                                   | LOW |

---

## 4. Rezime rizika

| Komponenta | HIGH rizici | MEDIUM rizici | LOW rizici |
|---|---|---|---|
| CLI <-> Server | 3 | 4 | 1 |
| Code Storage | 3 | 2 | 0 |
| Code Verifier | 2 | 3 | 1 |
| Firecracker Orchestrator | 5 | 3 | 0 |
| Invoke endpoint | 2 | 1 | 0 |
| **Ukupno** | **15** | **13** | **2** |

Najveći rizici su koncentrisani oko **Firecracker Orchestrator** komponente zbog prirode izvršavanja nepouzdanog koda. Ključne mitigacije su VM izolacija, resource limiti i redovno ažuriranje Firecracker-a.
