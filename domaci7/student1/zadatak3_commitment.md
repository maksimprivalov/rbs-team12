# Zadatak 3 – Commitment

**Flag format:** `csictf{}`  
**Flag:** `csictf{sc4r3d_0f_c0mm1tm3nt}`

---

## Početak – šta mi je dato

Jedini podatak koji imam je rečenica: *"hoshimaseok is up to no good. Track him down."*

Dakle, imam username. Prvo što mi je palo na pamet je da jednostavno ukucam `hoshimaseok` u Google i vidim šta izlazi. Izašao mi je GitHub profil odmah u prvim rezultatima, ali sam hteo da budem sistematičan i da vidim postoji li negde još.

---

## Korak 1 – Pretraga po platformama (Sherlock)

Koristio sam alat koji se zove **Sherlock** – traži zadati username na stotinama sajtova odjednom. Instalacija je prosta:

```bash
git clone https://github.com/sherlock-project/sherlock
cd sherlock
pip install -r requirements.txt
```

Pokretanje:

```bash
python3 sherlock hoshimaseok
```

Sherlock je izbacio nekoliko rezultata, ali jedini koji je bio aktivan i zanimljiv bio je GitHub nalog. Ostali sajtovi su vraćali 404 ili su bili sasvim nepovezani profili.

---

## Korak 2 – GitHub nalog

Odlazim na: `https://github.com/hoshimaseok`

Na nalogu postoji jedan repozitorijum koji odmah privlači pažnju: **SomethingFishy**. Naziv je dosta sugestivan. Otvaram ga.

Na `main` grani nema ničeg posebnog – par fajlova, nasumičan kod koji ne vodi nigde. Malo sam se vrteo okolo i nisam nalazio ništa. Onda sam primetio da postoji i **grana `dev`**.

Prebacim se na `dev`:

```
https://github.com/hoshimaseok/SomethingFishy/tree/dev
```

Ovde je mnogo više fajlova i foldera. Gledao sam kroz kod ali ništa očigledno. Onda mi je svanulo – ako je zadatak nazvan *Commitment*, možda je pointa upravo u **commitovima**, tj. git istoriji.

---

## Korak 3 – Kopanje po git istoriji

Kliknuo sam na **Commits** u GitHub interfejsu da vidim sve commitove na `dev` grani.

Nešto što odmah upada u oko: `.gitignore` fajl je **menjan dva puta**. To je sumnjivo. Zašto bi neko dva puta menjao `.gitignore`? Obično se to radi kada shvatiš da si greškom commitovao nešto što ne treba.

Otvorio sam stariji commit – onaj pre drugog `.gitignore` update-a – i video da je u tom trenutku u repozitorijumu postojao i `.env` fajl. Korisnik ga je naknadno dodao u `.gitignore` i izbrisao iz repozitorijuma, ali u git istoriji ostaje zauvek.

U `.env` fajlu se nalazio flag:

```
FLAG=csictf{sc4r3d_0f_c0mm1tm3nt}
```

---

## Zaključak i pouka

Ovo je klasičan OPSEC propust koji se dešava u praksi češće nego što bi trebalo. Programeri znaju da ne treba da commit-uju `.env` fajlove sa tajnim podacima, ali se desi da zaborave, pushu, pa naknadno obrišu. Problem je što git istorija **ne briše ništa** – podaci su zauvek dostupni svakome ko ima pristup repozitorijumu (ili čak i ako je repozitorijum javan).

Pravo rešenje kada se ovo desi nije samo brisanje fajla – treba odmah **revokovati kompromitovane kredencijale** i po potrebi uraditi rewrite git istorije alatima kao što su `git filter-branch` ili **BFG Repo Cleaner**.

Zanimljivo mi je bilo i što je username u imenu flaga – `sc4r3d_0f_c0mm1tm3nt` (scared of commitment) – što je direktna referenca na zadatak i na to što je korisnik pokušao da "pobegne" od svog commita brisanjem.
