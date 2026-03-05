#!/bin/bash
# Source .env vars for launchd services
WORKSPACE="$(dirname "$(dirname "$(realpath "$0")")")"
if [ -f "$WORKSPACE/.env" ]; then
  set -a
  source "$WORKSPACE/.env"
  set +a
fi
export WORKSPACE
exec /usr/bin/python3 "$@"
