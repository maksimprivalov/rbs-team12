#!/usr/bin/env bash
#
# Instalira Firecracker binarku + gostujući kernel i priprema /dev/kvm dozvole.
# Testirano za Arch Linux i Debian/Ubuntu (uklj. WSL2 sa nested virtualizacijom).
#
# Upotreba:
#   ./setup.sh                 # instalira sve u podrazumevane putanje
#   FC_VERSION=v1.10.1 ./setup.sh
#
# Dev podrazumevano: kernel ide u oblak/fc-assets/ (isto što gleda config.py).
# firecracker binarka ide na PATH (/usr/local/bin) jer config.py traži po PATH-u.
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FC_VERSION="${FC_VERSION:-v1.10.1}"
INSTALL_DIR="${INSTALL_DIR:-/usr/local/bin}"
ASSET_DIR="${ASSET_DIR:-$HERE/../../fc-assets}"
CI_VER="${CI_VER:-v1.10}"          # Firecracker CI bucket verzija
KERNEL_VERSION="${KERNEL_VERSION:-5.10}"   # serija kernela (uzima se najnoviji patch)

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|aarch64) ;;
  *) echo "Nepodržana arhitektura: $ARCH" >&2; exit 1 ;;
esac

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO="sudo"
fi

echo "==> Provera KVM-a"
if [ ! -e /dev/kvm ]; then
  echo "GREŠKA: /dev/kvm ne postoji." >&2
  echo "  - Na bare-metal Linux-u: omogući virtualizaciju (VT-x/AMD-V) u BIOS-u." >&2
  echo "  - U WSL2: potrebna je nested virtualizacija + 'kvm' modul (Win11 + .wslconfig)." >&2
  exit 1
fi

echo "==> Instalacija firecracker ${FC_VERSION} (${ARCH})"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
TARBALL="firecracker-${FC_VERSION}-${ARCH}.tgz"
URL="https://github.com/firecracker-microvm/firecracker/releases/download/${FC_VERSION}/${TARBALL}"
curl -fsSL "$URL" -o "$TMP/$TARBALL"
tar -xzf "$TMP/$TARBALL" -C "$TMP"
$SUDO install -m 0755 "$TMP/release-${FC_VERSION}-${ARCH}/firecracker-${FC_VERSION}-${ARCH}" "$INSTALL_DIR/firecracker"
echo "    -> $INSTALL_DIR/firecracker"
"$INSTALL_DIR/firecracker" --version || true

echo "==> Pronalaženje najnovijeg kernela (serija ${KERNEL_VERSION})"
mkdir -p "$ASSET_DIR"
ASSET_DIR="$(cd "$ASSET_DIR" && pwd)"   # normalizuj u apsolutnu putanju
# Bucket sadrži npr. vmlinux-5.10.223 (pun patch, bez .bin). Izlistaj i uzmi
# najnoviji patch te serije, preskačući .config i -no-acpi varijante.
PREFIX="firecracker-ci/${CI_VER}/${ARCH}/vmlinux-${KERNEL_VERSION}."
KEY="$(curl -fsSL "https://s3.amazonaws.com/spec.ccfc.min/?list-type=2&prefix=${PREFIX}" \
  | tr '<' '\n' \
  | sed -n "s#^Key>\(firecracker-ci/${CI_VER}/${ARCH}/vmlinux-[0-9.]*\)\$#\1#p" \
  | sort -V | tail -1)"
if [ -z "$KEY" ]; then
  echo "GREŠKA: nije pronađen kernel za seriju ${KERNEL_VERSION} (${ARCH}) u ${CI_VER}." >&2
  exit 1
fi
echo "==> Preuzimanje kernela: $KEY"
curl -fsSL "https://s3.amazonaws.com/spec.ccfc.min/${KEY}" -o "$ASSET_DIR/vmlinux"
echo "    -> $ASSET_DIR/vmlinux"

echo "==> Podešavanje /dev/kvm dozvola"
USER_NAME="$(id -un)"
# Napravi 'kvm' grupu ako ne postoji (čest slučaj na WSL/minimalnim sistemima)
if ! getent group kvm >/dev/null 2>&1; then
  echo "    Grupa 'kvm' ne postoji - pravim je."
  $SUDO groupadd -r kvm || true
fi
$SUDO usermod -aG kvm "$USER_NAME" || true
# Na WSL nema udev pravila koja postavljaju vlasništvo nad /dev/kvm - postavi ručno
$SUDO chgrp kvm /dev/kvm 2>/dev/null || true
$SUDO chmod 660 /dev/kvm 2>/dev/null || true

if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
  echo "    /dev/kvm je dostupan korisniku '$USER_NAME'. ✓"
else
  echo "    Korisnik '$USER_NAME' dodat u grupu 'kvm', ali TRENUTNA sesija to ne vidi."
  echo "    Aktiviraj odmah:   newgrp kvm          (ili se izloguj pa uloguj)"
  echo "    Brza alternativa:  $SUDO setfacl -m u:$USER_NAME:rw /dev/kvm"
fi
echo "    (Na WSL se dozvole nad /dev/kvm resetuju posle 'wsl --shutdown' - po potrebi ponovi.)"

echo
echo "Gotovo. Sledeći korak: ./build-rootfs.sh (pravi rootfs sa Python-om + guest agentom)."
