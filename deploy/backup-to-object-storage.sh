#!/usr/bin/env bash
# Royce ERP Cloud -- off-server backup, per platform-architecture.md §14 / ADR-006.
#
# Runs in one of two modes, selected by $1:
#   hourly  -- DB-only dump (bench's default without --with-files), plus the
#              incremental file mirror below. Together: data AND files at most ~1h old.
#   full    -- daily (since 2026-09-25; was 6-hourly): DB + public/private files as one
#              matched, self-contained snapshot -- the clean "go back to that day" point
#              that doesn't depend on the mirror. On the 1st of a month also kept in
#              monthly/.
#
# Uploads under "<mode>/<domain>/<site>/<timestamp>/" -- mode as the TOP-level
# prefix, not nested under site, specifically so a single R2 lifecycle rule per tier
# can expire it without one rule per tenant. Retention (R2 lifecycle, set by hand in
# the dashboard -- see docs/operations/backups.md): hourly/ 7d, full/ 30d, monthly/
# 365d, files-history/ 30d; files/ (the mirror) and demo-golden/ are never expired.
#
# Discovers every tenant site on this server dynamically (no hardcoded site list --
# new tenants created by the Control Plane must get backed up without anyone
# remembering to update this script).
set -euo pipefail

MODE="${1:?Usage: $0 hourly|full}"
case "$MODE" in
    hourly) BENCH_BACKUP_ARGS=() ;;
    full)   BENCH_BACKUP_ARGS=(--with-files) ;;
    *) echo "Unknown mode: $MODE (expected 'hourly' or 'full')" >&2; exit 2 ;;
esac

FRAPPE_DOCKER_DIR="${FRAPPE_DOCKER_DIR:-/opt/royce/frappe_docker}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-royce}"
# Prod: r2-crypt:crypt -- an rclone crypt remote, so everything is encrypted on this
# server before upload (2026-09-25). That matters: each set holds a full database dump and
# Frappe's site_config backup (database password AND encryption_key). A plain
# r2:<bucket> still works, unencrypted.
RCLONE_REMOTE="${RCLONE_REMOTE:-r2:royceerp}"
DOMAIN_SUFFIX="${DOMAIN_SUFFIX:-royceltd.com}"
STAGING_DIR="${STAGING_DIR:-/opt/royce/backup-staging}"
RETENTION_DAYS="${RETENTION_DAYS:-3}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [$MODE] $*"; }

# Reports success/failure as an actual Prometheus metric, not just a log line nobody
# is watching -- node_exporter's textfile collector picks up any *.prom file here.
# Written atomically (temp file + mv) per the textfile collector's own documented
# convention, so a scrape never reads a half-written file.
report_metric() {
    local success="$1"
    local tmp
    tmp="$(mktemp "$TEXTFILE_DIR/.royce_backup.XXXXXX")"
    cat > "$tmp" <<-METRICS
	# HELP royce_backup_last_run_timestamp_seconds Unix time of the last backup attempt.
	# TYPE royce_backup_last_run_timestamp_seconds gauge
	royce_backup_last_run_timestamp_seconds{mode="$MODE"} $(date +%s)
	# HELP royce_backup_last_run_success Whether the last backup run fully succeeded (1) or not (0).
	# TYPE royce_backup_last_run_success gauge
	royce_backup_last_run_success{mode="$MODE"} $success
	METRICS
    chmod 644 "$tmp"  # mktemp defaults to 600 -- node_exporter runs as a different user and needs read access
    mv "$tmp" "$TEXTFILE_DIR/royce_backup_$MODE.prom"
}

# Discover sites: any directory under sites/ containing a site_config.json, excluding
# the shared "assets" directory.
mapfile -t SITES < <(
    docker compose --project-name "$COMPOSE_PROJECT" exec -T backend \
        bash -c 'for d in sites/*/; do [ -f "${d}site_config.json" ] && basename "$d"; done' \
        2>/dev/null
) || true

