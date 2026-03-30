# Mehanizam za logovanje događaja — Secrets Management sistem

Kontekst: sistem za čuvanje i deljenje tajni (lozinki, API ključeva, sertifikata), sličan Infisical-u. Centralizovana platforma za logove: ELK stack (Elasticsearch, Logstash, Kibana) + Filebeat.


## 1. Strukturirano logovanje (troubleshooting)

Aplikacija emituje logove u JSON formatu sa obaveznim poljima:

- **timestamp** — ISO 8601 sa timezone (2025-03-30T14:22:05.123Z)
- **level** — DEBUG, INFO, WARN, ERROR, FATAL
- **service** — naziv mikroservisa (secrets-api, auth-service...)
- **traceId** — za korelaciju zahteva kroz više servisa
- **message** — opis događaja
- **context** — endpoint, HTTP metoda, status kod, IP adresa, trajanje

U produkciji se loguje INFO i više. DEBUG samo u development-u. Za smanjenje noise-a: rate limiting repetitivnih logova, sampling health check-ova.


## 2. Non-repudiation (neporicanje odgovornosti)

OWASP kaže: svaki log mora sadržati "kada, gde, ko, šta". Obavezno se loguju:

- Autentifikacija — uspeli/neuspeli login, MFA, odjava, istek sesije
- CRUD nad tajnama — kreiranje, čitanje, ažuriranje, brisanje
- Pristupna kontrola — promena uloga, dozvola, dodavanje korisnika
- Admin akcije — promena konfiguracije, rotacija ključeva

Svaki audit zapis sadrži: actorId, actorType (user/service-token/api-key), actorIp, action, resource, outcome (success/failure).

Audit logovi idu u **poseban ES indeks** (audit-secrets-YYYY.MM.dd), odvojen od operativnih. To omogućava lako izdvajanje i pretragu. Za integritet: append-only pristup, RBAC, opciono HMAC heširanje.

OWASP napomena: non-repudiation je teško postići samo logovima jer se verodostojnost zasniva na reviziji logging strane, a digitalni potpisi su teški za implementaciju.


## 3. Zaštita osetljivih podataka

Nikada se ne loguju: vrednosti tajni (lozinke, API ključevi, tokeni), sesijski ID-evi, enkripcioni ključevi, PII. Za tajne se loguju samo reference (secretId, secretPath).

Dvoslojna zaštita (defense in depth):

1. **Aplikacioni nivo** — redaction filter sa regex pattern matching-om pre pisanja u log
2. **Logstash nivo** — mutate filter koji briše/maskira osetljiva polja pre indeksiranja

Čak i ako app greškom propusti osetljiv podatak, Logstash ga presretne.


## 4. Pouzdanost, dostupnost i integritet

- ES klaster — min. 3 čvora, replikacija indeksa (replicas: 1) za visoku dostupnost
- Filebeat persistent queue — baferuje logove ako Logstash/ES nije dostupan
- TLS enkripcija za svu komunikaciju: Filebeat→Logstash→ES→Kibana
- RBAC u Elasticsearch-u — različite uloge za pisanje, čitanje, administraciju
- Log fajlovi na posebnoj particiji od OS-a (OWASP preporuka)
- Greške u logging procesu ne smeju blokirati rad aplikacije (asinhrono logovanje)
- Backup: snapshot-ovi ES indeksa na S3/MinIO


## 5. Precizno vremensko označavanje

Svi serveri koriste NTP (Network Time Protocol) sinhronizaciju. Format: ISO 8601 + UTC. Logstash date filter parsira timestamp iz loga i postavlja @timestamp polje. ES dodatno beleži vreme prijema — velika razlika između ta dva vremena ukazuje na manipulaciju ili NTP drift.

U Docker okruženju kontejneri nasleđuju sat host mašine, pa se NTP konfiguriše na host nivou.


## 6. Rotacija logova i urednost

### 6.1 Logrotate (tradicionalni sistemi)

Standardni Linux alat za rotaciju, kompresiju i brisanje logova. Pokreće se putem cron-a kao root.

Primer konfiguracije:

```
/var/log/secrets-api/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    su root loggroup    # KRITIČNO za mitigaciju
}
```

**Poznate ranjivosti:**

- **Race condition (CVE-2011-1098, logrotten exploit)** — ako logrotate radi kao root i korisnik kontroliše putanju log direktorijuma, napadač koristi inotify da zameni direktorijum symlink-om ka proizvoljnom direktorijumu (npr. /etc/bash_completion.d/). Pogođene verzije: 3.8.6, 3.11.0, 3.15.0. Iskorišćeno protiv GitLab-a (HackerOne #578119).
- **Shell injection (CVE-2011-1154)** — specijalni karakteri u imenima fajlova + shred direktiva → izvršavanje komandi kao root
- **DoS (CVE-2011-1155)** — newline/backslash u nazivima fajlova prekida rad logrotate-a

**Mitigacija:** koristiti `su` direktivu (ne radi kao root), log putanja u vlasništvu root-a, SELinux/AppArmor, redovno ažuriranje.

### 6.2 Docker log rotacija

Docker podrazumevano NE rotira logove (json-file driver). Konfiguracija u /etc/docker/daemon.json:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  }
}
```

Ili po servisu u docker-compose.yml:

```yaml
services:
  secrets-api:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "5"
