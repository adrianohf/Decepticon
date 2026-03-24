#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
# Decepticon 2.0 — One-line installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/catower/decepticon/main/scripts/install.sh | bash
#
# Environment variables:
#   VERSION              — Install a specific version (default: latest)
#   DECEPTICON_HOME      — Install directory (default: ~/.decepticon)
#   SKIP_PULL            — Skip Docker image pull (default: false)
# ─────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Constants ─────────────────────────────────────────────────────
REPO="catower/decepticon"
BRANCH="main"
RAW_BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"

# ── Colors ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[0;2m'
BOLD='\033[1m'
NC='\033[0m'

# ── Helpers ───────────────────────────────────────────────────────
info()    { echo -e "${DIM}$*${NC}"; }
success() { echo -e "${GREEN}$*${NC}"; }
warn()    { echo -e "${YELLOW}$*${NC}"; }
error()   { echo -e "${RED}$*${NC}" >&2; }
bold()    { echo -e "${BOLD}$*${NC}"; }

# ── Pre-flight checks ────────────────────────────────────────────
preflight() {
    # curl
    if ! command -v curl >/dev/null 2>&1; then
        error "Error: curl is required but not installed."
        exit 1
    fi

    # Docker
    if ! command -v docker >/dev/null 2>&1; then
        error "Error: Docker is required but not installed."
        echo -e "${DIM}Install Docker: ${NC}https://docs.docker.com/get-docker/"
        exit 1
    fi

    # Docker daemon
    if ! docker info >/dev/null 2>&1; then
        error "Error: Docker daemon is not running."
        echo -e "${DIM}Start Docker and re-run the installer.${NC}"
        exit 1
    fi

    # Docker Compose v2
    if ! docker compose version >/dev/null 2>&1; then
        error "Error: Docker Compose v2 is required."
        echo -e "${DIM}Docker Compose is included with Docker Desktop.${NC}"
        echo -e "${DIM}For Linux: ${NC}https://docs.docker.com/compose/install/linux/"
        exit 1
    fi
}

# ── Version resolution ───────────────────────────────────────────
resolve_version() {
    if [[ -n "${VERSION:-}" ]]; then
        DECEPTICON_VERSION="$VERSION"
        return
    fi

    info "Fetching latest version..."
    local latest
    latest=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" \
        | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')

    if [[ -z "$latest" ]]; then
        # No releases yet — use branch
        DECEPTICON_VERSION="latest"
        info "No releases found, using latest from $BRANCH branch."
    else
        DECEPTICON_VERSION="$latest"
    fi
}

# ── Download files ────────────────────────────────────────────────
download_files() {
    local install_dir="$1"

    info "Downloading configuration files..."

    # docker-compose.yml (always overwrite — this is infrastructure, not user config)
    curl -fsSL "$RAW_BASE/docker-compose.yml" -o "$install_dir/docker-compose.yml"

    # .env (only if not exists — never overwrite user's API keys)
    if [[ ! -f "$install_dir/.env" ]]; then
        curl -fsSL "$RAW_BASE/.env.example" -o "$install_dir/.env"
        info "Created .env from template. You'll need to add your API keys."
    else
        info ".env already exists, preserving your configuration."
    fi

    # LiteLLM config
    mkdir -p "$install_dir/config"
    curl -fsSL "$RAW_BASE/config/litellm.yaml" -o "$install_dir/config/litellm.yaml"

    # Version marker
    echo "$DECEPTICON_VERSION" > "$install_dir/.version"
}

