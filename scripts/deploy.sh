#!/usr/bin/env bash
# Deploy the dashboard to Cloudflare Pages.
#
# Only the website artifacts are published (index.html, functions/, static
# assets). Source CSVs, Python scripts and Git metadata are excluded so the
# upload stays small and Cloudflare's 25 MiB per-file limit is respected.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_NAME="${CLOUDFLARE_PAGES_PROJECT:-ph-shopee-dashboard-wting}"
STAGING_PARENT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
STAGING_DIR="$(mktemp -d "$STAGING_PARENT/ph-shopee-pages.XXXXXX")"

# Copy the published site.
cp "$PROJECT_DIR/index.html" "$STAGING_DIR/index.html"

# Functions (Cloudflare Pages Functions) - only if present.
if [ -d "$PROJECT_DIR/functions" ]; then
  mkdir -p "$STAGING_DIR/functions"
  cp -R "$PROJECT_DIR/functions/." "$STAGING_DIR/functions/"
fi

# Static assets.
for item in _headers _redirects robots.txt favicon.ico assets styles; do
  if [ -e "$PROJECT_DIR/$item" ]; then
    cp -R "$PROJECT_DIR/$item" "$STAGING_DIR/"
  fi
done

echo "Deploying from $STAGING_DIR"
cd "$STAGING_DIR"
exec npx wrangler pages deploy . --project-name="$PROJECT_NAME" "$@"
