#!/usr/bin/env bash
# Starts (or upgrades) the ERPNext stack on a hospital server: the pilot's layout,
#   /opt/royceerp/frappe_docker        frappe_docker at a pinned commit
#   /opt/royceerp/royceerp.env         stack settings + DB root password (600)
#   /opt/royceerp/compose.royceerp.yaml  resolved compose file (600; holds the password)
#   docker compose project "royceerp", volumes royceerp_sites / royceerp_db-data
# MariaDB 11.8 and Redis inside the stack; the frontend listens on 127.0.0.1:8080 only,
# behind the host nginx from setup-server.sh.
#
#   sudo bash start-stack.sh /opt/royceerp/hospital.env
#
# Upgrade: put the new image on the server, change IMAGE_TAG in hospital.env, take a
# backup (sudo systemctl start royce-backup@full), run this again, then
# `bench --site <site> migrate` (the script prints the command). The previous resolved
# compose file is kept as compose.royceerp.<old tag>.yaml for rollback.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
ENV_FILE="${1:-/opt/royceerp/hospital.env}"
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${IMAGE_TAG:?}" "${FRAPPE_DOCKER_COMMIT:?}" "${SITE:?}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-5}"; GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
ROOT=/opt/royceerp
P=(docker compose --project-name royceerp)
log() { echo "[$(date +%H:%M:%S)] $*"; }

docker image inspect "royceerp:$IMAGE_TAG" >/dev/null 2>&1 \
    || { echo "image royceerp:$IMAGE_TAG is not on this server (ship-image.sh)" >&2; exit 1; }

cd "$ROOT"
if [ ! -d frappe_docker ]; then
    log "frappe_docker @ $FRAPPE_DOCKER_COMMIT"
    git clone -q https://github.com/frappe/frappe_docker.git frappe_docker
fi
git -C frappe_docker -c advice.detachedHead=false checkout -q "$FRAPPE_DOCKER_COMMIT"

# The database root password is made once and never changed by this script.
DB_PASSWORD=$(sed -n 's/^DB_PASSWORD=//p' royceerp.env 2>/dev/null || true)
[ -n "$DB_PASSWORD" ] || { DB_PASSWORD=$(openssl rand -hex 16); log "new database root password (in royceerp.env)"; }
umask 077
cat > royceerp.env <<EOF
CUSTOM_IMAGE=royceerp
CUSTOM_TAG=$IMAGE_TAG
PULL_POLICY=never
DB_PASSWORD=$DB_PASSWORD
DB_HOST=db
DB_PORT=3306
REDIS_CACHE=redis-cache:6379
REDIS_QUEUE=redis-queue:6379
HTTP_PUBLISH_PORT=127.0.0.1:8080
FRAPPE_SITE_NAME_HEADER=\$\$host
UPSTREAM_REAL_IP_ADDRESS=172.16.0.0/12
UPSTREAM_REAL_IP_HEADER=X-Forwarded-For
CLIENT_MAX_BODY_SIZE=50m
GUNICORN_WORKERS=$GUNICORN_WORKERS
GUNICORN_THREADS=$GUNICORN_THREADS
GUNICORN_TIMEOUT=120
EOF

# Keep the running compose file for rollback before replacing it.
if [ -f compose.royceerp.yaml ]; then
    old=$(sed -n 's/^ *image: royceerp:\(.*\)$/\1/p' compose.royceerp.yaml | head -1)
    [ -n "$old" ] && [ "$old" != "$IMAGE_TAG" ] && cp -p compose.royceerp.yaml "compose.royceerp.$old.yaml" \
        && log "kept compose.royceerp.$old.yaml for rollback"
fi
(cd frappe_docker && docker compose --project-name royceerp --env-file ../royceerp.env \
    -f compose.yaml -f overrides/compose.mariadb.yaml -f overrides/compose.redis.yaml \
    -f overrides/compose.noproxy.yaml config) > compose.royceerp.yaml.new
mv compose.royceerp.yaml.new compose.royceerp.yaml
umask 022

log "starting royceerp:$IMAGE_TAG"
"${P[@]}" -f compose.royceerp.yaml up -d --remove-orphans
for _ in $(seq 1 60); do
    curl -fsS -o /dev/null http://127.0.0.1:8080/api/method/ping -H "Host: $SITE" 2>/dev/null && break
    sleep 3
done
"${P[@]}" -f compose.royceerp.yaml ps --format 'table {{.Service}}\t{{.Status}}'

if "${P[@]}" -f compose.royceerp.yaml exec -T backend test -f "sites/$SITE/site_config.json"; then
    log "site $SITE is here. After an image change run:"
    echo "  sudo docker compose -p royceerp -f $ROOT/compose.royceerp.yaml exec backend bench --site $SITE migrate"
else
    log "stack up, no site yet. Next: move-site.sh (from the pilot) or bench new-site"
fi