# ── Create launcher script ───────────────────────────────────────
create_launcher() {
    local bin_dir="$1"
    local install_dir="$2"

    mkdir -p "$bin_dir"

    cat > "$bin_dir/decepticon" << 'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

DECEPTICON_HOME="${DECEPTICON_HOME:-$HOME/.decepticon}"
COMPOSE_FILE="$DECEPTICON_HOME/docker-compose.yml"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $DECEPTICON_HOME/.env"
COMPOSE_PROFILES="$COMPOSE --profile cli"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
DIM='\033[0;2m'
BOLD='\033[1m'
NC='\033[0m'

check_api_key() {
    if grep -q "your-.*-key-here" "$DECEPTICON_HOME/.env" 2>/dev/null; then
        echo -e "${YELLOW}Warning: API keys not configured.${NC}"
        echo -e "${DIM}Run ${NC}${BOLD}decepticon config${NC}${DIM} to set your API keys.${NC}"
        echo ""
    fi
}

wait_for_server() {
    local port="${LANGGRAPH_PORT:-2024}"
    local max_wait=60
    local waited=0
    echo -ne "${DIM}Waiting for LangGraph server"
    while ! curl -sf "http://localhost:$port/ok" >/dev/null 2>&1; do
        if [[ $waited -ge $max_wait ]]; then
            echo -e "${NC}"
            echo -e "${RED}Server failed to start within ${max_wait}s.${NC}"
            echo -e "${DIM}Check logs: ${NC}${BOLD}decepticon logs${NC}"
            exit 1
        fi
        echo -n "."
        sleep 2
        waited=$((waited + 2))
    done
    echo -e " ${GREEN}ready${NC}"
}

case "${1:-}" in
    ""|start)
        check_api_key

        # Start background services
        echo -e "${DIM}Starting services...${NC}"
        $COMPOSE up -d litellm postgres sandbox langgraph

        wait_for_server

        # Run CLI in foreground (interactive)
        $COMPOSE_PROFILES run --rm cli
        ;;

    stop)
        echo -e "${DIM}Stopping all services...${NC}"
        $COMPOSE down
        echo -e "${GREEN}All services stopped.${NC}"
        ;;

    update)
        echo -e "${DIM}Pulling latest images...${NC}"
        $COMPOSE_PROFILES pull
        echo -e "${GREEN}Updated. Run ${NC}${BOLD}decepticon${NC}${GREEN} to restart.${NC}"
        ;;

    status)
        $COMPOSE ps
        ;;

    logs)
        $COMPOSE logs -f "${2:-langgraph}"
        ;;

    config)
        ${EDITOR:-${VISUAL:-nano}} "$DECEPTICON_HOME/.env"
        ;;

    victims)
        $COMPOSE --profile victims up -d
        echo -e "${GREEN}Victim targets started.${NC}"
        echo -e "${DIM}Use ${NC}${BOLD}decepticon status${NC}${DIM} to verify.${NC}"
        ;;

    --version|-v)
        echo "decepticon $(cat "$DECEPTICON_HOME/.version" 2>/dev/null || echo 'dev')"
        ;;

    --help|-h|help)
        echo -e "${BOLD}Decepticon${NC} — AI-powered autonomous red team framework"
        echo ""
        echo -e "${BOLD}Usage:${NC}"
        echo "  decepticon              Start services and open CLI"
        echo "  decepticon stop         Stop all services"
        echo "  decepticon update       Pull latest Docker images"
        echo "  decepticon status       Show service status"
        echo "  decepticon logs [svc]   Follow service logs (default: langgraph)"
        echo "  decepticon config       Edit configuration (.env)"
        echo "  decepticon victims      Start vulnerable test targets"
        echo "  decepticon --version    Show version"
        ;;

    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo -e "${DIM}Run ${NC}${BOLD}decepticon --help${NC}${DIM} for usage.${NC}"
        exit 1
        ;;
esac
LAUNCHER

    chmod 755 "$bin_dir/decepticon"
}

