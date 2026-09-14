#!/bin/zsh

set -euo pipefail

readonly AGENT_DIRECTORY="${HOME}/Library/LaunchAgents"
readonly DOMAIN="gui/$(/usr/bin/id -u)"

for label in xyz.trafriend.profit-ratio-capture xyz.trafriend.keep-awake; do
  /bin/launchctl bootout "${DOMAIN}/${label}" >/dev/null 2>&1 || true
  /bin/rm -f "${AGENT_DIRECTORY}/${label}.plist"
done

/bin/echo "TraFriend LaunchAgents: REMOVED"
/bin/echo "Keychain items were preserved."
