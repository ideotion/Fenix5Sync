#!/usr/bin/env bash
# Fenix5Sync installer — Debian/Ubuntu bootstrap, idempotent and safe to re-run.
#
# Two ways to run it:
#   1. One-line bootstrap (clones the repo first):
#        curl -fsSL https://raw.githubusercontent.com/ideotion/Fenix5Sync/main/install.sh | bash
#   2. From a checkout you already have:
#        git clone https://github.com/ideotion/Fenix5Sync.git && cd Fenix5Sync && ./install.sh
#
# It will: ensure git + system deps (python3, venv, pip, jmtpfs, gpsbabel) via apt,
# clone/update the repo, create a venv and install Python deps, write a default
# config if none exists, create a launcher + .desktop entry + systemd --user unit,
# then start the server on 127.0.0.1 and open your browser.
#
# Tunables (environment variables):
#   F5S_REPO_URL  override clone URL        F5S_BRANCH   branch to clone
#   F5S_DIR       install dir               F5S_PORT     server port (default 8765)
#   F5S_NO_LAUNCH set to 1 to skip auto-launch

set -euo pipefail

APP="fenix5sync"
DEFAULT_REPO_URL="https://github.com/ideotion/Fenix5Sync.git"
REPO_URL="${F5S_REPO_URL:-$DEFAULT_REPO_URL}"
BRANCH="${F5S_BRANCH:-}"
INSTALL_DIR="${F5S_DIR:-$HOME/.local/share/$APP}"
CONFIG_DIR="$HOME/.config/$APP"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
PORT="${F5S_PORT:-8765}"
BIN_DIR="$HOME/.local/bin"

c_info=$'\033[1;36m'; c_ok=$'\033[1;32m'; c_warn=$'\033[1;33m'; c_err=$'\033[1;31m'; c_off=$'\033[0m'
log()  { printf '%s==>%s %s\n' "$c_info" "$c_off" "$*"; }
ok()   { printf '%s[ok]%s %s\n' "$c_ok"  "$c_off" "$*"; }
warn() { printf '%s[!]%s %s\n'  "$c_warn" "$c_off" "$*" >&2; }
die()  { printf '%s[x]%s %s\n'  "$c_err" "$c_off" "$*" >&2; exit 1; }

# ---- privilege helper for apt ---------------------------------------------
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
fi

apt_install() {
  # Install only the packages that are actually missing (idempotent).
  local pkgs=("$@") missing=()
  command -v dpkg >/dev/null 2>&1 || { warn "dpkg not found; skipping apt step (non-Debian?)."; return 0; }
  for p in "${pkgs[@]}"; do
    dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p")
  done
  if [ ${#missing[@]} -eq 0 ]; then ok "system packages already present: ${pkgs[*]}"; return 0; fi
  command -v apt-get >/dev/null 2>&1 || { warn "apt-get not found; please install manually: ${missing[*]}"; return 0; }
  log "Installing system packages: ${missing[*]}"
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get update -qq || warn "apt-get update failed; continuing"
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y "${missing[@]}" \
    || die "apt-get install failed for: ${missing[*]}"
}

# ---- 1. git + locate/obtain the source ------------------------------------
apt_install git

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$SELF_DIR" ] && git -C "$SELF_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  # Running from an existing checkout: use it in place, read the real origin URL.
  SRC_DIR="$(git -C "$SELF_DIR" rev-parse --show-toplevel)"
  REPO_URL="$(git -C "$SRC_DIR" remote get-url origin 2>/dev/null || echo "$REPO_URL")"
  log "Using existing checkout: $SRC_DIR"
  log "Detected origin: $REPO_URL"
else
  # Bootstrap: clone (or update) into the install dir.
  if [ -d "$INSTALL_DIR/.git" ]; then
    log "Updating existing clone at $INSTALL_DIR"
    git -C "$INSTALL_DIR" pull --ff-only || warn "git pull failed; continuing with existing checkout"
  else
    log "Cloning $REPO_URL -> $INSTALL_DIR"
    if [ -n "$BRANCH" ]; then
      git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR" || die "git clone failed"
    else
      git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" || die "git clone failed"
    fi
  fi
  SRC_DIR="$INSTALL_DIR"
fi

# ---- 2. system dependencies -----------------------------------------------
# python3-venv/pip for the environment; jmtpfs for MTP watches; gpsbabel for GPX.
apt_install python3 python3-venv python3-pip jmtpfs gpsbabel

command -v python3 >/dev/null 2>&1 || die "python3 is required but not found"

# ---- 3. Python virtual environment + deps ---------------------------------
VENV="$SRC_DIR/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  log "Creating virtual environment at $VENV"
  python3 -m venv "$VENV"
fi
log "Installing Python dependencies (this may take a minute)"
"$VENV/bin/python" -m pip install --upgrade --quiet pip
"$VENV/bin/python" -m pip install --quiet -e "$SRC_DIR"
ok "Python environment ready"

VENV_BIN="$VENV/bin/$APP"

# ---- 4. default config -----------------------------------------------------
if [ ! -f "$CONFIG_FILE" ]; then
  mkdir -p "$CONFIG_DIR"
  cp "$SRC_DIR/config.example.yaml" "$CONFIG_FILE"
  if [ "$PORT" != "8765" ]; then
    sed -i "s/^\( *port: \).*/\1$PORT/" "$CONFIG_FILE"
  fi
  ok "Wrote default config to $CONFIG_FILE"
else
  ok "Config already exists at $CONFIG_FILE (left unchanged)"
fi
# Read the effective port back from the config so the launcher/URL agree with it.
PORT="$(awk '/^server:/{s=1} s&&/^ *port:/{print $2; exit}' "$CONFIG_FILE" 2>/dev/null || echo "$PORT")"
URL="http://127.0.0.1:$PORT/"

# ---- 5. launcher script ----------------------------------------------------
mkdir -p "$BIN_DIR"
LAUNCHER="$BIN_DIR/$APP"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
# Fenix5Sync launcher (generated by install.sh). Passes through to the venv CLI.
exec "$VENV_BIN" "\$@"
EOF
chmod +x "$LAUNCHER"
ok "Launcher: $LAUNCHER  (e.g. '$APP serve --open')"
case ":$PATH:" in
  *":$BIN_DIR:"*) : ;;
  *) warn "$BIN_DIR is not on your PATH. Add it, or run: $VENV_BIN serve --open" ;;
