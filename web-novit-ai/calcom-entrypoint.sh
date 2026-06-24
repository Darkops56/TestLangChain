#!/bin/sh
# Custom Cal.com startup wrapper that patches compiled chunks to fix the IS_E2E
# service map emptying issue while keeping the license bypass intact.
#
# Problem: NEXT_PUBLIC_IS_E2E=1 bypasses EE license checks (good) but also
# empties CalendarServiceMap, VideoApiAdapterMap, and AnalyticsServiceMap (bad).
#
# Solution: Patch the compiled JS to change the service map ternary condition
# from "1"===process.env.NEXT_PUBLIC_IS_E2E?{}:{...services...}
# to   "PATCHED"===process.env.NEXT_PUBLIC_IS_E2E?{}:{...services...}
#
# Since the env var is "1" (not "PATCHED"), the condition is always false,
# so the actual service maps are always used. License checks use a different
# pattern (no ?{}:) and remain unaffected.

set -e

CHUNKS_DIR="/calcom/apps/web/.next/server/chunks"

if [ -d "$CHUNKS_DIR" ]; then
  echo "[calcom-patch] Patching service map E2E checks in compiled chunks (including ssr/)..."

  PATCHED=0
  # Use find to recurse into subdirectories (ssr/, etc.)
  for f in $(find "$CHUNKS_DIR" -name '*.js' -type f); do
    if grep -q '"1"===process.env.NEXT_PUBLIC_IS_E2E?{}:' "$f" 2>/dev/null; then
      sed -i 's/"1"===process\.env\.NEXT_PUBLIC_IS_E2E?{}:/"PATCHED"===process.env.NEXT_PUBLIC_IS_E2E?{}:/g' "$f"
      # Show path relative to chunks dir
      REL=$(echo "$f" | sed "s|$CHUNKS_DIR/||")
      echo "[calcom-patch]   Patched: $REL"
      PATCHED=$((PATCHED + 1))
    fi
  done

  echo "[calcom-patch] Done. Patched $PATCHED chunk file(s)."
else
  echo "[calcom-patch] WARNING: Chunks directory not found at $CHUNKS_DIR"
fi

# ── Patch 2: Fix Zoho Calendar all-day event date parsing ──────────────
# Bug: Cal.com's Zoho Calendar integration expects dates in format
# YYYYMMDD[T]HHmmssZ but Zoho returns all-day events as just "YYYYMMDD"
# (e.g. "20260308" without time/timezone). This causes dayjs to create
# an Invalid Date, and .toISOString() throws "RangeError: Invalid time value".
#
# Fix: Replace the getUnavailability date parsing to detect all-day format
# (8 digits only) and parse with "YYYYMMDD" format instead. Also wrap in
# try-catch so any other unexpected format is gracefully skipped.

ZOHO_CHUNK=$(find "$CHUNKS_DIR" -name '*zohocalendar*CalendarService*.js' -type f 2>/dev/null | head -1)

if [ -n "$ZOHO_CHUNK" ]; then
  echo "[calcom-patch] Patching Zoho Calendar all-day event date parsing..."

  # The buggy code in getUnavailability:
  #   .map(t=>{let e=(0,i.default)(t.dateandtime.start,"YYYYMMDD[T]HHmmssZ").utc().toISOString(),
  #            a=(0,i.default)(t.dateandtime.end,"YYYYMMDD[T]HHmmssZ").utc().toISOString();
  #            return{start:e,end:a}})
  #
  # Replace with version that handles YYYYMMDD (all-day) + try-catch for safety

  ZOHO_OLD='\.map(t=>{let e=(0,i\.default)(t\.dateandtime\.start,"YYYYMMDD\[T\]HHmmssZ")\.utc()\.toISOString(),a=(0,i\.default)(t\.dateandtime\.end,"YYYYMMDD\[T\]HHmmssZ")\.utc()\.toISOString();return{start:e,end:a}})'
  ZOHO_NEW='.map(t=>{try{let s=t.dateandtime.start,d=t.dateandtime.end,e=(/^\\d{8}$/.test(s)?(0,i.default)(s,"YYYYMMDD"):(0,i.default)(s,"YYYYMMDD[T]HHmmssZ")).utc().toISOString(),a=(/^\\d{8}$/.test(d)?(0,i.default)(d,"YYYYMMDD"):(0,i.default)(d,"YYYYMMDD[T]HHmmssZ")).utc().toISOString();return{start:e,end:a}}catch(x){return null}}).filter(t=>t!==null)'

  if grep -q 'YYYYMMDD\[T\]HHmmssZ' "$ZOHO_CHUNK" 2>/dev/null; then
    sed -i "s|${ZOHO_OLD}|${ZOHO_NEW}|g" "$ZOHO_CHUNK"
    echo "[calcom-patch]   Patched: $(basename "$ZOHO_CHUNK")"
  else
    echo "[calcom-patch]   Zoho chunk already patched or pattern not found"
  fi
