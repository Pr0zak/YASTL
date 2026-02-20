#!/usr/bin/env bash
# YASTL - Proxmox LXC Container Setup Script
# Run this on the Proxmox host to create and configure an LXC container for YASTL
#
# This script works in two modes:
#   1. Local: Run from a cloned YASTL repo - copies files directly into the container
#   2. Remote: Set YASTL_INSTALL_MODE=git to clone from GitHub inside the container
#
# Prerequisites:
#   - Proxmox VE host with LXC support
#   - A Debian/Ubuntu LXC template downloaded
#
# Usage:
#   chmod +x proxmox-setup.sh
#   ./proxmox-setup.sh
#
# For the interactive one-liner installer, use ct-install.sh instead:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Pr0zak/YASTL/main/ct-install.sh)"

set -euo pipefail

# ============================================================
# Configuration - Edit these values or set as environment variables
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

# YASTL settings
YASTL_PORT="${YASTL_PORT:-8000}"
YASTL_DATA_DIR="/opt/yastl/data"

# Install mode: "local" (copy from checkout) or "git" (clone from GitHub)
YASTL_INSTALL_MODE="${YASTL_INSTALL_MODE:-local}"
YASTL_REPO="${YASTL_REPO:-https://github.com/Pr0zak/YASTL.git}"
YASTL_BRANCH="${YASTL_BRANCH:-main}"

# ============================================================

echo "========================================"
echo "  YASTL - Proxmox LXC Setup"
echo "========================================"

# Detect install mode based on whether we're in a repo checkout
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
if [[ "$YASTL_INSTALL_MODE" == "local" ]] && [[ ! -f "${SCRIPT_DIR}/pyproject.toml" ]]; then
    echo "  No local checkout detected, switching to git clone mode."
    YASTL_INSTALL_MODE="git"
fi

echo ""
echo "Configuration:"
echo "  CT ID:        $CT_ID"
echo "  Hostname:     $CT_HOSTNAME"
echo "  Memory:       ${CT_MEMORY}MB"
echo "  Disk:         ${CT_DISK}GB"
echo "  Cores:        $CT_CORES"
echo "  Install Mode: $YASTL_INSTALL_MODE"
echo ""

read -rp "Proceed with container creation? [y/N] " confirm
if [[ "$confirm" != [yY] ]]; then
    echo "Aborted."
    exit 0
fi

# Step 1: Create the LXC container
echo ""
echo "[1/5] Creating LXC container $CT_ID..."
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

# Step 2: Start container and install dependencies
echo "[2/5] Starting container and installing dependencies..."
pct start "$CT_ID"
sleep 5  # Wait for container to boot

pct exec "$CT_ID" -- bash -c "
    export DEBIAN_FRONTEND=noninteractive

    # Disable Proxmox enterprise repos (require paid subscription)
    rm -f /etc/apt/sources.list.d/pve-enterprise.list
    rm -f /etc/apt/sources.list.d/ceph.list

    apt-get update -qq
    apt-get install -y -qq --no-install-recommends \
        python3-full python3-pip python3-dev \
        libgl1-mesa-glx libglib2.0-0 libgomp1 \
        git curl ca-certificates \
        build-essential pkg-config >/dev/null 2>&1

    # Install version-matched venv package (e.g. python3.13-venv on Trixie)
    PY_VER=\$(python3 -c 'import sys; print(f\"{sys.version_info[0]}.{sys.version_info[1]}\")')
    apt-get install -y -qq \"python\${PY_VER}-venv\" >/dev/null 2>&1

    apt-get clean
    rm -rf /var/lib/apt/lists/*
"

# Step 3: Install YASTL
echo "[3/5] Installing YASTL application..."
pct exec "$CT_ID" -- bash -c "
    mkdir -p /opt/yastl
    mkdir -p ${YASTL_DATA_DIR}/thumbnails
    python3 -m venv /opt/yastl/venv
"

if [[ "$YASTL_INSTALL_MODE" == "git" ]]; then
    echo "  Cloning YASTL from GitHub..."
    pct exec "$CT_ID" -- bash -c "
        git clone --depth 1 --branch '${YASTL_BRANCH}' '${YASTL_REPO}' /opt/yastl/src 2>/dev/null
        cd /opt/yastl/src
        /opt/yastl/venv/bin/pip install --no-cache-dir -q . 2>&1 | tail -1
    "
    WORK_DIR="/opt/yastl/src"
else
    echo "  Copying application files from local checkout..."
    tar -cf - -C "$SCRIPT_DIR" app/ pyproject.toml | pct exec "$CT_ID" -- tar -xf - -C /opt/yastl/
    pct exec "$CT_ID" -- bash -c "
        cd /opt/yastl
        /opt/yastl/venv/bin/pip install --no-cache-dir .
    "
    WORK_DIR="/opt/yastl"
fi

# Step 4: Create systemd service
echo "[4/5] Creating systemd service..."
pct exec "$CT_ID" -- bash -c "cat > /etc/systemd/system/yastl.service << UNIT
[Unit]
Description=YASTL - Yet Another STL 3D Model Library
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=${WORK_DIR}
Environment=YASTL_MODEL_LIBRARY_DB=${YASTL_DATA_DIR}/library.db
Environment=YASTL_MODEL_LIBRARY_THUMBNAIL_PATH=${YASTL_DATA_DIR}/thumbnails
Environment=YASTL_PORT=${YASTL_PORT}
ExecStart=/opt/yastl/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${YASTL_PORT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
"

pct exec "$CT_ID" -- systemctl daemon-reload
pct exec "$CT_ID" -- systemctl enable yastl
pct exec "$CT_ID" -- systemctl start yastl

# Create update helper (only for git installs)
if [[ "$YASTL_INSTALL_MODE" == "git" ]]; then
    pct exec "$CT_ID" -- bash -c "cat > /usr/local/bin/yastl-update << 'UPDATEEOF'
#!/usr/bin/env bash
set -euo pipefail
echo \"Updating YASTL...\"
cd /opt/yastl/src
git pull --ff-only
/opt/yastl/venv/bin/pip install --no-cache-dir -q .
systemctl restart yastl
echo \"YASTL updated and restarted.\"
UPDATEEOF
chmod +x /usr/local/bin/yastl-update"
fi

# Step 5: Get container IP and show summary
echo "[5/5] Verifying installation..."
sleep 3

CT_IP=$(pct exec "$CT_ID" -- hostname -I | awk '{print $1}') || CT_IP=""

echo ""
echo "========================================"
echo "  YASTL Setup Complete!"
echo "========================================"
echo ""
echo "  Container ID:  $CT_ID"
echo "  Container IP:  ${CT_IP:-<pending DHCP>}"
echo "  Web UI:        http://${CT_IP:-<IP>}:${YASTL_PORT}"
echo ""
echo "  Database:      ${YASTL_DATA_DIR}/library.db"
echo "  Thumbnails:    ${YASTL_DATA_DIR}/thumbnails/"
echo ""
echo "  Service:       pct exec $CT_ID -- systemctl status yastl"
echo "  Logs:          pct exec $CT_ID -- journalctl -u yastl -f"
if [[ "$YASTL_INSTALL_MODE" == "git" ]]; then
    echo "  Update:        pct exec $CT_ID -- yastl-update"
fi
echo ""
echo "  Configure model library paths in the web UI Settings page."
echo ""
