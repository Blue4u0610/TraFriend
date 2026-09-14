#!/bin/zsh

# Finite launchd entry point for TraFriend's production market-data update.
# Secrets are read from the logged-in user's Keychain and never echoed.

set -u
umask 077

readonly REPOSITORY_ROOT="/Users/bluefile/Blue's coding/PythonProject/TraFriend"
readonly API_ROOT="${REPOSITORY_ROOT}/services/api"
readonly PYTHON="${API_ROOT}/.venv/bin/python"
readonly OPEND_APP="/Users/bluefile/Applications/Futu_OpenD.app"
readonly KEYCHAIN_ACCOUNT="$(/usr/bin/id -un)"
readonly DATABASE_SERVICE="xyz.trafriend.production-database-url"
readonly ALPACA_KEY_SERVICE="xyz.trafriend.alpaca-api-key"
readonly ALPACA_SECRET_SERVICE="xyz.trafriend.alpaca-secret-key"
readonly LOCK_DIRECTORY="${TMPDIR:-/tmp}/xyz.trafriend.profit-ratio.lock"

timestamp() {
  /bin/date -u '+%Y-%m-%dT%H:%M:%SZ'
}

log() {
  /bin/echo "$(timestamp) $1"
}

notify_failure() {
  /usr/bin/osascript -e \
    'display notification "自动采集失败，请检查 TraFriend 日志和 Futu 登录状态。" with title "TraFriend"' \
    >/dev/null 2>&1 || true
}

keychain_value() {
  /usr/bin/security find-generic-password \
    -a "${KEYCHAIN_ACCOUNT}" \
    -s "$1" \
    -w 2>/dev/null
}

release_lock() {
  /bin/rm -f "${LOCK_DIRECTORY}/pid" 2>/dev/null || true
  /bin/rmdir "${LOCK_DIRECTORY}" 2>/dev/null || true
}

acquire_lock() {
  if /bin/mkdir "${LOCK_DIRECTORY}" 2>/dev/null; then
    /bin/echo "$$" >"${LOCK_DIRECTORY}/pid"
    return 0
  fi

  local existing_pid=""
  if [[ -r "${LOCK_DIRECTORY}/pid" ]]; then
    existing_pid="$(<"${LOCK_DIRECTORY}/pid")"
  fi
  if [[ "${existing_pid}" == <-> ]] && /bin/kill -0 "${existing_pid}" 2>/dev/null; then
    log "capture skipped: another invocation is running"
    return 1
  fi

  release_lock
  /bin/mkdir "${LOCK_DIRECTORY}" 2>/dev/null || return 1
  /bin/echo "$$" >"${LOCK_DIRECTORY}/pid"
}

ensure_opend() {
  if /usr/bin/nc -z 127.0.0.1 11111 >/dev/null 2>&1; then
    log "Futu OpenD listener: READY"
    return 0
  fi

  if [[ ! -d "${OPEND_APP}" ]]; then
    log "Futu OpenD listener: FAILED (application missing)"
    return 1
  fi

  log "Futu OpenD listener: STARTING"
  /usr/bin/open -gj "${OPEND_APP}" >/dev/null 2>&1 || return 1
  local attempt
  for attempt in {1..12}; do
    /bin/sleep 5
    if /usr/bin/nc -z 127.0.0.1 11111 >/dev/null 2>&1; then
      log "Futu OpenD listener: READY"
      return 0
    fi
  done
  log "Futu OpenD listener: FAILED (login or startup required)"
  return 1
}

validate_runtime() {
  if [[ ! -x "${PYTHON}" ]]; then
    log "runtime validation: FAILED (Python environment missing)"
    return 1
  fi

  (
    cd "${API_ROOT}" || exit 1
    "${PYTHON}" -c '
import os
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
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
        revision = MigrationContext.configure(connection).get_current_revision()
    expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    if revision != expected:
        raise SystemExit(1)
    print(f"production database: READY host={target.host} database={target.database}")
finally:
    engine.dispose()
'
  )
}

main() {
  if ! acquire_lock; then
    return 0
  fi
  trap release_lock EXIT INT TERM

  local database_url alpaca_key alpaca_secret
  database_url="$(keychain_value "${DATABASE_SERVICE}")" || {
    log "runtime validation: FAILED (production database Keychain item missing)"
    notify_failure
    return 1
  }
  alpaca_key="$(keychain_value "${ALPACA_KEY_SERVICE}")" || {
    log "runtime validation: FAILED (Alpaca API key Keychain item missing)"
    notify_failure
    return 1
  }
  alpaca_secret="$(keychain_value "${ALPACA_SECRET_SERVICE}")" || {
    log "runtime validation: FAILED (Alpaca secret Keychain item missing)"
    notify_failure
    return 1
  }

  export DATABASE_URL="${database_url}"
  export ALPACA_API_KEY="${alpaca_key}"
  export ALPACA_SECRET_KEY="${alpaca_secret}"
  export TRAFRIEND_ENV="production"
  export TRAFRIEND_CORS_ORIGINS="https://trafriend.xyz,https://www.trafriend.xyz"
  export TRAFRIEND_DAILY_CLOSE_PROVIDER="alpaca"
  export TRAFRIEND_PROFIT_RATIO_METHODOLOGY="FUTU_CHIPS_PROFIT_RATIO"
  export TRAFRIEND_FUTU_OPEND_HOST="127.0.0.1"
  export TRAFRIEND_FUTU_OPEND_PORT="11111"
  export TRAFRIEND_FUTU_PROFIT_RATIO_QUALITY="UNKNOWN"
  unset database_url alpaca_key alpaca_secret

  if ! validate_runtime; then
    log "runtime validation: FAILED"
    notify_failure
    return 1
  fi
  if ! ensure_opend; then
    notify_failure
    return 1
  fi
  if [[ "${1:-}" == "--check" ]]; then
    log "launchd runtime check: PASS"
    return 0
  fi

  local futu_status market_status
  log "Futu Profit Ratio capture: START"
  (
    cd "${API_ROOT}" || exit 1
    "${PYTHON}" -m trafriend_api.scripts.capture_futu_profit_ratio
  )
  futu_status=$?

  log "Daily market update: START"
  (
    cd "${API_ROOT}" || exit 1
    "${PYTHON}" -m trafriend_api.scripts.run_daily_market_update
  )
  market_status=$?

  if (( futu_status != 0 || market_status != 0 )); then
    log "capture result: FAILED futu=${futu_status} market=${market_status}"
    notify_failure
    return 1
  fi
  log "capture result: COMPLETE"
}

main "$@"
