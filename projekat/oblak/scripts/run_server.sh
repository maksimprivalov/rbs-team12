#!/usr/bin/env bash
#
# Pokreće Oblak server NATIVNO u WSL/Linux-u (ne u Docker-u), da bi imao pristup
# /dev/kvm za Firecracker. Pravi venv, instalira zavisnosti + CLI, seed-uje
# korisnike i startuje uvicorn.
#
# Upotreba:  ./scripts/run_server.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"   # oblak/
cd "$ROOT"

# Apsolutne putanje za bazu i storage (nezavisno od cwd-a; .env.example cilja Docker)
export DATABASE_URL="sqlite:///$ROOT/oblak.db"
export STORAGE_PATH="$ROOT/storage"
mkdir -p "$STORAGE_PATH"

if [ ! -d .venv ]; then
  echo "==> Pravim venv (.venv)"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate

echo "==> Instaliram zavisnosti servera + CLI"
# pip>=21.3 i setuptools>=64 su neophodni za editable install (PEP 660)
pip install  --upgrade pip setuptools wheel
pip install  -r server/requirements.txt
pip install  -e cli

[ -f .env ] || cp .env.example .env

echo "==> Seed test korisnika (admin/alice/bob)"
( cd server && python ../scripts/seed.py )

echo "==> Server: http://localhost:8000  (Swagger: /docs).  Ctrl+C za prekid."
cd server
exec uvicorn main:app --host 0.0.0.0 --port 8000 --reload