#!/usr/bin/env bash
# YASTL - Proxmox LXC Container Setup Script
# Run this on the Proxmox host to create and configure an LXC container for YASTL
#
# Prerequisites:
#   - Proxmox VE host with LXC support
#   - A Debian/Ubuntu LXC template downloaded
#   - NFS share accessible from the Proxmox host
#
# Usage:
#   chmod +x proxmox-setup.sh
#   ./proxmox-setup.sh

set -euo pipefail

# ============================================================
# Configuration - Edit these values for your environment
# ============================================================
CT_ID="${CT_ID:-200}"
CT_HOSTNAME="${CT_HOSTNAME:-yastl}"
CT_MEMORY="${CT_MEMORY:-2048}"        # MB
CT_SWAP="${CT_SWAP:-512}"             # MB
CT_DISK="${CT_DISK:-8}"               # GB
CT_CORES="${CT_CORES:-2}"
CT_TEMPLATE="${CT_TEMPLATE:-local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst}"
CT_STORAGE="${CT_STORAGE:-local-lvm}"
CT_BRIDGE="${CT_BRIDGE:-vmbr0}"

# NFS mount configuration
NFS_SERVER="${NFS_SERVER:-}"           # e.g., 192.168.1.100
NFS_SHARE="${NFS_SHARE:-}"            # e.g., /volume1/3dPrinting
NFS_MOUNT_POINT="/nfs/DATA/3dPrinting"

# YASTL settings
YASTL_PORT="${YASTL_PORT:-8000}"
YASTL_DATA_DIR="/opt/yastl/data"

# ============================================================

echo "========================================"
echo "  YASTL - Proxmox LXC Setup"
echo "========================================"

# Validate NFS config
if [[ -z "$NFS_SERVER" || -z "$NFS_SHARE" ]]; then
    echo ""
    echo "NFS configuration required. Set environment variables:"
    echo "  export NFS_SERVER=192.168.1.100"
    echo "  export NFS_SHARE=/volume1/3dPrinting"
    echo ""
    echo "Or edit the Configuration section in this script."
    exit 1
fi

echo ""
echo "Configuration:"
echo "  CT ID:        $CT_ID"
echo "  Hostname:     $CT_HOSTNAME"
echo "  Memory:       ${CT_MEMORY}MB"
echo "  Disk:         ${CT_DISK}GB"
echo "  Cores:        $CT_CORES"
echo "  NFS Server:   $NFS_SERVER"
echo "  NFS Share:    $NFS_SHARE"
echo "  Mount Point:  $NFS_MOUNT_POINT"
echo ""

read -rp "Proceed with container creation? [y/N] " confirm
if [[ "$confirm" != [yY] ]]; then
    echo "Aborted."
    exit 0
fi

# Step 1: Create the LXC container
echo ""
echo "[1/6] Creating LXC container $CT_ID..."
pct create "$CT_ID" "$CT_TEMPLATE" \
    --hostname "$CT_HOSTNAME" \
    --memory "$CT_MEMORY" \
    --swap "$CT_SWAP" \
    --rootfs "${CT_STORAGE}:${CT_DISK}" \
    --cores "$CT_CORES" \
    --net0 "name=eth0,bridge=${CT_BRIDGE},ip=dhcp" \
    --unprivileged 1 \
    --features "nesting=1" \
    --onboot 1 \
    --start 0

# Step 2: Configure NFS mount in container
echo "[2/6] Configuring NFS mount..."

# Add NFS mount point to container config
# For unprivileged containers, we bind-mount from the host
# First, mount NFS on the host
HOST_NFS_MOUNT="/mnt/yastl-nfs-${CT_ID}"
mkdir -p "$HOST_NFS_MOUNT"

# Add to /etc/fstab on host if not already present
FSTAB_ENTRY="${NFS_SERVER}:${NFS_SHARE} ${HOST_NFS_MOUNT} nfs rw,soft,intr 0 0"
if ! grep -qF "$HOST_NFS_MOUNT" /etc/fstab; then
    echo "$FSTAB_ENTRY" >> /etc/fstab
    echo "  Added NFS mount to /etc/fstab"
fi
mount -a 2>/dev/null || mount "$HOST_NFS_MOUNT" || true

# Bind mount NFS into the container
pct set "$CT_ID" -mp0 "${HOST_NFS_MOUNT},mp=${NFS_MOUNT_POINT},ro=1"
echo "  NFS share will be available at ${NFS_MOUNT_POINT} inside the container"

# Step 3: Start container and install dependencies
echo "[3/6] Starting container and installing dependencies..."
pct start "$CT_ID"
sleep 5  # Wait for container to boot

pct exec "$CT_ID" -- bash -c "
    apt-get update
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        libgl1-mesa-glx libglib2.0-0 \
        git curl
    apt-get clean
    rm -rf /var/lib/apt/lists/*
"

# Step 4: Install YASTL
echo "[4/6] Installing YASTL application..."
pct exec "$CT_ID" -- bash -c "
    mkdir -p /opt/yastl
    mkdir -p ${YASTL_DATA_DIR}/thumbnails
    python3 -m venv /opt/yastl/venv
"

# Copy application files into container
echo "  Copying application files..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tar -cf - -C "$SCRIPT_DIR" app/ pyproject.toml | pct exec "$CT_ID" -- tar -xf - -C /opt/yastl/

pct exec "$CT_ID" -- bash -c "
    cd /opt/yastl
    /opt/yastl/venv/bin/pip install --no-cache-dir .
"

# Step 5: Create systemd service
echo "[5/6] Creating systemd service..."
pct exec "$CT_ID" -- bash -c "cat > /etc/systemd/system/yastl.service << 'UNIT'
[Unit]
Description=YASTL - Yet Another STL 3D Model Library
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/yastl
Environment=YASTL_MODEL_LIBRARY_DB=${YASTL_DATA_DIR}/library.db
Environment=YASTL_MODEL_LIBRARY_SCAN_PATH=${NFS_MOUNT_POINT}
Environment=YASTL_MODEL_LIBRARY_THUMBNAIL_PATH=${YASTL_DATA_DIR}/thumbnails
ExecStart=/opt/yastl/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${YASTL_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
"

pct exec "$CT_ID" -- systemctl daemon-reload
pct exec "$CT_ID" -- systemctl enable yastl
pct exec "$CT_ID" -- systemctl start yastl

# Step 6: Get container IP and show summary
echo "[6/6] Verifying installation..."
sleep 3

CT_IP=$(pct exec "$CT_ID" -- hostname -I | awk '{print $1}')

echo ""
echo "========================================"
echo "  YASTL Setup Complete!"
echo "========================================"
echo ""
echo "  Container ID:  $CT_ID"
echo "  Container IP:  ${CT_IP:-<pending DHCP>}"
echo "  Web UI:        http://${CT_IP:-<IP>}:${YASTL_PORT}"
echo ""
echo "  NFS Mount:     ${NFS_MOUNT_POINT} (read-only)"
echo "  Database:      ${YASTL_DATA_DIR}/library.db"
echo "  Thumbnails:    ${YASTL_DATA_DIR}/thumbnails/"
echo ""
echo "  Service:       systemctl status yastl (inside CT)"
echo "  Logs:          journalctl -u yastl -f (inside CT)"
echo ""
echo "  To trigger initial scan, visit:"
echo "    http://${CT_IP:-<IP>}:${YASTL_PORT}"
echo "  and click 'Scan Library' or run:"
echo "    curl -X POST http://${CT_IP:-<IP>}:${YASTL_PORT}/api/scan"
echo ""
