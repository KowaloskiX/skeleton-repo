#!/usr/bin/env bash
# Checks the environment BEFORE the first run: tool versions, pin consistency and free ports.
#
# It grew out of concrete failures, not predictions:
#   - a locally installed mongod stole the port from Docker and the application quietly talked
#     to a different database,
#   - Node 23 passed most gates, but dependency-cruiser supports only ^22||^24,
#   - a zombie server on :3000 was "borrowed" by Playwright instead of starting its own.
#
# Deliberately plain bash: it has to work when NOTHING is installed yet.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

RED=$'\033[31m'; YELLOW=$'\033[33m'; GREEN=$'\033[32m'; DIM=$'\033[2m'; OFF=$'\033[0m'
errors=0
warnings=0

ok()   { printf '  %sOK%s   %s\n' "$GREEN" "$OFF" "$1"; }
warn() { printf '  %sWARN%s %s\n' "$YELLOW" "$OFF" "$1"; warnings=$((warnings + 1)); }
bad()  { printf '  %sFAIL%s %s\n' "$RED" "$OFF" "$1"; errors=$((errors + 1)); }

# --- pins: mise.toml has to agree with .nvmrc, which CI uses ---
printf '\n%sPin consistency%s\n' "$DIM" "$OFF"
nvmrc_node="$(tr -d '[:space:]' < .nvmrc 2>/dev/null)"
mise_node="$(grep -E '^node[[:space:]]*=' mise.toml 2>/dev/null | sed -E 's/.*"([^"]+)".*/\1/')"
if [ -z "$nvmrc_node" ] || [ -z "$mise_node" ]; then
  warn "cannot read the Node version from .nvmrc or mise.toml"
elif [ "$nvmrc_node" = "$mise_node" ]; then
  ok "Node pinned consistently in .nvmrc and mise.toml ($nvmrc_node)"
else
  bad ".nvmrc says $nvmrc_node, mise.toml says $mise_node — CI uses .nvmrc"
fi

# --- tool versions ---
printf '\n%sTools%s\n' "$DIM" "$OFF"
check_major() { # name, version-output, required-major
  local name="$1" got="$2" want="$3"
  if [ -z "$got" ]; then bad "$name: not found (requires $want)"; return; fi
  if [ "${got%%.*}" = "$want" ]; then ok "$name $got"
  else bad "$name $got — requires $want.x"; fi
}

check_major "node" "$(node --version 2>/dev/null | tr -d 'v')" "$nvmrc_node"
check_major "pnpm" "$(pnpm --version 2>/dev/null)" "11"
python_version="$(python3 --version 2>/dev/null | awk '{print $2}')"
case "$python_version" in
  3.12.*) ok "python $python_version" ;;
  "")     bad "python3: not found (requires 3.12.x)" ;;
  *)      warn "python $python_version — CI and mise pin 3.12.x" ;;
esac
uv_version="$(uv --version 2>/dev/null | awk '{print $2}')"
if [ -n "$uv_version" ]; then
  ok "uv $uv_version"
else
  bad "uv: not found"
fi

if docker info >/dev/null 2>&1; then
  ok "docker is running"
else
  bad "docker is not responding — the database and Redis will not start, nor testcontainers"
fi

# --- porty ---
# Mongo on 27018 and Redis on 6380 (not the defaults) precisely because locally installed
# instances win over the Docker ports.
printf '\n%sPorty%s\n' "$DIM" "$OFF"
check_port() { # port, do czego, czy-nasz-kontener-go-zajmuje-to-ok
  local port="$1" what="$2"
  local pid
  pid="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1)"
  if [ -z "$pid" ]; then
    ok "$port wolny ($what)"
    return
  fi
  local owner
  owner="$(ps -o comm= -p "$pid" 2>/dev/null | xargs basename 2>/dev/null)"
  warn "$port taken by '$owner' (pid $pid) — $what"
}

# The frontend and API ports are configurable (WEB_PORT/API_PORT) — we check the ones that
# will actually be used, so the warning is not about somebody else's process.
check_port "${WEB_PORT:-3000}" "frontend dev; a taken port gets 'borrowed' by Playwright (workaround: WEB_PORT=3100)"
check_port "${API_PORT:-8000}" "backend uvicorn (workaround: API_PORT=8100)"
check_port 27018 "MongoDB from docker-compose"
check_port 6380 "Redis from docker-compose"

# --- configuration ---
printf '\n%sConfiguration%s\n' "$DIM" "$OFF"
if [ -f .env ]; then
  if grep -q 'change-me' .env 2>/dev/null; then
    warn ".env still has AUTH_SECRET=change-me — generate one: openssl rand -hex 32"
  else
    ok ".env present"
  fi
else
  warn "no .env — copy it: cp .env.example .env (without it the defaults apply)"
fi

printf '\n'
if [ "$errors" -gt 0 ]; then
  printf '%sErrors: %d, warnings: %d%s\n' "$RED" "$errors" "$warnings" "$OFF"
  exit 1
fi
printf '%sEnvironment ready%s (warnings: %d)\n' "$GREEN" "$OFF" "$warnings"
