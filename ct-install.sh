#!/usr/bin/env bash
# YASTL - Proxmox Container One-Line Installer
# =============================================
# Run this directly on a Proxmox VE host to create an LXC container
# with YASTL fully installed and ready to use.
#
# One-liner install:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/Pr0zak/YASTL/main/ct-install.sh)"
#
# Or download and run:
#   curl -fsSL https://raw.githubusercontent.com/Pr0zak/YASTL/main/ct-install.sh -o ct-install.sh
#   chmod +x ct-install.sh
#   ./ct-install.sh
#
# Non-interactive mode (all options via environment variables):
#   export CT_ID=200
#   export YASTL_NONINTERACTIVE=1
#   bash ct-install.sh

set -euo pipefail

# ============================================================
# Defaults
# ============================================================
YASTL_REPO="${YASTL_REPO:-https://github.com/Pr0zak/YASTL.git}"
YASTL_BRANCH="${YASTL_BRANCH:-main}"

CT_ID="${CT_ID:-}"
CT_HOSTNAME="${CT_HOSTNAME:-yastl}"
CT_MEMORY="${CT_MEMORY:-2048}"
CT_SWAP="${CT_SWAP:-512}"
CT_DISK="${CT_DISK:-8}"
CT_CORES="${CT_CORES:-2}"
CT_TEMPLATE="${CT_TEMPLATE:-}"
CT_STORAGE="${CT_STORAGE:-local-lvm}"
CT_BRIDGE="${CT_BRIDGE:-vmbr0}"

YASTL_PORT="${YASTL_PORT:-8000}"
YASTL_DATA_DIR="/opt/yastl/data"
YASTL_NONINTERACTIVE="${YASTL_NONINTERACTIVE:-0}"

# ============================================================
# Colors and formatting
# ============================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

banner() {
    echo -e "${CYAN}${BOLD}"
    cat << 'EOF'
 __   __ _    ____  _____  _
 \ \ / // \  / ___||_   _|| |
  \ V // _ \ \___ \  | |  | |
   | |/ ___ \ ___) | | |  | |___
   |_/_/   \_\____/  |_|  |_____|

  Yet Another STL - 3D Model Library
  Proxmox LXC Container Installer
EOF
    echo -e "${NC}"
}

info()    { echo -e "${BLUE}[INFO]${NC}    $*"; }
success() { echo -e "${GREEN}[OK]${NC}      $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}    $*"; }
error()   { echo -e "${RED}[ERROR]${NC}   $*"; }
step()    { echo -e "\n${BOLD}${CYAN}>> $*${NC}"; }

prompt_value() {
    local var_name="$1"
    local prompt_text="$2"
    local default_val="$3"
    local current_val="${!var_name:-$default_val}"

    if [[ "$YASTL_NONINTERACTIVE" == "1" ]]; then
        eval "$var_name=\"$current_val\""
        return
    fi

    local display_default=""
    if [[ -n "$current_val" ]]; then
        display_default=" ${DIM}[${current_val}]${NC}"
    fi

    echo -ne "  ${prompt_text}${display_default}: "
    read -r input
    if [[ -n "$input" ]]; then
        eval "$var_name=\"$input\""
    else
        eval "$var_name=\"$current_val\""
    fi
}

# ============================================================
# Preflight checks
# ============================================================
preflight() {
    step "Running preflight checks"

    # Must be root
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root on a Proxmox host."
        echo "  Try: sudo bash ct-install.sh"
        exit 1
    fi

    # Must be Proxmox
    if ! command -v pct &>/dev/null; then
        error "Proxmox VE not detected (pct command not found)."
        echo "  This script must be run on a Proxmox VE host."
        exit 1
    fi

    if ! command -v pvesh &>/dev/null; then
        error "Proxmox VE not detected (pvesh command not found)."
        exit 1
    fi

    success "Proxmox VE detected"

    # Check for curl or wget
    if ! command -v curl &>/dev/null && ! command -v wget &>/dev/null; then
        error "Neither curl nor wget found. Install one first."
        exit 1
    fi

    # Check for git
    if ! command -v git &>/dev/null; then
        warn "git not found on host - installing..."
        # Disable Proxmox enterprise repos if present (require paid subscription)
        if [[ -f /etc/apt/sources.list.d/pve-enterprise.list ]]; then
            rm -f /etc/apt/sources.list.d/pve-enterprise.list
            warn "Disabled pve-enterprise repo (requires subscription)"
        fi
        if [[ -f /etc/apt/sources.list.d/ceph.list ]]; then
            rm -f /etc/apt/sources.list.d/ceph.list
            warn "Disabled ceph enterprise repo (requires subscription)"
        fi
        apt-get update -qq && apt-get install -y -qq git
        if ! command -v git &>/dev/null; then
            error "Failed to install git on host"
            exit 1
        fi
        success "git installed"
    fi

    success "All preflight checks passed"
}

