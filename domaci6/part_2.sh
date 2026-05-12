#!/bin/bash
# network_filesystem_audit.sh - pregled mreze i fajlsistema
# Pokretanje: sudo ./network_filesystem_audit.sh

[ "$(id -u)" -ne 0 ] && echo "Nije pokrenuto kao root"

echo "=== Linux Network & Filesystem Audit | $(date) ==="

# ============================================================
# 1. IPv4 FIREWALL PRAVILA
# Otkriva: otvorene portove svima (npr. SSH bez whiteliste),
# nedostajuca pravila za izlazni saobracaj, pravila koja se
# gube posle reboota
# Komande: iptables
# ============================================================
echo ""
echo "--- IPv4 firewall (iptables) ---"

if command -v iptables &>/dev/null; then
    iptables -L -v -n 2>/dev/null

    INPUT_POLICY=$(iptables -L INPUT 2>/dev/null | head -1 | grep -oE 'ACCEPT|DROP|REJECT')
    [ "$INPUT_POLICY" = "ACCEPT" ] \
        && echo "  [BAD] INPUT politika je ACCEPT - sav saobracaj dozvoljen!" \
        || echo "  [OK]  INPUT politika: $INPUT_POLICY"

    OUTPUT_POLICY=$(iptables -L OUTPUT 2>/dev/null | head -1 | grep -oE 'ACCEPT|DROP|REJECT')
    [ "$OUTPUT_POLICY" = "ACCEPT" ] \
        && echo "  [WARN] OUTPUT politika je ACCEPT - izlazni saobracaj nije ogranicen." \
        || echo "  [OK]  OUTPUT politika: $OUTPUT_POLICY"

    if iptables -L INPUT -v -n 2>/dev/null | grep -qE 'dpt:22.*(0\.0\.0\.0|anywhere)'; then
        echo "  [WARN] SSH (port 22) otvoren svima - razmotrite IP whitelist."
    fi

    if [ -f /etc/iptables.up.rules ] || [ -f /etc/iptables/rules.v4 ] || [ -f /etc/network/if-pre-up.d/iptables ]; then
        echo "  [OK]  Firewall pravila ce preziveti reboot."
    else
        echo "  [BAD] Firewall pravila se gube posle reboota - nisu sacuvana!"
    fi
else
    echo "  [WARN] iptables nije dostupan."
fi

# ============================================================
# 2. IPv6 FIREWALL PRAVILA
# Otkriva: nezasticen IPv6 saobracaj koji napadacu omogucava
# da zaobilazi sva IPv4 firewall pravila
# Komande: ip6tables
# ============================================================
echo ""
echo "--- IPv6 firewall (ip6tables) ---"

if command -v ip6tables &>/dev/null; then
    ip6tables -L -v -n 2>/dev/null

    for chain in INPUT OUTPUT FORWARD; do
        POLICY=$(ip6tables -L "$chain" 2>/dev/null | head -1 | grep -oE 'ACCEPT|DROP|REJECT')
        [ "$POLICY" = "ACCEPT" ] \
            && echo "  [BAD] IPv6 $chain politika je ACCEPT - nema IPv6 zastite!" \
            || echo "  [OK]  IPv6 $chain politika: $POLICY"
    done
else
    echo "  [WARN] ip6tables nije dostupan."
fi

# ============================================================
# 3. MREZNI INTERFEJSI I RUTE
# Otkriva: neocekivane aktivne interfejse ili rute koji mogu
# ukazivati na kompromitovanje; servise koji slusaju na svim
# interfejsima umesto samo na localhost-u
# Komande: ip, ss
# ============================================================
echo ""
echo "--- Mrezni interfejsi i rute ---"

echo "Interfejsi:"
ip addr 2>/dev/null || ifconfig -a 2>/dev/null

echo ""
echo "Rute:"
ip route 2>/dev/null || route -n 2>/dev/null

echo ""
echo "TCP servisi koji slusaju:"
ss -tln 2>/dev/null || netstat -tln 2>/dev/null

echo ""
echo "UDP servisi koji slusaju:"
ss -uln 2>/dev/null || netstat -uln 2>/dev/null

echo ""
echo "Potencijalno opasni otvoreni portovi:"
FOUND=false
for port in 21 23 25 111 512 513 514 2049; do
    if ss -tln 2>/dev/null | grep -q ":$port "; then
        echo "  [WARN] Port $port je otvoren - proverite da li je servis potreban."
        FOUND=true
    fi
done
$FOUND || echo "  [OK]  Nisu detektovani ocigledni opasni portovi."

# ============================================================
# 4. MONTIRANE PARTICIJE (/etc/fstab)
# Otkriva: odsustvo noexec na /tmp sto dozvoljava pokretanje
# malicioznih binarnih fajlova; noatime onemogucava pracenje
# vremena pristupa fajlovima sto otezava forenziku
# Komande: cat
# ============================================================
echo ""
echo "--- Montirane particije (/etc/fstab) ---"

if [ -f /etc/fstab ]; then
    echo "Sadrzaj /etc/fstab:"
    grep -v "^#\|^$" /etc/fstab | while read -r line; do echo "  $line"; done

    echo ""
    grep -qE '\s/tmp\s' /etc/fstab \
        && (grep -E '\s/tmp\s' /etc/fstab | grep -q 'noexec' \
            && echo "  [OK]  /tmp montiran sa noexec." \
            || echo "  [BAD] /tmp nema noexec - korisnici mogu izvrsavati fajlove iz /tmp!") \
        || echo "  [WARN] /tmp nije posebno montiran - nasledjuje opcije root particije."

    grep -qE '\s/tmp\s' /etc/fstab \
        && (grep -E '\s/tmp\s' /etc/fstab | grep -q 'nosuid' \
            && echo "  [OK]  /tmp montiran sa nosuid." \
            || echo "  [WARN] /tmp nema nosuid - setuid fajlovi u /tmp mogu biti opasni.")

    grep -q 'noatime' /etc/fstab \
        && echo "  [WARN] Detektovana 'noatime' opcija - otezava forenziku." \
        || echo "  [OK]  noatime nije prisutan - vreme pristupa fajlovima se belezi."