# Sites deliberately not backed up (space-separated), e.g. the public demo: it is reset
# from a golden snapshot every night (reset-demo.sh), so hourly copies are just clutter.
if [ -n "${EXCLUDE_SITES:-}" ]; then
    KEPT=()
    for s in "${SITES[@]}"; do
        [[ " $EXCLUDE_SITES " == *" $s "* ]] && log "skipping excluded site $s" || KEPT+=("$s")
    done
    SITES=("${KEPT[@]}")
fi

if [ "${#SITES[@]}" -eq 0 ]; then
    log "ERROR: no sites discovered -- refusing to run (this would silently back up nothing)"
    report_metric 0
    exit 1
fi

log "Discovered ${#SITES[@]} site(s): ${SITES[*]}"
FAILED=0

# --- Incremental file mirror (every run, after the site's DB dump) --------------------
# Hourly DB dumps alone left files up to a full-backup interval behind: a restore brought
# back the File records but not the files uploaded since (added 2026-09-25). rclone sync
# mirrors public/files and private/files to files/<domain>/<site>/, uploading only what
# changed; anything changed or deleted is moved to files-history/.../<timestamp>/ rather
# than lost. It runs in the pinned official rclone image with the sites volume mounted
# READ-ONLY -- the backup account can't read Docker's volume directory itself.
SITES_VOLUME="${SITES_VOLUME:-${COMPOSE_PROJECT}_sites}"
RCLONE_IMAGE="${RCLONE_IMAGE:-rclone/rclone:1.75.1}"
RCLONE_CONFIG_DIR="${RCLONE_CONFIG_DIR:-/opt/royce/backup-home/.config/rclone}"

sync_site_files() {
    local site="$1" kind rc=0
    # Guard: a wrong volume name makes Docker create an EMPTY volume, and syncing from
    # empty would empty the mirror. Only sync if the mount really holds this site.
    docker volume inspect "$SITES_VOLUME" >/dev/null 2>&1 || { log "FAILED: volume $SITES_VOLUME not found"; return 1; }
    for kind in public private; do
        docker run --rm --network bridge \
            -v "$SITES_VOLUME:/sites:ro" -v "$RCLONE_CONFIG_DIR:/config/rclone:ro" \
            --entrypoint sh "$RCLONE_IMAGE" -c '
                test -f "/sites/$1/site_config.json" || { echo "not a site: $1" >&2; exit 3; }
                rclone sync "/sites/$1/$2/files" "$3/files/$4/$1/$2/" \
                    --backup-dir "$3/files-history/$4/$1/$5/$2/" --stats 0' \
            _ "$site" "$kind" "$RCLONE_REMOTE" "$DOMAIN_SUFFIX" "$TIMESTAMP" || rc=1
    done
    if [ "$rc" = 0 ]; then log "Synced $site files to $RCLONE_REMOTE/files/$DOMAIN_SUFFIX/$site/"
    else log "FAILED: file sync for $site"; fi
    return $rc
}