# ============================================================
# Auto-detect available templates
# ============================================================
detect_template() {
    if [[ -n "$CT_TEMPLATE" ]]; then
        return
    fi

    step "Detecting available LXC templates"

    # Look for Debian 12 templates first, then any Debian, then Ubuntu
    local template=""
    local templates_dir="/var/lib/vz/template/cache"

    if [[ -d "$templates_dir" ]]; then
        template=$(ls -1 "$templates_dir" 2>/dev/null \
            | grep -E 'debian-12.*\.tar\.(gz|zst|xz)$' \
            | head -1) || true

        if [[ -z "$template" ]]; then
            template=$(ls -1 "$templates_dir" 2>/dev/null \
                | grep -E 'debian-.*\.tar\.(gz|zst|xz)$' \
                | sort -rV | head -1) || true
        fi

        if [[ -z "$template" ]]; then
            template=$(ls -1 "$templates_dir" 2>/dev/null \
                | grep -E 'ubuntu-.*\.tar\.(gz|zst|xz)$' \
                | sort -rV | head -1) || true
        fi
    fi

    if [[ -n "$template" ]]; then
        CT_TEMPLATE="local:vztmpl/${template}"
        success "Found template: ${template}"
    else
        warn "No suitable template found locally."
        info "Downloading Debian 12 template..."
        pveam update >/dev/null 2>&1 || true

        local available
        available=$(pveam available --section system 2>/dev/null \
            | grep -E 'debian-12' | awk '{print $2}' | head -1) || true

        if [[ -n "$available" ]]; then
            pveam download local "$available"
            CT_TEMPLATE="local:vztmpl/${available}"
            success "Downloaded template: ${available}"
        else
            error "Could not find or download a Debian template."
            echo "  Download one manually via: pveam download local <template>"
            echo "  Then re-run with: CT_TEMPLATE=local:vztmpl/<filename> $0"
            exit 1
        fi
    fi
}

# ============================================================
# Auto-detect next available CT ID
# ============================================================
detect_ct_id() {
    if [[ -n "$CT_ID" ]]; then
        return
    fi

    # Find the next available ID starting from 200
    local id=200
    while pct status "$id" &>/dev/null; do
        ((id++))
    done
    CT_ID="$id"
}

# ============================================================
# Detect available storage
# ============================================================
detect_storage() {
    local available
    available=$(pvesm status 2>/dev/null \
        | awk 'NR>1 && $2 ~ /^(lvm|lvmthin|dir|zfs)/ {print $1}' \
        | head -1) || true

    if [[ -n "$available" ]]; then
        CT_STORAGE="$available"
    fi
}

# ============================================================
# Detect network bridges
# ============================================================
detect_bridge() {
    local bridge
    bridge=$(ip -o link show type bridge 2>/dev/null \
        | awk -F': ' '{print $2}' \
        | head -1) || true

    if [[ -n "$bridge" ]]; then
        CT_BRIDGE="$bridge"
    fi
}

# ============================================================
# Interactive configuration wizard
# ============================================================
wizard() {
    step "Configuration"

    detect_ct_id
    detect_storage
    detect_bridge

    if [[ "$YASTL_NONINTERACTIVE" == "1" ]]; then
        return
    fi

    echo -e "\n  ${BOLD}Container Settings${NC}"
    echo -e "  ${DIM}────────────────────────────────────────${NC}"
    prompt_value CT_ID       "Container ID"       "$CT_ID"
    prompt_value CT_HOSTNAME "Hostname"           "$CT_HOSTNAME"
    prompt_value CT_MEMORY   "Memory (MB)"        "$CT_MEMORY"
    prompt_value CT_CORES    "CPU cores"          "$CT_CORES"
    prompt_value CT_DISK     "Disk size (GB)"     "$CT_DISK"
    prompt_value CT_STORAGE  "Storage pool"       "$CT_STORAGE"
    prompt_value CT_BRIDGE   "Network bridge"     "$CT_BRIDGE"
    prompt_value YASTL_PORT  "YASTL web port"     "$YASTL_PORT"
}

