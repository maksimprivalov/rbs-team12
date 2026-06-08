# Zadatak 5 - Educational Purposes Only

**Flag format:** `UNS{}`  
**Flag:** `UNS{V3RY_OLD_4RCH1V3}`

---

## Šta je dato

Dobio sam dva fajla:
- `old.rar` - zaštićen arhiv koji ne mogu da otvorim bez šifre
- `forgotten_password.txt` - fajl koji navodi kako da rekonstruišem šifru

Sadržaj `forgotten_password.txt`:

```
In order to forge the password, answer following questions and merge the answers together. Good luck!
https://www.md5hashgenerator.com/

1. Date when Faculty of Technical Sciences officialy opened. (Date Format : DD/MM/YYYY)
   MD5 : 02c3890bb0b03a24b99c3e4a39f18c44

2. First name of the person who held the position of dean at the faculty from 01.10.1975. until September 30, 1977. ?
   MD5 : 06904f68128802c069e782b772e85eda

3. The date when the FTN website was launched. (Date Format : DD/MM/YYYY)
   MD5 : f4d7caf81e33bc156cc3e98cf8095d2e

4. The year when studies in the field of "Poštanski saobraćaj i telekomunikacije" were introduced.
   MD5 : 5ec829debe54b19a5f78d9a65b900a39
```

Dakle, šifra = spoj tačnih odgovora na sva četiri pitanja. MD5 hashevi su tu da mogu da proverim svaki odgovor posebno pre nego što probam da otvorim arhiv.

---

## Pitanje 1 - Datum zvaničnog otvaranja FTN-a

Počeo sam od Wikipedije. Na srpskoj i srpskohrvatskoj verziji stranice za FTN Novi Sad piše:

> "Fakultet tehničkih nauka je osnovan 18. maja 1960. godine odlukom Narodne skupštine Narodne Republike Srbije."

Format koji pitanje traži je `DD/MM/YYYY`, dakle: **18/05/1960**

Proverio sam na sajtu za MD5: hash od `18/05/1960` daje `02c3890bb0b03a24b99c3e4a39f18c44` - tačno se poklapa. ✓

---

## Pitanje 2 - Ime dekana od 01.10.1975.

Ovo je zahtevalo malo više kopanja. Pokušao sam da nađem stranicu FTN-a sa istorijatom dekana (`ftn.uns.ac.rs/istorijat-funkcije-dekan`) ali ona nije bila dostupna u trenutku pretrage.

Onda sam naišao na zanimljivu stranicu na ftn.uns.ac.rs - nekrolog pod naslovom koji u URL-u kaže nešto u stilu "preminuo je nas dekan 1975-1979 prof dr Dragutin Zelenovic". To mi je odmah dalo odgovor.

**Dragutin** Zelenović je bio dekan FTN-a od 1975. do 1979. godine, što pokriva traženi period (01.10.1975 - 30.09.1977).

MD5 od `Dragutin` = `06904f68128802c069e782b772e85eda` ✓

Dragutin Zelenović je inače bio i rektor Univerziteta u Novom Sadu i prvi predsednik Vlade Republike Srbije - zanimljiva ličnost.

---

## Pitanje 3 - Datum pokretanja FTN sajta

Ovo pitanje mi je oduzelo najviše vremena. Nisam mogao da nađem direktan izvor koji kaže tačan datum pokretanja sajta. Probao sam:

- Zvaničnu FTN stranicu (nema podatka)
- Googlovao kombinacije ključnih reči - ništa konkretno
- Pokušao Wayback Machine (`web.archive.org`) da vidim najstariji snimak `ftn.uns.ac.rs`

Kada nisam mogao da nađem odgovor direktno, primenio sam drugačiji pristup. Pošto znam format (`DD/MM/YYYY`) i znam MD5 koji tražim, mogu da **brute-force-ujem** sve moguće datume u nekom razumnom opsegu (recimo 1994-2010) i vidim koji daje traženi hash.

Napisao sam kratak Python skript:

```python
import hashlib
import calendar

expected = 'f4d7caf81e33bc156cc3e98cf8095d2e'

for year in range(1994, 2010):
    for month in range(1, 13):
        max_day = calendar.monthrange(year, month)[1]
        for day in range(1, max_day + 1):
            s = f'{day:02d}/{month:02d}/{year}'
            if hashlib.md5(s.encode()).hexdigest() == expected:
                print(f'Match: {s}')
```

Skript je brzo izbacio rezultat: **18/05/2005**

Zanimljivo je što je isti dan i mesec kao datum osnivanja fakulteta (18. maja), samo 45 godina kasnije.

MD5 od `18/05/2005` = `f4d7caf81e33bc156cc3e98cf8095d2e` ✓

---

## Pitanje 4 - Godina uvođenja "Poštanskog saobraćaja i telekomunikacija"

Na Wikipediji i na FTN stranici pronašao sam sledeće:

> "Od školske 1999/2000. dolazi promena, kada počinju studije grafičkog inženjerstva i dizajna, poštanskog saobraćaja i telekomunikacija..."

Odgovor je **1999** (godina u kojoj je počela školska 1999/2000).

MD5 od `1999` = `5ec829debe54b19a5f78d9a65b900a39` ✓

---

## Spajanje odgovora i otvaranje arhiva

Fajl kaže "merge the answers together", pa ih jednostavno nadovežem:

```
18/05/1960 + Dragutin + 18/05/2005 + 1999
= "18/05/1960Dragutin18/05/20051999"
```

Otvaram arhiv:

```bash
unrar e old.rar -p"18/05/1960Dragutin18/05/20051999"
```

Arhiv se otvara i izvlači `flag.png`. Na slici piše:

**`UNS{V3RY_OLD_4RCH1V3}`**

---

## Zaključak i pouka

Zadatak pokazuje kako se javno dostupne informacije mogu iskoristiti za rekonstrukciju tajnog podatka (šifre). Sve četiri informacije koje su bile potrebne nalaze se na internetu - Wikipedia, zvanične stranice fakulteta, arhive sajtova.

Lozinke koje su bazirane na javno poznatim faktima (datumi osnivanja institucija, imenovanje rukovodilaca, datumi pokretanja sajtova) nisu bezbedne jer ih napadač može pronaći istim istraživanjem koje smo ovde sproveli. Ovo važi i u realnom svetu - mnogi sistemi koriste slične "sigurnosne" podatke (npr. pitanja poput "kada ste osnovani") koji su trivijalno dostupni.

Zanimljiv detalj: brute-force MD5-a po datumima bio je potpuno validan pristup za pitanje 3, pošto je prostor pretrage mali (svega par hiljada datuma u razumnom opsegu). MD5 nije kriptografski siguran za ovakvu primenu.
