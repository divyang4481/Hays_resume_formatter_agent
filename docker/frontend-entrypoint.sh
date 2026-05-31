#!/bin/sh
set -eu

: "${API_BASE_URL:=http://localhost:8000}"
: "${PORTAL_BASE_PATH:=/portal}"

export API_BASE_URL PORTAL_BASE_PATH
envsubst '${API_BASE_URL} ${PORTAL_BASE_PATH}' \
    < /tmp/frontend-config.template.js \
    > /usr/share/nginx/html/portal/config.js