# ============================================================
# Show summary and confirm
# ============================================================
confirm() {
    echo ""
    echo -e "  ${BOLD}Summary${NC}"
    echo -e "  ${DIM}────────────────────────────────────────${NC}"
    echo -e "  Container ID:    ${BOLD}$CT_ID${NC}"
    echo -e "  Hostname:        $CT_HOSTNAME"
    echo -e "  Resources:       ${CT_MEMORY}MB RAM, ${CT_CORES} cores, ${CT_DISK}GB disk"
    echo -e "  Storage:         $CT_STORAGE"
    echo -e "  Network:         $CT_BRIDGE (DHCP)"
    echo -e "  Template:        $CT_TEMPLATE"
    echo -e "  Web port:        $YASTL_PORT"
    echo ""

    if [[ "$YASTL_NONINTERACTIVE" == "1" ]]; then
        return
    fi

    echo -ne "  ${BOLD}Proceed with installation? [Y/n]${NC} "
    read -r confirm_input
    if [[ "$confirm_input" =~ ^[nN] ]]; then
        echo "  Aborted."
        exit 0
    fi
}

# ============================================================
# Check if CT ID is already in use
# ============================================================
check_ct_exists() {
    if pct status "$CT_ID" &>/dev/null; then
        error "Container ID $CT_ID already exists."
        echo "  Choose a different ID or remove the existing container:"
        echo "    pct stop $CT_ID && pct destroy $CT_ID"
        exit 1
    fi
}

# ============================================================
# Create the LXC container
# ============================================================
create_container() {
    step "Creating LXC container $CT_ID"

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

    success "Container $CT_ID created"
}

# ============================================================
# Wait for container networking
# ============================================================
wait_for_network() {
    local max_wait=30
    local waited=0

    info "Waiting for container networking..."
    while [[ $waited -lt $max_wait ]]; do
        if pct exec "$CT_ID" -- ping -c1 -W1 8.8.8.8 &>/dev/null; then
            success "Container has network connectivity"
            return
        fi
        sleep 2
        ((waited += 2))
    done

    warn "Network not confirmed after ${max_wait}s, continuing anyway..."
}

