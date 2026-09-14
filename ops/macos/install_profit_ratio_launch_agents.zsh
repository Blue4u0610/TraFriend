#!/bin/zsh

set -euo pipefail

readonly REPOSITORY_ROOT="/Users/bluefile/Blue's coding/PythonProject/TraFriend"
readonly SOURCE_DIRECTORY="${REPOSITORY_ROOT}/ops/macos"
readonly AGENT_DIRECTORY="${HOME}/Library/LaunchAgents"
readonly LOG_DIRECTORY="${HOME}/Library/Logs/TraFriend"
readonly DOMAIN="gui/$(/usr/bin/id -u)"

install_agent() {
  local label="$1"
  local source="${SOURCE_DIRECTORY}/${label}.plist"
  local destination="${AGENT_DIRECTORY}/${label}.plist"
  /bin/launchctl bootout "${DOMAIN}/${label}" >/dev/null 2>&1 || true
  /usr/bin/install -m 600 "${source}" "${destination}"
  /bin/launchctl bootstrap "${DOMAIN}" "${destination}"
  /bin/launchctl enable "${DOMAIN}/${label}"
}

/bin/mkdir -p "${AGENT_DIRECTORY}" "${LOG_DIRECTORY}"
"${SOURCE_DIRECTORY}/run_profit_ratio_capture.zsh" --check

install_agent "xyz.trafriend.keep-awake"
install_agent "xyz.trafriend.profit-ratio-capture"
/bin/launchctl kickstart -k "${DOMAIN}/xyz.trafriend.keep-awake"

/bin/echo "TraFriend keep-awake LaunchAgent: LOADED"
/bin/echo "TraFriend capture LaunchAgent: LOADED"
/bin/echo "Schedule: 09:50, 10:20, 13:20, 13:50, 16:20, 16:50 local time"
