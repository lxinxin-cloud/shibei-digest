#!/usr/bin/env bash
set -euo pipefail

read -r -s -p "Bark device key: " BARK_DEVICE_KEY
printf "\n"
read -r -s -p "Feishu webhook URL: " FEISHU_WEBHOOK_URL
printf "\n"

security add-generic-password -a "$USER" -s shibei_digest_BARK_DEVICE_KEY -w "$BARK_DEVICE_KEY" -U >/dev/null
security add-generic-password -a "$USER" -s shibei_digest_FEISHU_WEBHOOK_URL -w "$FEISHU_WEBHOOK_URL" -U >/dev/null

printf "Saved Bark and Feishu credentials to macOS Keychain.\n"
