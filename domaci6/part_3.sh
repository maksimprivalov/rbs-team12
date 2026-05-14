#!/bin/bash
# users_audit.sh - pregled korisnika i SSH konfiguracije
# Pokretanje: sudo ./users_audit.sh

[ "$(id -u)" -ne 0 ] && echo "Nije pokrenuto kao root"

echo "=== Linux Users & SSH Audit | $(date) ==="

# ============================================================
# 1. /etc/passwd
# Otkriva: korisnici sa UID 0 (backdoor), sistemski nalozi
# sa interaktivnim shell-om koji ne bi trebalo da ga imaju
# Komande: awk
# ============================================================
echo ""
echo "--- /etc/passwd ---"

echo "Korisnici sa UID 0:"
awk -F: '$3==0 { print $1 }' /etc/passwd | while read -r u; do
    [ "$u" = "root" ] && echo "  [OK]  root" || echo "  [BAD] $u ima UID 0 - potencijalna backdoor!"
done

echo "Korisnici sa interaktivnim shell-om:"
awk -F: '$7 ~ /\/(bash|sh|zsh|ksh)$/ { printf "  %-15s UID=%-6s %s\n", $1, $3, $7 }' /etc/passwd

echo "Sistemski nalozi (UID<1000) sa shell-om:"
FOUND=false
awk -F: '$3<1000 && $3!=0 && $7 ~ /\/(bash|sh|zsh)$/ { print $1 " UID=" $3 }' /etc/passwd | while read -r line; do
    echo "  [BAD] $line"
    FOUND=true
done
$FOUND || echo "  [OK]  Nema sistemskih naloga sa shell-om."

# ============================================================
# 2. /etc/shadow - algoritam hesovanja
# Otkriva: slabi algoritmi (DES, MD5) laki za brute-force;
# preporuceni su SHA-512 ($6$) ili bcrypt ($2b$)
# Komande: awk
# ============================================================
echo ""
echo "--- /etc/shadow ---"

if [ -r /etc/shadow ]; then
    while IFS=: read -r user hash _; do
        [[ "$hash" =~ ^[\*!] || -z "$hash" ]] && continue
        case "$hash" in
            \$6\$*)         echo "  [OK]  $user - SHA-512" ;;
            \$5\$*|\$2b\$*) echo "  [OK]  $user - SHA-256 / bcrypt" ;;
            \$1\$*)         echo "  [BAD] $user - MD5, lako za brute-force!" ;;
            *)              echo "  [BAD] $user - DES ili nepoznato, kriticno slabo!" ;;
        esac
    done < /etc/shadow

    NO_PASS=$(awk -F: '$2=="" {print $1}' /etc/shadow)
    [ -n "$NO_PASS" ] && echo "  [BAD] Korisnici bez lozinke: $NO_PASS" || echo "  [OK]  Svi korisnici imaju lozinku."
else
    echo "  [WARN] /etc/shadow nije citljiv - potreban root."
fi

# ============================================================
# 3. sudo konfiguracija
# Otkriva: NOPASSWD (sudo bez lozinke), opasne komande
# koje omogucavaju eskalaciju privilegija
# Komande: grep
# ============================================================
echo ""
echo "--- sudo konfiguracija ---"

if [ -r /etc/sudoers ]; then
    echo "Aktivne linije u /etc/sudoers:"
    grep -v "^#\|^$" /etc/sudoers | while read -r line; do echo "  $line"; done

    grep -v "^#" /etc/sudoers | grep -q "NOPASSWD" \
        && echo "  [BAD] NOPASSWD nadjen - sudo bez lozinke!" \
        || echo "  [OK]  Nema NOPASSWD konfiguracije."

    for cmd in vim python python3 perl find bash sh chmod chown; do
        grep -v "^#" /etc/sudoers | grep -q "$cmd" \
            && echo "  [WARN] Opasna komanda '$cmd' u sudoers - moguca eskalacija privilegija."
    done
else
    echo "  [WARN] /etc/sudoers nije citljiv - potreban root."
fi

# ============================================================
# 4. SSH konfiguracija (/etc/ssh/sshd_config)
# Otkriva: dozvoljena root prijava, slaba autentifikacija,
# TCP forwarding koji omogucava zaobilazenje firewall-a
# Komande: grep
# ============================================================
echo ""
echo "--- SSH konfiguracija ---"

SSHD="/etc/ssh/sshd_config"
if [ ! -f "$SSHD" ]; then
    echo "  [WARN] sshd_config nije pronadjen."
else
    get_opt() { grep -i "^$1" "$SSHD" 2>/dev/null | awk '{print $2}' | head -1; }

    VAL=$(get_opt PermitRootLogin); VAL=${VAL:-"yes (default)"}
    [ "$VAL" = "no" ] && echo "  [OK]  PermitRootLogin: no" \
        || echo "  [BAD] PermitRootLogin: $VAL - postaviti na 'no'!"

    VAL=$(get_opt PasswordAuthentication); VAL=${VAL:-"yes (default)"}
    [ "$VAL" = "no" ] && echo "  [OK]  PasswordAuthentication: no" \
        || echo "  [WARN] PasswordAuthentication: $VAL - ranjivo na bruteforce."

    VAL=$(get_opt PermitEmptyPasswords)
    [ "$VAL" = "yes" ] && echo "  [BAD] PermitEmptyPasswords: yes - prijava bez lozinke!" \
        || echo "  [OK]  PermitEmptyPasswords: ${VAL:-no (default)}"

    VAL=$(get_opt AllowTcpForwarding); VAL=${VAL:-"yes (default)"}
    [ "$VAL" = "no" ] && echo "  [OK]  AllowTcpForwarding: no" \
        || echo "  [WARN] AllowTcpForwarding: $VAL - korisnici mogu tunelirati saobracaj."

    VAL=$(get_opt Port)
    [ -z "$VAL" ] || [ "$VAL" = "22" ] \
        && echo "  [WARN] SSH port je 22 (default) - razmotrite promenu." \
        || echo "  [OK]  SSH port: $VAL"

    echo ""
    echo "Kompletan sshd_config (bez komentara):"
    grep -v "^#\|^$" "$SSHD" | while read -r line; do echo "  $line"; done
fi

echo ""
echo "=== Audit zavrsen: $(date) ==="