```

max-size = maks. veličina fajla pre rotacije, max-file = broj čuvanih fajlova. Važi samo za nove kontejnere.


## 7. ELK Stack — komponente i integracija

Tok: **Filebeat → Logstash → Elasticsearch → Kibana**

**Filebeat** — laki agent na svakom hostu, prati log fajlove i šalje na Logstash. Koristi registar pozicije u fajlu (ne šalje ponovo pročitane redove) i persistent queue za otpornost na prekide.

**Logstash** — pipeline sa 3 sekcije:

- **Input:** prima od Beats na portu 5044 sa TLS-om
- **Filter:** json{} za parsiranje JSON logova; grok{} za nestrukturirane logove (syslog, Apache) koristeći pattern-e poput %{SYSLOGTIMESTAMP}, %{COMBINEDAPACHELOG}; date{} za postavljanje @timestamp; mutate{} za redakciju osetljivih podataka i tagovanje audit događaja
- **Output:** dva ES indeksa — logs-secrets-YYYY.MM.dd (operativni) i audit-secrets-YYYY.MM.dd (audit)

Grok sintaksa: %{SYNTAX:SEMANTIC} — SYNTAX je pattern koji se matchuje, SEMANTIC je naziv polja. Logstash dolazi sa ~120 predefinisanih pattern-a. Za testiranje: Grok Debugger u Kibani.

**Elasticsearch** — distribuirani search engine, indeksira u inverted index strukturu (Apache Lucene). Ključna konfiguracija:

- Index templates — automatski primenjuju mapiranja na nove indekse
- ILM (Index Lifecycle Management) — faze: hot (aktivan) → warm (stariji, manje shard-ova) → cold (zamrznut) → delete. Audit logovi se čuvaju min. 365 dana.
- Bezbednost: xpack.security, TLS za transport i HTTP, RBAC, audit logging samog klastera

**Kibana** — vizualizacioni sloj:

- **Discover** — pretraga i filtriranje po vremenu, IP-u, korisniku, tipu događaja
- **Dashboardi** — real-time paneli (pristupi tajnama po korisniku, neuspeli logini po IP-u, timeline audit događaja, geo-distribucija pristupa)
- **Alerting** — npr. >5 neuspelih logina sa iste IP za 5 minuta
- **SIEM** — ugrađena aplikacija sa stotinama pravila usklađenih sa MITRE ATT&CK framework-om


## 8. Zaštita od Log Injection

OWASP definiše Log Injection kao ubacivanje malicioznih podataka u logove. Vrste napada:

- Falsifikovanje zapisa — prikrivanje maliciozne aktivnosti ili okrivljavanje drugog korisnika
- XSS preko logova — JS kod koji se izvršava u web viewer-u logova
- RCE — u najgorem slučaju izvršavanje koda (Log4Shell / Log4j, 2021.)
- DoS — preplavljivanje logova radi iscrpljivanja diska

Mere zaštite: sanitizacija ulaza (uklanjanje CR/LF/delimiter karaktera), strukturirano logovanje (JSON), allow-list pristup za korisnički ulaz, nikad string konkatenacija sa korisničkim podacima.


## Sumarna tabela

| Zahtev | Rešenje | Alat |
|--------|---------|------|
| Troubleshooting | JSON logovi sa obaveznim poljima | SLF4J/Winston/Pino |
| Non-repudiation | Poseban audit indeks, who/what/when/where | ES + Kibana Data View |
| Osetljivi podaci | Dvoslojna redakcija (app + Logstash) | Regex + mutate plugin |
| Pouzdanost/integritet | Klaster, replikacija, TLS, RBAC | ES cluster + Filebeat |
| Precizno vreme | NTP + ISO 8601 UTC | NTP + Logstash date filter |
| Urednost logova | Log nivoi, rotacija, ILM | Docker log-driver / logrotate |


## Reference

- OWASP Logging Cheat Sheet — cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Top 10:2025 A09 — Security Logging and Alerting Failures
- OWASP Log Injection — owasp.org/www-community/attacks/Log_Injection
- Elastic Stack Security — elastic.co/elastic-stack/security
- Logstash Grok Filter — elastic.co/guide/en/logstash/current/plugins-filters-grok.html
- Docker Logging Drivers — docs.docker.com/engine/logging/configure/
- Logrotten exploit — github.com/whotwagner/logrotten
- CVE-2011-1098, CVE-2011-1154, CVE-2011-1155 — Red Hat RHSA-2011:0407
