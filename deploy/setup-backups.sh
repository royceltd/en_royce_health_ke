#!/usr/bin/env bash
# Off-server, encrypted backups for a hospital server, using the platform's own backup
# script (backup-to-object-storage.sh, next to this one) unchanged,
# pointed at the hospital stack (compose project "royceerp", volume royceerp_sites):
#   hourly  database dump of every site + incremental file mirror
#   daily   00:30 full set (database + files tars); on the 1st also kept in monthly/
# Encrypted on this server before upload (rclone crypt), so the bucket holds nothing
# readable. Also works on the pilot server (same stack layout).
#
#   sudo bash setup-backups.sh /opt/royceerp/hospital.env
#
# Before running: create the hospital's own R2 bucket and an R2 API token with
# Object Read & Write on that bucket only (Cloudflare > R2 > Manage API tokens). The
# script asks for the endpoint, key ID and secret the first time, and makes the
# encryption keys itself. AFTERWARDS: save /opt/royce/backup-home/.config/rclone/rclone.conf
# in the password manager. Lose it and every backup is unreadable.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1090
source "${1:-/opt/royceerp/hospital.env}"
: "${R2_BUCKET:?}" "${BACKUP_DOMAIN:?}"
RCLONE_REMOTE="${RCLONE_REMOTE:-r2-crypt:crypt}"
RCLONE_VERSION=1.75.1
RCLONE_SHA256=982b5aa772841168f8e380f139e9e787b2a105403e32b94da8676a0e1c0a13ab
RCLONE_IMAGE=rclone/rclone@sha256:45401ad7410db1d67ffdb58e19059ad20b0d8e0285a60e38bbec55cc1019c7a5
HOME_DIR=/opt/royce/backup-home
CONF="$HOME_DIR/.config/rclone/rclone.conf"
log() { echo "[$(date +%H:%M:%S)] $*"; }

if ! /usr/local/bin/rclone version 2>/dev/null | head -1 | grep -qx "rclone v$RCLONE_VERSION"; then
    log "rclone $RCLONE_VERSION (official release; Ubuntu's 1.60 logs false errors against R2)"
    tmp=$(mktemp -d)
    curl -fsSL -o "$tmp/r.zip" "https://downloads.rclone.org/v$RCLONE_VERSION/rclone-v$RCLONE_VERSION-linux-amd64.zip"
    echo "$RCLONE_SHA256  $tmp/r.zip" | sha256sum -c --quiet
    unzip -q "$tmp/r.zip" -d "$tmp"
    install -m 755 "$tmp/rclone-v$RCLONE_VERSION-linux-amd64/rclone" /usr/local/bin/rclone
    rm -rf "$tmp"
fi
apt-get remove -yq rclone >/dev/null 2>&1 || true

log "service account royce-backup"
id royce-backup >/dev/null 2>&1 || useradd --system --shell /usr/sbin/nologin --home-dir "$HOME_DIR" --no-create-home royce-backup
usermod -aG docker royce-backup
install -d -o royce-backup -g royce-backup -m 700 "$HOME_DIR" "$HOME_DIR/.config" "$HOME_DIR/.config/rclone"
install -d -o royce-backup -g royce-backup -m 750 /opt/royce/backup-staging /opt/royce/backup-metrics

if [ ! -s "$CONF" ]; then
    log "R2 credentials for bucket $R2_BUCKET (input hidden where secret)"
    read -rp  "R2 endpoint (https://<account-id>.r2.cloudflarestorage.com): " R2_ENDPOINT
    read -rp  "R2 access key ID: " R2_KEY
    read -rsp "R2 secret access key: " R2_SECRET; echo
    rc() { sudo -u royce-backup HOME="$HOME_DIR" /usr/local/bin/rclone --config "$CONF" "$@"; }
    rc config create r2 s3 provider=Cloudflare access_key_id="$R2_KEY" secret_access_key="$R2_SECRET" \
        endpoint="$R2_ENDPOINT" acl=private no_check_bucket=true >/dev/null
    rc config create r2-crypt crypt remote="r2:$R2_BUCKET" filename_encryption=off directory_name_encryption=false \
        password="$(openssl rand -base64 32)" password2="$(openssl rand -base64 32)" >/dev/null
    unset R2_SECRET
    chmod 600 "$CONF"
    log "IMPORTANT: save $CONF in the password manager now (sudo cat it). Without it the backups can't be read."
