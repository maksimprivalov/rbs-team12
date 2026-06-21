#!/bin/bash
# Preuzima Firecracker binarni fajl i gradi Python rootfs za Oblak platformu.
# Pokrenuti JEDNOM na Linux hostu sa KVM pristupom, pre 'docker-compose up'.
#
# Preduslovi: curl, docker, e2fsprogs, xz-utils
# Rezultat: /opt/firecracker/vmlinux.bin i /opt/firecracker/python.ext4

set -euo pipefail

FC_VERSION="1.8.0"
FC_DIR="/opt/firecracker"
ROOTFS_SIZE_MB=512
ROOTFS_TMP=$(mktemp -d)

echo "=== Oblak — Firecracker setup ==="

# --- 1. Direktorijum ---
sudo mkdir -p "$FC_DIR"

# --- 2. Firecracker binarni fajl ---
FC_ARCHIVE="firecracker-v${FC_VERSION}-x86_64.tgz"
FC_URL="https://github.com/firecracker-microvm/firecracker/releases/download/v${FC_VERSION}/${FC_ARCHIVE}"

if [ ! -f "$FC_DIR/firecracker" ]; then
    echo "[1/4] Preuzimam Firecracker v${FC_VERSION}..."
    curl -fsSL -o "/tmp/${FC_ARCHIVE}" "$FC_URL"
    tar -xzf "/tmp/${FC_ARCHIVE}" -C /tmp
    sudo mv "/tmp/release-v${FC_VERSION}-x86_64/firecracker-v${FC_VERSION}-x86_64" "$FC_DIR/firecracker"
    sudo chmod +x "$FC_DIR/firecracker"
    rm -rf "/tmp/${FC_ARCHIVE}" "/tmp/release-v${FC_VERSION}-x86_64"
    echo "    Firecracker -> $FC_DIR/firecracker"
else
    echo "[1/4] Firecracker već postoji — preskačem."
fi

# Dodajemo symlink na PATH
sudo ln -sf "$FC_DIR/firecracker" /usr/local/bin/firecracker

# --- 3. Kernel image ---
# Koristimo zvanični Firecracker test kernel (minimalan, brzo pokretanje ~125ms)
KERNEL_URL="https://s3.amazonaws.com/spec.ccfc.min/firecracker-ci/v1.8/x86_64/vmlinux-5.10.225"

if [ ! -f "$FC_DIR/vmlinux.bin" ]; then
    echo "[2/4] Preuzimam kernel image..."
    sudo curl -fsSL -o "$FC_DIR/vmlinux.bin" "$KERNEL_URL"
    echo "    Kernel -> $FC_DIR/vmlinux.bin"
else
    echo "[2/4] Kernel već postoji — preskačem."
fi

# --- 4. Python rootfs ---
# Gradimo minimal Alpine Linux + Python3 rootfs kao ext4 sliku.
# Rootfs sadrži:
#   - busybox (sh, mount, reboot)
#   - python3
#   - /init skripta koja montira code drive i pokreće main.py

if [ ! -f "$FC_DIR/python.ext4" ]; then
    echo "[3/4] Gradim Python rootfs (Alpine Linux + Python3)..."

    # Koristimo Docker Alpine image kao bazu
    CONTAINER_ID=$(docker create python:3.11-alpine)
    ROOTFS_TAR="$ROOTFS_TMP/rootfs.tar"
    docker export "$CONTAINER_ID" -o "$ROOTFS_TAR"
    docker rm "$CONTAINER_ID"

    # Raspakujemo u temp direktorijum
    ROOTFS_DIR="$ROOTFS_TMP/rootfs"
    mkdir -p "$ROOTFS_DIR"
    tar -xf "$ROOTFS_TAR" -C "$ROOTFS_DIR"

    # Upisujemo /init skriptu — pokrenuti na startu VM-a
    cat > "$ROOTFS_DIR/init" << 'INIT_EOF'
#!/bin/sh
# Oblak MicroVM init skripta

# Montiramo osnovne fajlsisteme
mount -t proc proc /proc 2>/dev/null
mount -t sysfs sysfs /sys 2>/dev/null
mount -t tmpfs tmpfs /tmp 2>/dev/null

# Montiramo code drive (/dev/vdb) koji sadrži korisnikov main.py
mkdir -p /code
if mount /dev/vdb /code -o ro 2>/dev/null; then
    # Postavljamo PYTHONPATH na venv ako postoji
    if [ -d /code/venv ]; then
        export PYTHONPATH=/code/venv
    fi

    # Izvršavamo korisnikov kod — output ide na serial (ttyS0)
    python3 /code/main.py 2>&1
    EXIT_CODE=$?
    echo "EXIT_CODE:${EXIT_CODE}"
else
    echo "ERROR: Ne mogu da montiram code drive /dev/vdb"
    echo "EXIT_CODE:1"
fi

# Cleanly shutdown VM
echo o > /proc/sysrq-trigger 2>/dev/null || reboot -f
INIT_EOF
    chmod +x "$ROOTFS_DIR/init"

    # Kreiramo ext4 sliku
    ROOTFS_IMG="$FC_DIR/python.ext4"
    dd if=/dev/zero of="$ROOTFS_IMG" bs=1M count=$ROOTFS_SIZE_MB status=none
    mkfs.ext4 -F -L rootfs "$ROOTFS_IMG" > /dev/null 2>&1

    # Kopiramo rootfs sadržaj u ext4 sliku koristeći loop device
    LOOP=$(sudo losetup -f --show "$ROOTFS_IMG")
    sudo mkdir -p /mnt/fc_rootfs
    sudo mount "$LOOP" /mnt/fc_rootfs
    sudo cp -a "$ROOTFS_DIR/." /mnt/fc_rootfs/
    sudo umount /mnt/fc_rootfs
    sudo losetup -d "$LOOP"

    sudo chown root:root "$ROOTFS_IMG"
    echo "    Rootfs -> $FC_DIR/python.ext4 (${ROOTFS_SIZE_MB}MB)"
else
    echo "[3/4] Rootfs već postoji — preskačem."
fi

# --- 5. KVM pristup ---
echo "[4/4] Proveravamo KVM pristup..."
if [ -e /dev/kvm ]; then
    # Dodajemo trenutnog korisnika u kvm grupu
    if ! groups | grep -q kvm; then
        sudo usermod -aG kvm "$USER"
        echo "    Dodat $USER u kvm grupu — potreban je re-login!"
    fi
    sudo chmod 660 /dev/kvm
    echo "    /dev/kvm dostupan."
else
    echo "    UPOZORENJE: /dev/kvm ne postoji — KVM nije omogućen."
    echo "    Proveri da li je hardware virtualizacija uključena u BIOS-u."
fi

# --- Cleanup ---
rm -rf "$ROOTFS_TMP"

echo ""
echo "=== Setup završen! ==="
echo "Sadržaj $FC_DIR:"
ls -lh "$FC_DIR"
echo ""
echo "Pokrenuti Oblak server:"
echo "  docker-compose up --build"