else
  echo "[calcom-patch] WARNING: Zoho Calendar chunk not found"
fi

# ── Patch 3: Fix Zoho Calendar transparent events blocking availability ─
# Bug: Cal.com's getUnavailability() returns ALL non-private Zoho events as
# "busy" blocks. This means all-day events marked as "Don't add to free/busy
# schedule" (transparency=1) still block availability slots.
#
# The Zoho Calendar API uses an integer `transparency` field:
#   0 = Add to free/busy schedule (opaque → busy)
#   1 = Don't add to free/busy schedule (transparent → free)
#
# Fix: Add a transparency check to the getUnavailability filter so that
# transparent events (transparency===1) are excluded.
#   Before: .filter(t=>!1===t.isprivate)
#   After:  .filter(t=>!1===t.isprivate&&1!==t.transparency)

ZOHO_CHUNK=${ZOHO_CHUNK:-$(find "$CHUNKS_DIR" -name '*zohocalendar*CalendarService*.js' -type f 2>/dev/null | head -1)}

if [ -n "$ZOHO_CHUNK" ]; then
  echo "[calcom-patch] Patching Zoho Calendar transparency filter..."

  if grep -q '\.filter(t=>!1===t\.isprivate)' "$ZOHO_CHUNK" 2>/dev/null; then
    sed -i 's/\.filter(t=>!1===t\.isprivate)/.filter(t=>!1===t.isprivate\&\&1!==t.transparency)/g' "$ZOHO_CHUNK"
    echo "[calcom-patch]   Patched transparency filter: $(basename "$ZOHO_CHUNK")"
  else
    echo "[calcom-patch]   Transparency filter already patched or pattern not found"
  fi
else
  echo "[calcom-patch] WARNING: Zoho Calendar chunk not found for transparency patch"
fi

# ── Cal.com startup (inlined from start.sh for control) ────────────────
# We inline start.sh instead of exec'ing it so we can insert steps
# between the seed (which resets app enabled states) and yarn start.

echo "[calcom-patch] Starting Cal.com startup sequence..."
cd /calcom

scripts/replace-placeholder.sh "$BUILT_NEXT_PUBLIC_WEBAPP_URL" "$NEXT_PUBLIC_WEBAPP_URL"

# Extract host:port from DATABASE_URL (postgresql://user:pass@host:port/db)
DB_HOSTPORT=$(echo "$DATABASE_URL" | sed -n 's|.*@\([^/]*\)/.*|\1|p')
scripts/wait-for-it.sh ${DB_HOSTPORT} -- echo "database is up"

npx prisma migrate deploy --schema /calcom/packages/prisma/schema.prisma
npx ts-node --transpile-only /calcom/scripts/seed-app-store.ts

# ── Patch 4: Enable calendar & video apps after seed ───────────────────
# The seed-app-store.ts script resets app enabled states on every startup.
# Re-enable Google Calendar, Zoho Calendar, and Google Meet so users don't
# have to manually toggle them in Settings → Apps after each container recreate.

echo "[calcom-patch] Enabling Google Calendar, Zoho Calendar, and Google Meet apps..."
node -e "
  const { Client } = require('pg');
  const c = new Client(process.env.DATABASE_URL);
  c.connect()
    .then(() => c.query(
      \"UPDATE \\\"App\\\" SET enabled = true WHERE slug IN ('google-calendar', 'zohocalendar', 'google-meet')\"
    ))
    .then(r => { console.log('[calcom-patch]   Enabled ' + r.rowCount + ' app(s)'); c.end(); })
    .catch(e => { console.error('[calcom-patch]   Enable apps error: ' + e.message); c.end(); });
"

echo "[calcom-patch] Starting Cal.com server (direct next start, bypassing turbo)..."
cd /calcom/apps/web
exec /calcom/node_modules/.bin/next start -p 3000
