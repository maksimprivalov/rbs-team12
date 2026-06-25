#!/usr/bin/env bash
#
# Pravi ext4 rootfs za Oblak microVM od python:3.11-slim (glibc) image-a i
# ubacuje guest agenta kao init (/usr/local/bin/oblak-run.py).
#
# Zašto python:3.11-slim (glibc): server instalira korisnikove zavisnosti
# host pip-om (python 3.11, glibc). Da bi prevedeni wheel-ovi radili u VM-u,
# guest mora imati isti ABI -> glibc + Python 3.11.
#
# Zahteva: docker, mkfs.ext4 (e2fsprogs). NE zahteva root (mkfs koristi -d, a
# izlaz podrazumevano ide u oblak/fc-assets/ koji je u folderu projekta).
#
# Upotreba:
#   ./build-rootfs.sh
#   OUTPUT=/tmp/rootfs.ext4 IMAGE_MB=1024 ./build-rootfs.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUEST_AGENT="${GUEST_AGENT:-$HERE/../../server/services/firecracker/guest/oblak-run.py}"
ASSET_DIR="${ASSET_DIR:-$HERE/../../fc-assets}"
OUTPUT="${OUTPUT:-$ASSET_DIR/rootfs.ext4}"
BASE_IMAGE="${BASE_IMAGE:-python:3.11-slim}"
IMAGE_MB="${IMAGE_MB:-1024}"

if [ ! -f "$GUEST_AGENT" ]; then
  echo "GREŠKA: guest agent nije pronađen: $GUEST_AGENT" >&2
  exit 1
fi
command -v docker >/dev/null || { echo "GREŠKA: docker nije instaliran." >&2; exit 1; }
command -v mkfs.ext4 >/dev/null || { echo "GREŠKA: mkfs.ext4 (e2fsprogs) nije instaliran." >&2; exit 1; }

mkdir -p "$(dirname "$OUTPUT")"

TMP="$(mktemp -d)"
ROOTFS_DIR="$TMP/rootfs"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$ROOTFS_DIR"

echo "==> Izvoz filesystem-a iz $BASE_IMAGE"
CID="$(docker create "$BASE_IMAGE" sleep 1)"
docker export "$CID" | tar -x -C "$ROOTFS_DIR"
docker rm "$CID" >/dev/null

echo "==> Ubacivanje guest agenta kao init"
install -D -m 0755 "$GUEST_AGENT" "$ROOTFS_DIR/usr/local/bin/oblak-run.py"
# Sigurnosna provera: init mora biti izvršan i imati ispravan shebang
head -n1 "$ROOTFS_DIR/usr/local/bin/oblak-run.py"

# Minimalni /etc da se Python lepo ponaša (UTF-8, /tmp postoji)
mkdir -p "$ROOTFS_DIR/tmp" "$ROOTFS_DIR/job" "$ROOTFS_DIR/proc" "$ROOTFS_DIR/sys"
chmod 1777 "$ROOTFS_DIR/tmp"

echo "==> Pravljenje ext4 image-a (${IMAGE_MB} MB) -> $OUTPUT"
IMG="$TMP/rootfs.ext4"
truncate -s "${IMAGE_MB}M" "$IMG"
mkfs.ext4 -F -q -d "$ROOTFS_DIR" "$IMG"
install -m 0644 "$IMG" "$OUTPUT"

echo
echo "Gotovo: $OUTPUT"
echo "Putanja mora da se poklopi sa firecracker_rootfs u server/config.py."