fi
sudo -u royce-backup HOME="$HOME_DIR" /usr/local/bin/rclone --config "$CONF" lsf "r2:$R2_BUCKET" --max-depth 1 >/dev/null \
    || { echo "cannot reach bucket $R2_BUCKET with these credentials" >&2; exit 1; }

log "backup script and units"
install -o royce-backup -m 750 "$HERE/backup-to-object-storage.sh" /opt/royce/backup-to-object-storage.sh
docker pull -q "$RCLONE_IMAGE" >/dev/null

ONFAIL=
if [ -n "${ALERT_WEBHOOK:-}" ]; then
    printf 'ALERT_WEBHOOK=%s\nHOSPITAL=%s\n' "$ALERT_WEBHOOK" "${HOSPITAL:-$(hostname)}" > /etc/royce-backup-alert.env
    chmod 600 /etc/royce-backup-alert.env
    cat > /opt/royce/backup-alert.sh <<'EOF'
#!/bin/bash
# $1 = the failed unit. Posts one line to the webhook (Slack-compatible JSON).
msg=":warning: $HOSPITAL: $1 failed on $(hostname). Check: journalctl -u $1"
curl -fsS -m 20 -H "Content-Type: application/json" -d "{\"text\": \"$msg\"}" "$ALERT_WEBHOOK"
EOF
    chmod 755 /opt/royce/backup-alert.sh
    cat > /etc/systemd/system/royce-backup-alert@.service <<'EOF'
[Unit]
Description=Post a failed backup to the alert webhook

[Service]
Type=oneshot
EnvironmentFile=/etc/royce-backup-alert.env
ExecStart=/opt/royce/backup-alert.sh %i
EOF
    ONFAIL="OnFailure=royce-backup-alert@%n.service"
fi

cat > /etc/systemd/system/royce-backup@.service <<EOF
[Unit]
Description=Hospital %i backup of every site to off-server object storage
After=docker.service
Requires=docker.service
$ONFAIL

[Service]
Type=oneshot
Environment=COMPOSE_PROJECT=royceerp
Environment=SITES_VOLUME=royceerp_sites
Environment=RCLONE_REMOTE=$RCLONE_REMOTE
Environment=DOMAIN_SUFFIX=$BACKUP_DOMAIN
Environment=STAGING_DIR=/opt/royce/backup-staging
Environment=RETENTION_DAYS=3
Environment=TEXTFILE_DIR=/opt/royce/backup-metrics
Environment=RCLONE_IMAGE=$RCLONE_IMAGE
Environment=RCLONE_CONFIG_DIR=$HOME_DIR/.config/rclone
Environment=CP_DB_CONTAINER=none
ExecStart=/bin/bash /opt/royce/backup-to-object-storage.sh %i
User=royce-backup
EOF
cat > /etc/systemd/system/royce-backup-hourly.timer <<'EOF'
[Unit]
Description=Hourly hospital backup (database dump + incremental file mirror)

[Timer]
Unit=royce-backup@hourly.service
OnCalendar=hourly
RandomizedDelaySec=300
Persistent=true

[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/royce-backup-full.timer <<'EOF'
[Unit]
Description=Daily hospital full backup (database + files snapshot)

[Timer]
Unit=royce-backup@full.service
OnCalendar=*-*-* 00:30:00
RandomizedDelaySec=600
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now royce-backup-hourly.timer royce-backup-full.timer >/dev/null

log "first full backup now (a few minutes)"
systemctl start royce-backup@full.service || { journalctl -u royce-backup@full -n 40 --no-pager; exit 1; }
journalctl -u royce-backup@full -n 15 --no-pager -o cat
sudo -u royce-backup HOME="$HOME_DIR" /usr/local/bin/rclone --config "$CONF" lsf -R "${RCLONE_REMOTE}/full/$BACKUP_DOMAIN/" --max-depth 3 | tail -8
systemctl list-timers 'royce-backup*' --no-pager
log "done. Set the bucket's lifecycle rules by hand (README) and do a restore drill this week."
