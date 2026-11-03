#!/usr/bin/env bash
# Cloudflare Pages deployment script (CI-safe)
set -euo pipefail

echo "::group::Environment"
echo "CF_PAGES=1" && echo "CF_PAGES_UPLOAD_JWT=${CF_PAGES_UPLOAD_JWT:+present}"
echo "CLOUDFLARE_API_TOKEN=${CLOUDFLARE_API_TOKEN:+present}"
echo "CLOUDFLARE_ACCOUNT_ID=${CLOUDFLARE_ACCOUNT_ID:+present}"
echo "CF_PAGES_BRANCH=${CF_PAGES_BRANCH:-}"
echo "CF_PAGES_COMMIT_SHA=${CF_PAGES_COMMIT_SHA:-}"
echo "::endgroup::"

# Pages CI provides CF_PAGES_UPLOAD_JWT automatically
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] && [ -z "${CF_PAGES_UPLOAD_JWT:-}" ]; then
  echo "No Cloudflare credentials found in environment." >&2
  exit 1
fi

npx --yes wrangler@latest pages deploy . \
  --project-name "${CF_PAGES_PROJECT_NAME:-ph-shopee-dashboard-wting}" \
  --branch "${CF_PAGES_BRANCH:-main}" \
  --commit-hash "${CF_PAGES_COMMIT_SHA:-HEAD}" \
  --commit-message "Deploy from CI"