esac

# ---- 6. XDG .desktop entry -------------------------------------------------
APPS_DIR="$HOME/.local/share/applications"
mkdir -p "$APPS_DIR"
cat > "$APPS_DIR/$APP.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Fenix5Sync
Comment=Local-first, offline Garmin Fenix 5 activity browser
Exec=$LAUNCHER serve --open
Terminal=false
Categories=Utility;Network;Sports;
Keywords=garmin;fenix;fit;running;cycling;
EOF
ok "Desktop entry: $APPS_DIR/$APP.desktop"

# ---- 7. systemd --user service (optional auto-start) -----------------------
if command -v systemctl >/dev/null 2>&1; then
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/$APP.service" <<EOF
[Unit]
Description=Fenix5Sync local server
After=network.target

[Service]
Type=simple
ExecStart=$VENV_BIN serve
Restart=on-failure

[Install]
WantedBy=default.target
EOF
  ok "systemd --user unit: $UNIT_DIR/$APP.service"
  echo "    Enable auto-start on login with:"
  echo "      systemctl --user enable --now $APP.service"
fi

# ---- 8. auto-launch --------------------------------------------------------
echo
if [ "${F5S_NO_LAUNCH:-0}" = "1" ]; then
  ok "Install complete. Start later with: $APP serve --open"
  exit 0
fi

# Already running on this port? Just open the browser.
if curl -fsS --max-time 1 "${URL}api/health" >/dev/null 2>&1; then
  ok "Server already running at $URL"
else
  log "Starting server at $URL"
  LOG_DIR="$HOME/.local/share/$APP/logs"; mkdir -p "$LOG_DIR"
  nohup "$VENV_BIN" serve --port "$PORT" >>"$LOG_DIR/server.out" 2>&1 &
  disown || true
  # Wait until it is accepting connections.
  for _ in $(seq 1 60); do
    curl -fsS --max-time 1 "${URL}api/health" >/dev/null 2>&1 && break
    sleep 0.25
  done
fi

if curl -fsS --max-time 1 "${URL}api/health" >/dev/null 2>&1; then
  ok "Fenix5Sync is running at $URL"
  if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  else
    echo "    Open this URL in your browser: $URL"
  fi
else
  warn "Server did not become ready; check $HOME/.local/share/$APP/logs/"
  echo "    Try running in the foreground: $APP serve --open"
fi
