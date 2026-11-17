#!/usr/bin/env bash
# Moves a site from one server's royceerp stack to another's, through this machine.
#
#   bash move-site.sh royce-test vilcom-bethesda bethesda.royceltd.com            # rehearsal
#   bash move-site.sh --final royce-test vilcom-bethesda bethesda.royceltd.com    # the real move
#
# Rehearsal: takes a fresh backup on the source and restores it on the target as a
# quiet copy (scheduler off, emails muted); the source keeps running. Run it as often as you like: drop the target's copy first
# (the restore refuses to overwrite an existing site).
#
# --final: first puts the source site in maintenance mode and stops its scheduler, so
# nothing is written there after the backup, and the copy goes live (scheduler on).
# Then switch DNS to the target. The source
# stays frozen as the fallback; undo with set-maintenance-mode off + enable-scheduler.
#
# AS=<other name> restores under another site name (a drill on a server that already
# has the site, e.g. source and target the same server); drop it afterwards.
#
# Both hosts: ssh hosts this machine can reach, with sudo. The target needs
# setup-server.sh and start-stack.sh done. Also copies the source's email (SMTP)
# settings, which the pilot keeps in common_site_config.json, not in the site.
set -euo pipefail
FINAL=0
if [ "${1:-}" = --final ]; then FINAL=1; shift; fi
SRC="${1:?usage: $0 [--final] <source ssh host> <target ssh host> <site>}"
DST="${2:?}"; SITE="${3:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"
BE=royceerp-backend-1
TS=$(date +%Y%m%d-%H%M%S)
IN="/home/frappe/move-$TS"
DIR="/opt/royceerp/restore/$SITE-$TS"
TARGET="${AS:-$SITE}"
AS_ARGS=""; [ -n "${AS:-}" ] && AS_ARGS="--as $AS"
[ "$FINAL" = 1 ] && AS_ARGS="$AS_ARGS --live"
log() { echo "[$(date +%H:%M:%S)] $*"; }

ssh "$DST" "sudo docker exec $BE test ! -d sites/$TARGET" \
    || { echo "$TARGET already exists on $DST: drop it first if this is another rehearsal" >&2; exit 1; }

if [ "$FINAL" = 1 ]; then
    log "freezing $SITE on $SRC (maintenance mode, scheduler off)"
    ssh "$SRC" "sudo docker exec $BE bench --site $SITE set-maintenance-mode on && sudo docker exec $BE bench --site $SITE disable-scheduler"
    sleep 20   # let running requests and jobs finish
fi

log "backup on $SRC"
ssh "$SRC" "sudo docker exec $BE bench --site $SITE backup --with-files --backup-path $IN >/dev/null"
ssh "$SRC" "sudo docker exec $BE python3 -c '
import json
c = json.load(open(\"sites/common_site_config.json\"))
keys = [k for k in c if k.startswith(\"mail_\") or k in (\"use_tls\", \"use_ssl\", \"auto_email_id\", \"email_sender_name\", \"always_use_account_email_id_as_sender\")]
json.dump({k: c[k] for k in keys}, open(\"$IN/common-mail.json\", \"w\"))
'"
ssh "$SRC" "sudo docker exec $BE ls -la $IN"

log "copying to $DST:$DIR"
ssh "$SRC" "sudo docker exec $BE tar -C $IN -cf - ." | ssh "$DST" "sudo install -d -m 700 $DIR && sudo tar -C $DIR -xf -"
ssh "$SRC" "sudo docker exec $BE rm -rf $IN"
ssh "$DST" "sudo install -d -m 755 /opt/royceerp/kit && sudo tee /opt/royceerp/kit/restore-backup.sh >/dev/null" < "$HERE/restore-backup.sh"

log "restoring on $DST"
ssh "$DST" "sudo bash /opt/royceerp/kit/restore-backup.sh $DIR $SITE $AS_ARGS && sudo rm -rf $DIR"

log "source counts, to compare with the checks above:"
ssh "$SRC" "sudo docker exec -i $BE bash -c 'cd sites && ../env/bin/python -'" <<PY
import frappe
frappe.init(site="$SITE", sites_path=".")
frappe.connect()
names = ("User", "Company", "Patient", "Patient Encounter", "Healthcare Practitioner", "Item", "Item Price",
         "Sales Invoice", "Payment Entry", "GL Entry", "Stock Ledger Entry")
print("   records:", ", ".join(f"{d} {frappe.db.count(d)}" for d in names if frappe.db.exists("DocType", d)))
frappe.destroy()
PY

if [ "$FINAL" = 1 ]; then
    log "NEXT: point the DNS record for $SITE at $DST's address (Cloudflare, proxied), then log in and check."
    log "The source stays frozen. Fallback: DNS back + on $SRC: bench --site $SITE set-maintenance-mode off; enable-scheduler"
else
    log "rehearsal done; the source is untouched. Test through an ssh tunnel (see README)."
fi
