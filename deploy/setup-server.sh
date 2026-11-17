#!/usr/bin/env bash
# Turns a fresh Ubuntu 24.04 VPS into a hospital server, the way the pilot server
# (royce-test, 80.241.222.38) was set up by hand on 2026-11-06/07:
#   admin user + key-only SSH, ufw (22 + 80/443, Cloudflare-only by default), fail2ban,
#   unattended security upgrades, swap, timezone, Docker CE, host nginx in front of the
#   ERPNext stack (which listens on 127.0.0.1:8080 only), Cloudflare Origin certificate.
#
#   sudo bash setup-server.sh /opt/royceerp/hospital.env
#
# Safe to re-run. It refuses to switch SSH passwords off unless the admin user has a key.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
ENV_FILE="${1:-/opt/royceerp/hospital.env}"
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE (copy hospital.env.example and fill it in)" >&2; exit 1; }
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${SITE:?}" "${ADMIN_USER:?}" "${ADMIN_SSH_PUBKEYS:?}" "${ORIGIN_CERT:?}" "${ORIGIN_KEY:?}"
TZ="${TZ:-Africa/Nairobi}"; SWAP_GB="${SWAP_GB:-4}"; CLOUDFLARE_ONLY="${CLOUDFLARE_ONLY:-1}"

log() { echo "[$(date +%H:%M:%S)] $*"; }

. /etc/os-release
[ "$ID" = ubuntu ] && [ "$VERSION_ID" = 24.04 ] || log "WARNING: tested on Ubuntu 24.04, this is $PRETTY_NAME"
[[ "$ADMIN_SSH_PUBKEYS" == *AAAA*replace* ]] && { echo "ADMIN_SSH_PUBKEYS is still the example" >&2; exit 1; }

log "timezone $TZ"
timedatectl set-timezone "$TZ"

log "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl gnupg git jq zstd unzip openssl ufw fail2ban unattended-upgrades nginx

if [ "$SWAP_GB" -gt 0 ] && ! swapon --show | grep -q .; then
    log "swap ${SWAP_GB}G"
    fallocate -l "${SWAP_GB}G" /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

log "admin user $ADMIN_USER"
id "$ADMIN_USER" >/dev/null 2>&1 || adduser --disabled-password --gecos "" "$ADMIN_USER"
usermod -aG sudo "$ADMIN_USER"
echo "$ADMIN_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$ADMIN_USER" && chmod 440 "/etc/sudoers.d/90-$ADMIN_USER"
home=$(getent passwd "$ADMIN_USER" | cut -d: -f6)
install -d -m 700 -o "$ADMIN_USER" -g "$ADMIN_USER" "$home/.ssh"
touch "$home/.ssh/authorized_keys"
while IFS= read -r key; do
    [ -n "$key" ] && ! grep -qxF "$key" "$home/.ssh/authorized_keys" && echo "$key" >> "$home/.ssh/authorized_keys"
done <<< "$ADMIN_SSH_PUBKEYS"
chown "$ADMIN_USER:$ADMIN_USER" "$home/.ssh/authorized_keys" && chmod 600 "$home/.ssh/authorized_keys"

log "ssh: key-only"
grep -q '^ssh-' "$home/.ssh/authorized_keys" || { echo "no key for $ADMIN_USER: not touching SSH" >&2; exit 1; }
cat > /etc/ssh/sshd_config.d/00-royce-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
MaxAuthTries 6
X11Forwarding no
EOF
# cloud-init often writes "PasswordAuthentication yes" in 50-cloud-init.conf; first match wins
# in sshd, and 00- sorts first, but flip it too so nobody is misled reading it.
sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config.d/*.conf 2>/dev/null || true
sshd -t && systemctl reload ssh

log "fail2ban"
cat > /etc/fail2ban/jail.local <<'EOF'
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
[sshd]
enabled = true
backend = systemd
EOF
systemctl enable --now fail2ban >/dev/null && systemctl restart fail2ban

log "unattended security upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

log "docker"
if ! command -v docker >/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -q
    apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "$ADMIN_USER"
# Rotate container logs (Docker keeps them forever by default).
if [ ! -f /etc/docker/daemon.json ]; then
    echo '{ "log-driver": "json-file", "log-opts": { "max-size": "50m", "max-file": "5" } }' > /etc/docker/daemon.json
    systemctl restart docker
fi

log "firewall"
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow 22/tcp comment ssh >/dev/null
if [ "$CLOUDFLARE_ONLY" = 1 ]; then
    ufw delete allow 80,443/tcp >/dev/null 2>&1 || true
    for net in $(curl -fsS https://www.cloudflare.com/ips-v4) $(curl -fsS https://www.cloudflare.com/ips-v6); do
        ufw allow proto tcp from "$net" to any port 80,443 comment cloudflare >/dev/null
    done
else
    ufw allow 80,443/tcp >/dev/null
fi
ufw --force enable >/dev/null

log "origin certificate"
install -d -m 700 /etc/ssl/royce
[ -f "$ORIGIN_CERT" ] && install -m 644 "$ORIGIN_CERT" /etc/ssl/royce/origin.pem
[ -f "$ORIGIN_KEY" ] && install -m 600 "$ORIGIN_KEY" /etc/ssl/royce/origin.key
[ -s /etc/ssl/royce/origin.pem ] && [ -s /etc/ssl/royce/origin.key ] \
    || { echo "origin certificate/key missing ($ORIGIN_CERT, $ORIGIN_KEY)" >&2; exit 1; }
[ "$(openssl x509 -noout -pubkey -in /etc/ssl/royce/origin.pem | openssl sha256)" = \
  "$(openssl pkey -pubout -in /etc/ssl/royce/origin.key | openssl sha256)" ] \
    || { echo "origin certificate and key don't match" >&2; exit 1; }

log "nginx"
rm -f /etc/nginx/sites-enabled/default
cat > /etc/nginx/sites-available/royceerp <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 301 https://\$host\$request_uri;
}
server {
    listen 443 ssl http2 default_server;
    listen [::]:443 ssl http2 default_server;
    server_name $SITE;
    ssl_certificate     /etc/ssl/royce/origin.pem;
    ssl_certificate_key /etc/ssl/royce/origin.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    client_max_body_size 50m;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 120s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/royceerp /etc/nginx/sites-enabled/royceerp
nginx -t && systemctl reload nginx

install -d -m 755 -o "$ADMIN_USER" -g "$ADMIN_USER" /opt/royceerp
chown root:root "$ENV_FILE" && chmod 600 "$ENV_FILE"

log "done. Next: get the image onto this server (ship-image.sh or build-image.sh), then start-stack.sh"
log "Check you can still log in as $ADMIN_USER in a NEW terminal before closing this one."