for site in "${SITES[@]}"; do
    log "--- $site ---"
    run_start_marker="$(mktemp)"  # timestamp reference for "-newer" below, not real content

    if ! docker compose --project-name "$COMPOSE_PROJECT" exec -T backend \
            bench --site "$site" backup "${BENCH_BACKUP_ARGS[@]}"; then
        log "FAILED: bench backup for $site"
        FAILED=1
        rm -f "$run_start_marker"
        continue
    fi

    site_staging="$STAGING_DIR/$MODE/$site/$TIMESTAMP"
    mkdir -p "$site_staging"

    # Copy out only this run's files, selected by modification time -- NOT by
    # parsing/stripping filename suffixes. That approach was tried first and had a
    # real bug: "-files.tar" is a substring of "-private-files.tar", so stripping it
    # first left a mangled prefix that matched only the private-files entry and
    # caused the other files to be deleted as "not matching". Time-based selection
    # has no equivalent trap. See docs/operations/backups.md.
    docker compose --project-name "$COMPOSE_PROJECT" cp \
        "backend:/home/frappe/frappe-bench/sites/$site/private/backups/." "$site_staging/" \
        2>/dev/null || true
    find "$site_staging" -type f ! -newer "$run_start_marker" -delete
    rm -f "$run_start_marker"

    if [ -z "$(ls -A "$site_staging" 2>/dev/null)" ]; then
        log "FAILED: no backup files staged for $site -- not uploading an empty set"
        FAILED=1
        continue
    fi

    remote_path="$RCLONE_REMOTE/$MODE/$DOMAIN_SUFFIX/$site/$TIMESTAMP/"
    if rclone copy "$site_staging/" "$remote_path" --checksum; then
        log "Uploaded $site backup to $remote_path"
    else
        log "FAILED: rclone upload for $site"
        FAILED=1
    fi

    # Monthly keeper: the full set of the 1st of each month also goes to monthly/ (its own
    # R2 lifecycle rule keeps it ~a year; full/ itself is kept ~30 days).
    if [ "$MODE" = full ] && [ "$(date +%d)" = 01 ]; then
        rclone copy "$site_staging/" "$RCLONE_REMOTE/monthly/$DOMAIN_SUFFIX/$site/$TIMESTAMP/" --checksum \
            || { log "FAILED: monthly copy for $site"; FAILED=1; }
    fi

    sync_site_files "$site" || FAILED=1
done

# --- Control Plane database -----------------------------------------------------------
# Customers, subscriptions, payments, sites, API-key hashes, the audit log. Not a Frappe
# site, so the loop above never covered it: until 2026-09-25 it had NO backup at all
# (found while checking the disaster-recovery runbook). Small (~130 KB), so it goes out
# every run, hourly and full. Skipped only on a server that doesn't host a Control Plane.
CP_DB_CONTAINER="${CP_DB_CONTAINER:-royce-cp-db-1}"
if docker inspect "$CP_DB_CONTAINER" >/dev/null 2>&1; then
    log "--- control plane database ---"
    cp_staging="$STAGING_DIR/$MODE/_control-plane/$TIMESTAMP"
    mkdir -p "$cp_staging"
    cp_dump="$cp_staging/control-plane.dump"
    # Custom format (pg_restore), then read back its table of contents so a truncated or
    # empty dump fails here instead of being uploaded as if it were fine. grep -c, not
    # grep -q: -q exits at the first match, pg_restore then dies of SIGPIPE, and under
    # pipefail the check fails at random (it did, 2026-09-25 20:03).
    if docker exec "$CP_DB_CONTAINER" pg_dump -U royce -Fc royce_control_plane > "$cp_dump" \
        && [ "$(docker exec -i "$CP_DB_CONTAINER" pg_restore -l < "$cp_dump" | grep -c "TABLE DATA")" -gt 0 ]; then
        remote_path="$RCLONE_REMOTE/$MODE/$DOMAIN_SUFFIX/_control-plane/$TIMESTAMP/"
        if rclone copy "$cp_staging/" "$remote_path" --checksum; then
            log "Uploaded control plane database ($(stat -c %s "$cp_dump") bytes) to $remote_path"
        else
            log "FAILED: rclone upload for the control plane database"
            FAILED=1
        fi
    else
        log "FAILED: pg_dump of the control plane database"
        FAILED=1
    fi
else
    log "no Control Plane database container ($CP_DB_CONTAINER) on this server -- skipping"
fi

# Prune local staging older than retention -- the off-server copy is now the source
# of truth; this is disk hygiene on the workload server, not the actual backup.
# Off-server retention (how long R2 KEEPS each tier) is a separate concern, handled
# by R2 lifecycle rules, not this script -- see docs/operations/backups.md.
find "$STAGING_DIR/$MODE" -mindepth 2 -maxdepth 2 -type d -mtime "+$RETENTION_DAYS" -exec rm -rf {} + 2>/dev/null || true

if [ "$FAILED" -ne 0 ]; then
    log "One or more sites failed to back up -- see above"
    report_metric 0
    exit 1
fi
log "All sites backed up successfully"
report_metric 1