else
    echo "  [WARN] /etc/fstab nije pronadjen."
fi

# ============================================================
# 5. PERMISIJE OSETLJIVIH FAJLOVA
# Otkriva: /etc/shadow citljiv neovlascenim korisnicima
# omogucava offline napad recnikom na heshove lozinki;
# SSL kljucevi dostupni svima omogucavaju dekriptovanje saobracaja
# Komande: stat, find
# ============================================================
echo ""
echo "--- Permisije osetljivih fajlova ---"

for f in /etc/shadow /etc/sudoers /etc/ssh/sshd_config /etc/passwd /etc/gshadow; do
    if [ -e "$f" ]; then
        PERM=$(stat -c "%a" "$f" 2>/dev/null)
        WORLD=$(( 0$PERM & 7 ))
        [ "$WORLD" -ge 4 ] \
            && echo "  [BAD] $f je citljiv svima! (permisije: $PERM)" \
            || echo "  [OK]  $f - permisije OK ($PERM)"
    fi
done

echo ""
echo "SSL privatni kljucevi:"
FOUND=false
for dir in /etc/ssl/private /etc/apache2/ssl /etc/nginx/ssl /etc/pki/tls/private; do
    if [ -d "$dir" ]; then
        find "$dir" -type f \( -name "*.key" -o -name "*.pem" \) 2>/dev/null | while read -r kf; do
            PERM=$(stat -c "%a" "$kf" 2>/dev/null)
            WORLD=$(( 0$PERM & 7 ))
            [ "$WORLD" -ge 4 ] \
                && echo "  [BAD] $kf citljiv svima! (permisije: $PERM)" \
                || echo "  [OK]  $kf - permisije OK ($PERM)"
            FOUND=true
        done
    fi
done
$FOUND || echo "  [INFO] Nisu pronadjeni SSL kljucevi na standardnim lokacijama."

echo ""
echo "Backup kopije osetljivih fajlova:"
BAD=$(find /etc / -maxdepth 3 \( -name "*.bak" -o -name "*.backup" -o -name "shadow.backup" \) \
    -type f -perm -004 2>/dev/null | grep -v /proc)
[ -n "$BAD" ] \
    && echo "$BAD" | while read -r line; do echo "  [BAD] $line je citljiv svima!"; done \
    || echo "  [OK]  Nisu pronadjeni javno citljivi backup fajlovi."

# ============================================================
# 6. SUID FAJLOVI
# Otkriva: nepoznate ili nepotrebne setuid binarne fajlove
# koji se izvrsavaju sa privilegijama vlasnika (najcesce root)
# i mogu biti iskorisceni za eskalaciju privilegija
# Komande: find
# ============================================================
echo ""
echo "--- SUID fajlovi (find / -perm -4000) ---"

KNOWN="/bin/su /bin/ping /bin/ping6 /bin/umount /bin/mount
       /usr/bin/passwd /usr/bin/sudo /usr/bin/newgrp
       /usr/bin/chsh /usr/bin/chfn /usr/bin/gpasswd /usr/sbin/uuidd"

find / -perm -4000 -type f 2>/dev/null | grep -v /proc | sort | while read -r f; do
    OWNER=$(stat -c "%U" "$f" 2>/dev/null)
    PERM=$(stat -c "%a" "$f" 2>/dev/null)
    IS_KNOWN=0
    for k in $KNOWN; do [ "$f" = "$k" ] && IS_KNOWN=1 && break; done

    if [ "$IS_KNOWN" -eq 1 ]; then
        echo "  [OK]  $f (vlasnik: $OWNER, permisije: $PERM) - legitiman."
    elif [ "$OWNER" = "root" ]; then
        echo "  [BAD] $f (vlasnik: root, permisije: $PERM) - nepoznat root SUID fajl!"
    else
        echo "  [WARN] $f (vlasnik: $OWNER, permisije: $PERM) - proverite nuznost."
    fi
done

# ============================================================
# 7. WORLD-WRITABLE FAJLOVI
# Otkriva: fajlove koje moze menjati bilo koji korisnik;
# ako cron izvrsava takav fajl kao root, svako moze ubaciti
# maliciozni kod i eskalirati privilegije
# Komande: find
# ============================================================
echo ""
echo "--- World-writable fajlovi (find / -type f -perm -002) ---"

WW=$(find / -type f -perm -002 2>/dev/null | grep -v /proc | grep -v /sys | grep -v /dev)

if [ -z "$WW" ]; then
    echo "  [OK]  Nisu pronadjeni world-writable fajlovi."
else
    echo "$WW" | while read -r f; do
        OWNER=$(stat -c "%U" "$f" 2>/dev/null)
        if echo "$f" | grep -qE '^/etc/|^/bin/|^/sbin/|^/usr/'; then
            echo "  [BAD] $f (vlasnik: $OWNER) - sistemski direktorijum!"
        elif echo "$f" | grep -qE '^/var/www/|^/srv/|^/opt/'; then
            echo "  [WARN] $f (vlasnik: $OWNER) - web/app direktorijum."
        else
            echo "  [INFO] $f (vlasnik: $OWNER)"
        fi
    done
    echo ""
    echo "  Preporuka: chmod o-w <fajl> za svaki nepotreban slucaj."
fi

echo ""
echo "=== Audit zavrsen: $(date) ==="