# ============================================================
# Install system dependencies in the container
# ============================================================
install_deps() {
    step "Installing system dependencies inside container"

    pct exec "$CT_ID" -- bash -c "
        export DEBIAN_FRONTEND=noninteractive

        # Disable Proxmox enterprise repos (require paid subscription)
        rm -f /etc/apt/sources.list.d/pve-enterprise.list
        rm -f /etc/apt/sources.list.d/ceph.list

        apt-get update -qq
        apt-get install -y -qq --no-install-recommends \
            python3-full python3-pip python3-dev \
            libgomp1 \
            git curl ca-certificates \
            build-essential pkg-config

        # GL libraries (package names differ between Debian versions)
        apt-get install -y -qq libgl1-mesa-glx libglib2.0-0 2>/dev/null || \
            apt-get install -y -qq libgl1 libglib2.0-0t64 2>/dev/null || true

        # Install version-matched venv package (e.g. python3.13-venv on Trixie)
        PY_VER=\$(python3 -c 'import sys; print(f\"{sys.version_info[0]}.{sys.version_info[1]}\")')
        apt-get install -y -qq \"python\${PY_VER}-venv\" >/dev/null 2>&1

        apt-get clean
        rm -rf /var/lib/apt/lists/*
    "

    success "System dependencies installed"
}

# ============================================================
# Clone and install YASTL
# ============================================================
install_yastl() {
    step "Installing YASTL application"

    pct exec "$CT_ID" -- bash -c "
        # Create data directories
        mkdir -p '${YASTL_DATA_DIR}/thumbnails'

        # Set up Python virtual environment
        python3 -m venv /opt/yastl/venv

        # Clone from GitHub
        if ! git clone --depth 1 --branch '${YASTL_BRANCH}' '${YASTL_REPO}' /opt/yastl/src; then
            echo 'ERROR: git clone failed. Check network connectivity and that the repo/branch exist.' >&2
            exit 1
        fi

        # Install YASTL and dependencies
        cd /opt/yastl/src
        /opt/yastl/venv/bin/pip install --no-cache-dir -q .
    "

    success "YASTL installed"
}

# ============================================================
# Create systemd service
# ============================================================
create_service() {
    step "Creating systemd service"

    pct exec "$CT_ID" -- bash -c "cat > /etc/systemd/system/yastl.service << 'SERVICEEOF'
[Unit]
Description=YASTL - Yet Another STL 3D Model Library
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/yastl/src
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
SERVICEEOF
"

    pct exec "$CT_ID" -- systemctl daemon-reload
    pct exec "$CT_ID" -- systemctl enable yastl >/dev/null 2>&1
    pct exec "$CT_ID" -- systemctl start yastl

    success "YASTL service created and started"
}

# ============================================================
# Create update helper script inside the container
# ============================================================
create_update_script() {
    pct exec "$CT_ID" -- bash -c "cat > /usr/local/bin/yastl-update << 'UPDATEEOF'
#!/usr/bin/env bash
# YASTL update script - pull latest changes and restart
set -euo pipefail
echo \"Updating YASTL...\"
cd /opt/yastl/src
git pull --ff-only
/opt/yastl/venv/bin/pip install --no-cache-dir -q .
systemctl restart yastl
echo \"YASTL updated and restarted.\"
UPDATEEOF
chmod +x /usr/local/bin/yastl-update"
}

# ============================================================
# Verify installation
# ============================================================
verify() {
    step "Verifying installation"

    sleep 3

    # Check service status
    if pct exec "$CT_ID" -- systemctl is-active --quiet yastl 2>/dev/null; then
        success "YASTL service is running"
    else
        warn "Service may still be starting up..."
    fi

    # Get container IP
    CT_IP=$(pct exec "$CT_ID" -- hostname -I 2>/dev/null | awk '{print $1}') || CT_IP=""

    # Try health check
    local health_ok=false
    for i in 1 2 3 4 5; do
        if pct exec "$CT_ID" -- curl -sf "http://127.0.0.1:${YASTL_PORT}/health" &>/dev/null; then
            health_ok=true
            break
        fi
        sleep 2
    done

    if $health_ok; then
        success "Health check passed"
    else
        warn "Health check not responding yet (may need a moment to start)"
    fi
}

# ============================================================
# Print final summary
# ============================================================
summary() {
    echo ""
    echo -e "${GREEN}${BOLD}"
    echo "  ========================================"
    echo "    YASTL Installation Complete!"
    echo "  ========================================"
    echo -e "${NC}"
    echo -e "  ${BOLD}Access${NC}"
    if [[ -n "${CT_IP:-}" ]]; then
        echo -e "    Web UI:  ${BOLD}${GREEN}http://${CT_IP}:${YASTL_PORT}${NC}"
    else
        echo -e "    Web UI:  http://<CONTAINER_IP>:${YASTL_PORT}"
        echo -e "    ${DIM}(run 'pct exec $CT_ID -- hostname -I' to get the IP)${NC}"
    fi
    echo ""
    echo -e "  ${BOLD}Container${NC}"
    echo -e "    ID:        $CT_ID"
    echo -e "    Hostname:  $CT_HOSTNAME"
    echo -e "    Enter:     ${DIM}pct enter $CT_ID${NC}"
    echo ""
    echo -e "  ${BOLD}Management${NC}"
    echo -e "    Service:   ${DIM}pct exec $CT_ID -- systemctl status yastl${NC}"
    echo -e "    Logs:      ${DIM}pct exec $CT_ID -- journalctl -u yastl -f${NC}"
    echo -e "    Update:    ${DIM}pct exec $CT_ID -- yastl-update${NC}"
    echo -e "    Restart:   ${DIM}pct exec $CT_ID -- systemctl restart yastl${NC}"
    echo ""
    echo -e "  ${BOLD}Paths (inside container)${NC}"
    echo -e "    Database:    ${YASTL_DATA_DIR}/library.db"
    echo -e "    Thumbnails:  ${YASTL_DATA_DIR}/thumbnails/"
    echo -e "    App source:  /opt/yastl/src/"
    echo ""
    echo -e "  ${DIM}Configure model library paths in the web UI Settings page.${NC}"
    echo ""
}

# ============================================================
# Cleanup on failure
# ============================================================
cleanup_on_error() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo ""
        error "Installation failed (exit code: $exit_code)"
        echo ""
        echo "  To clean up the partially created container:"
        echo "    pct stop $CT_ID 2>/dev/null; pct destroy $CT_ID"
        echo ""
        echo "  To retry:"
        echo "    CT_ID=$CT_ID bash ct-install.sh"
    fi
}

# ============================================================
# Main
# ============================================================
main() {
    banner
    trap cleanup_on_error EXIT

    preflight
    detect_template
    wizard
    confirm

    check_ct_exists
    create_container

    # Start the container
    step "Starting container"
    pct start "$CT_ID"
    sleep 5
    wait_for_network

    install_deps
    install_yastl
    create_service
    create_update_script
    verify

    # Remove the error trap on success
    trap - EXIT
    summary
}

main "$@"
