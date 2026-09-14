#!/bin/zsh

# One-time interactive configuration. Secret values are entered silently and are
# stored only in the logged-in user's macOS Keychain.

set -euo pipefail
umask 077

readonly REPOSITORY_ROOT="/Users/bluefile/Blue's coding/PythonProject/TraFriend"
readonly API_ROOT="${REPOSITORY_ROOT}/services/api"
readonly PYTHON="${API_ROOT}/.venv/bin/python"
readonly KEYCHAIN_ACCOUNT="$(/usr/bin/id -un)"

keychain_value() {
  /usr/bin/security find-generic-password \
    -a "${KEYCHAIN_ACCOUNT}" \
    -s "$1" \
    -w 2>/dev/null
}

read_secret() {
  local prompt="$1"
  local value=""
  read -r -s "value?${prompt}"
  /bin/echo
  REPLY="${value}"
}

store_secret() {
  local service="$1"
  local value="$2"
  /usr/bin/security add-generic-password \
    -U \
    -a "${KEYCHAIN_ACCOUNT}" \
    -s "${service}" \
    -w "${value}" \
    -T /usr/bin/security \
    >/dev/null
}

production_url="${TRAFRIEND_PRODUCTION_DATABASE_URL:-}"
if [[ -z "${production_url}" ]]; then
  read_secret "Paste Render external DATABASE_URL (input hidden): "
  production_url="${REPLY}"
fi

alpaca_key="${ALPACA_API_KEY:-$(keychain_value "xyz.trafriend.alpaca-api-key" || true)}"
if [[ -z "${alpaca_key}" ]]; then
  read_secret "Paste ALPACA_API_KEY (input hidden): "
  alpaca_key="${REPLY}"
fi

alpaca_secret="${ALPACA_SECRET_KEY:-$(keychain_value "xyz.trafriend.alpaca-secret-key" || true)}"
if [[ -z "${alpaca_secret}" ]]; then
  read_secret "Paste ALPACA_SECRET_KEY (input hidden): "
  alpaca_secret="${REPLY}"
fi

if [[ -z "${production_url}" || -z "${alpaca_key}" || -z "${alpaca_secret}" ]]; then
  /bin/echo "Keychain configuration: FAILED (empty input)" >&2
  exit 1
fi

(
  cd "${API_ROOT}"
  DATABASE_URL="${production_url}" \
  TRAFRIEND_ENV=production \
  TRAFRIEND_CORS_ORIGINS=https://www.trafriend.xyz \
  "${PYTHON}" -c '
import os
from sqlalchemy import text
from trafriend_api.infrastructure.persistence.database import create_database_engine
from trafriend_api.infrastructure.persistence.database_target import (
    DatabaseEnvironment,
    require_writable_database_target,
)

target = require_writable_database_target(os.environ["DATABASE_URL"], "production")
if target.environment != DatabaseEnvironment.PRODUCTION:
    raise SystemExit(1)
engine = create_database_engine(os.environ["DATABASE_URL"])
try:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    print(f"Production connection: SUCCESS host={target.host} database={target.database}")
finally:
    engine.dispose()
'
)

store_secret "xyz.trafriend.production-database-url" "${production_url}"
store_secret "xyz.trafriend.alpaca-api-key" "${alpaca_key}"
store_secret "xyz.trafriend.alpaca-secret-key" "${alpaca_secret}"
unset production_url alpaca_key alpaca_secret REPLY

/bin/echo "Production database Keychain item: SET"
/bin/echo "Alpaca API key Keychain item: SET"
/bin/echo "Alpaca secret Keychain item: SET"