# ── PATH setup (bash/zsh/fish) ────────────────────────────────────
setup_path() {
    local bin_dir="$1"
    local path_export="export PATH=\"$bin_dir:\$PATH\""

    # Already in PATH?
    if echo "$PATH" | tr ':' '\n' | grep -qx "$bin_dir"; then
        info "PATH already includes $bin_dir"
        return
    fi

    # GitHub Actions
    if [[ -n "${GITHUB_PATH:-}" ]]; then
        echo "$bin_dir" >> "$GITHUB_PATH"
        return
    fi

    local current_shell
    current_shell=$(basename "${SHELL:-bash}")
    local XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

    case "$current_shell" in
        fish)
            local fish_config="$XDG_CONFIG_HOME/fish/config.fish"
            if [[ -f "$fish_config" ]]; then
                if ! grep -q "$bin_dir" "$fish_config" 2>/dev/null; then
                    echo -e "\n# decepticon" >> "$fish_config"
                    echo "fish_add_path $bin_dir" >> "$fish_config"
                    info "Added to PATH in $fish_config"
                fi
            fi
            ;;
        zsh)
            local zshrc="${ZDOTDIR:-$HOME}/.zshrc"
            if [[ -f "$zshrc" ]] || [[ -w "$(dirname "$zshrc")" ]]; then
                if ! grep -q "$bin_dir" "$zshrc" 2>/dev/null; then
                    echo -e "\n# decepticon" >> "$zshrc"
                    echo "$path_export" >> "$zshrc"
                    info "Added to PATH in $zshrc"
                fi
            fi
            ;;
        *)
            # bash and others
            local bashrc="$HOME/.bashrc"
            local profile="$HOME/.profile"
            local target="$bashrc"
            [[ ! -f "$target" ]] && target="$profile"

            if [[ -f "$target" ]] || [[ -w "$(dirname "$target")" ]]; then
                if ! grep -q "$bin_dir" "$target" 2>/dev/null; then
                    echo -e "\n# decepticon" >> "$target"
                    echo "$path_export" >> "$target"
                    info "Added to PATH in $target"
                fi
            fi
            ;;
    esac
}

# ── Pull Docker images ────────────────────────────────────────────
pull_images() {
    local install_dir="$1"

    if [[ "${SKIP_PULL:-}" == "true" ]]; then
        info "Skipping Docker image pull (SKIP_PULL=true)."
        return
    fi

    echo ""
    info "Pulling Docker images (this may take a few minutes)..."
    (cd "$install_dir" && docker compose --env-file .env --profile cli pull) || {
        warn "Warning: Failed to pull some images."
        info "You can pull them manually later: decepticon update"
    }
}

# ── Main ──────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BOLD}Decepticon 2.0${NC} — Installer"
    echo ""

    # Pre-flight
    preflight

    # Version
    resolve_version

    # Install directory
    local install_dir="${DECEPTICON_HOME:-$HOME/.decepticon}"
    local bin_dir="$HOME/.local/bin"
    mkdir -p "$install_dir"

    info "Installing Decepticon $DECEPTICON_VERSION"
    info "Directory: $install_dir"
    echo ""

    # Download
    download_files "$install_dir"
    success "Configuration files downloaded."

    # Launcher
    create_launcher "$bin_dir" "$install_dir"
    success "Launcher installed to $bin_dir/decepticon"

    # PATH
    setup_path "$bin_dir"

    # Docker images
    pull_images "$install_dir"

    # Done
    echo ""
    echo -e "${GREEN}────────────────────────────────────────────${NC}"
    echo -e "${GREEN}  Decepticon installed successfully!${NC}"
    echo -e "${GREEN}────────────────────────────────────────────${NC}"
    echo ""
    echo -e "  ${BOLD}1.${NC} Configure your API key:"
    echo -e "     ${BOLD}decepticon config${NC}"
    echo ""
    echo -e "  ${BOLD}2.${NC} Start Decepticon:"
    echo -e "     ${BOLD}decepticon${NC}"
    echo ""

    # Hint to reload shell
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$bin_dir"; then
        echo -e "  ${DIM}Restart your shell or run:${NC}"
        echo -e "     ${BOLD}export PATH=\"$bin_dir:\$PATH\"${NC}"
        echo ""
    fi
}

main "$@"
