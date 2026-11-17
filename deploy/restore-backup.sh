#!/usr/bin/env bash
# Restores a site from a bench backup set in a folder on THIS hospital server.
# Used by move-site.sh (pilot -> hospital server) and for restore drills.
#
#   sudo bash restore-backup.sh <folder> <site> [--as <other site name>] [--live]
#   sudo bash restore-backup.sh --check <site>
#
# <folder> holds one set: *-database.sql.gz, *-files.tar, *-private-files.tar,
# *-site_config_backup.json, and optionally common-mail.json (the source server's
# email settings, written by move-site.sh). --as restores under another name, for a
# drill that leaves the live site alone (drop it afterwards:
# bench drop-site <name> --db-root-password ... --no-backup).
#
# Without --live the copy is quiet: scheduler off and emails muted, so a rehearsal or
# drill never sends SMS reminders or emails alongside the real site. --live (the final
# move) switches the scheduler on.
#
# Keeps this server's database login; every other site setting (encryption_key above
# all: without it stored passwords can't be decrypted) comes from the backup.
# Refuses to overwrite a site that already exists.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
BACKEND="${BACKEND:-royceerp-backend-1}"
BENCH="/home/frappe/frappe-bench"
be()  { docker exec "$BACKEND" "$@"; }
bei() { docker exec -i "$BACKEND" "$@"; }

check_site() {
    echo "checks for $1: stored passwords decrypt; record counts; files on disk"
    bei bash -c "cd $BENCH/sites && $BENCH/env/bin/python - '$1'" <<'PY'
import os, sys, frappe
from frappe.utils.password import get_decrypted_password
frappe.init(site=sys.argv[1], sites_path=".")
frappe.connect()
try:
    rows = frappe.db.sql("select doctype, name, fieldname from `__Auth` where encrypted = 1", as_dict=True)
    bad = []
    for r in rows:
        try:
            get_decrypted_password(r.doctype, r.name, r.fieldname, raise_exception=True)
        except Exception as e:
            bad.append(f"{r.doctype}/{r.name}/{r.fieldname}: {type(e).__name__}")
    print(f"   encrypted passwords: {len(rows)}, {len(rows) - len(bad)} decrypt")
    for b in bad:
        print("   FAILED", b)
    names = ("User", "Company", "Patient", "Patient Encounter", "Healthcare Practitioner", "Item", "Item Price",
             "Sales Invoice", "Payment Entry", "GL Entry", "Stock Ledger Entry")
    counts = {d: frappe.db.count(d) for d in names if frappe.db.exists("DocType", d)}
    print("   records:", ", ".join(f"{k} {v}" for k, v in counts.items()))
    files = frappe.get_all("File", filters={"is_folder": 0, "file_url": ["like", "/%files/%"]}, fields=["name"])
    missing = [f.name for f in files if not os.path.exists(frappe.get_doc("File", f.name).get_full_path())]
    print(f"   uploaded files: {len(files)}, {len(files) - len(missing)} on disk")
    bad += missing
    sys.exit(1 if bad else 0)
finally:
    frappe.destroy()
PY
}

if [ "${1:-}" = --check ]; then check_site "${2:?site}"; exit; fi
SRC_DIR="${1:?usage: $0 <folder> <site> [--as <name>]}"
SITE="${2:?usage: $0 <folder> <site> [--as <name>]}"
TARGET="$SITE"; LIVE=0
shift 2
while [ $# -gt 0 ]; do
    case "$1" in
        --as)   TARGET="${2:?--as needs a site name}"; shift 2 ;;
        --live) LIVE=1; shift ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done
log() { echo "[$(date +%H:%M:%S)] [$TARGET] $*"; }

be test ! -d "$BENCH/sites/$TARGET" || { log "site already exists here: refusing"; exit 1; }
DB=; FILES=; PRIVATE=; CFG=
for f in "$SRC_DIR"/*; do
    case "$f" in
        # "-files.tar" is a substring of "-private-files.tar": match the longer one first.
        *-database.sql.gz)         DB=$(basename "$f") ;;
        *-private-files.tar)       PRIVATE=$(basename "$f") ;;
        *-files.tar)               FILES=$(basename "$f") ;;
        *-site_config_backup.json) CFG=$(basename "$f") ;;
    esac
done
[ -n "$DB" ] && [ -n "$FILES" ] && [ -n "$PRIVATE" ] && [ -n "$CFG" ] \
    || { log "incomplete backup set in $SRC_DIR (need database, files, private files, site config)"; exit 1; }
log "set: $DB"

IN="/home/frappe/restore/$TARGET"
be mkdir -p "$IN"
docker cp "$SRC_DIR/." "$BACKEND:$IN/"
docker exec -u root "$BACKEND" chown -R frappe /home/frappe/restore

ROOT_PW=$(sed -n 's/^DB_PASSWORD=//p' /opt/royceerp/royceerp.env)
log "creating the site"
be bench new-site "$TARGET" --mariadb-root-password "$ROOT_PW" \
    --admin-password "$(openssl rand -hex 16)" --mariadb-user-host-login-scope=% >/dev/null
log "restoring database and files"
be bench --site "$TARGET" restore "$IN/$DB" \
    --with-public-files "$IN/$FILES" --with-private-files "$IN/$PRIVATE" --db-root-password "$ROOT_PW"

log "site settings from the backup (keeping this server's database login)"
bei python3 - "$TARGET" "$IN/$CFG" <<'PY'
import json, os, sys
site, backup = sys.argv[1], sys.argv[2]
path = f"/home/frappe/frappe-bench/sites/{site}/site_config.json"
current, saved = json.load(open(path)), json.load(open(backup))
keep = {"db_name", "db_user", "db_password", "db_type", "db_host", "db_port"}
moved = sorted(k for k in saved if k not in keep)
current.update({k: saved[k] for k in moved})
with open(path + ".tmp", "w") as f:
    json.dump(current, f, indent=1, sort_keys=True)
os.replace(path + ".tmp", path)
print("   keys:", ", ".join(moved))
PY

if [ -f "$SRC_DIR/common-mail.json" ]; then
    log "email settings into common_site_config (the pilot keeps SMTP there)"
    bei python3 - "$IN/common-mail.json" <<'PY'
import json, os, sys
path = "/home/frappe/frappe-bench/sites/common_site_config.json"
current, mail = json.load(open(path)), json.load(open(sys.argv[1]))
current.update(mail)
with open(path + ".tmp", "w") as f:
    json.dump(current, f, indent=1, sort_keys=True)
os.replace(path + ".tmp", path)
print("   keys:", ", ".join(sorted(mail)))
PY
fi

log "migrating"
be bench --site "$TARGET" migrate >/dev/null
if [ "$LIVE" = 1 ]; then
    be bench --site "$TARGET" enable-scheduler
else
    be bench --site "$TARGET" disable-scheduler
    be bench --site "$TARGET" set-config -p mute_emails 1
    log "quiet copy: scheduler off, emails muted (--live for the real move)"
fi
be bench --site "$TARGET" clear-cache
# The only site on a hospital server answers for the bare IP too.
[ "$(be bash -c 'ls -d sites/*/site_config.json | wc -l')" = 1 ] && be bench use "$TARGET"
be rm -rf "$IN"
check_site "$TARGET"
log "done"
