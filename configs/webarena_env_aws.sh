#!/usr/bin/env bash
# Source this before running BrowserGym WebArena tasks.
# Assumes WebArena services are deployed on the EC2 host with the standard ports.

WEBARENA_BASE_URL="${WEBARENA_BASE_URL:-http://18.117.39.199}"

export WA_SHOPPING="${WA_SHOPPING:-${WEBARENA_BASE_URL}:8082/}"
export WA_SHOPPING_ADMIN="${WA_SHOPPING_ADMIN:-${WEBARENA_BASE_URL}:8083/admin}"
export WA_REDDIT="${WA_REDDIT:-${WEBARENA_BASE_URL}:8080}"
export WA_GITLAB="${WA_GITLAB:-${WEBARENA_BASE_URL}:9001}"
export WA_WIKIPEDIA="${WA_WIKIPEDIA:-${WEBARENA_BASE_URL}:8081/wikipedia_en_all_maxi_2022-05/A/User:The_other_Kiwix_guy/Landing}"
export WA_MAP="${WA_MAP:-${WEBARENA_BASE_URL}:443}"
export WA_HOMEPAGE="${WA_HOMEPAGE:-${WEBARENA_BASE_URL}:80}"

# Set to empty if the deployed WebArena stack does not expose full reset.
export WA_FULL_RESET="${WA_FULL_RESET:-${WEBARENA_BASE_URL}:7565}"

echo "WA_SHOPPING=${WA_SHOPPING}"
echo "WA_SHOPPING_ADMIN=${WA_SHOPPING_ADMIN}"
echo "WA_REDDIT=${WA_REDDIT}"
echo "WA_GITLAB=${WA_GITLAB}"
echo "WA_WIKIPEDIA=${WA_WIKIPEDIA}"
echo "WA_MAP=${WA_MAP}"
echo "WA_HOMEPAGE=${WA_HOMEPAGE}"
echo "WA_FULL_RESET=${WA_FULL_RESET}"
