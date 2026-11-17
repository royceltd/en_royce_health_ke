#!/usr/bin/env bash
# Deploys a hospital release built by GitHub Actions (.github/workflows/hospital-image.yml):
# pulls the image from the registry, backs up every site, switches the stack, migrates,
# checks. Nothing is built on the server. Run on the server, as root:
#
#   bash deploy-release.sh 16-hke0.37.1 hospital.royceltd.com              # demo first
#   bash deploy-release.sh 16-hke0.37.1 bethesda.royceltd.com              # then the next
#   bash deploy-release.sh --rollback 16-hke0.37.0 hospital.royceltd.com   # previous image
#
# The server must be logged in to the registry once (a classic token with only
# read:packages): docker login ghcr.io -u <github user>
# The stack keeps its local image name (royceerp:<tag>), so compose files, start-stack.sh
# and ship-image.sh are unchanged. Every site on the server runs the same image: migrate
# each site named, and name the others as soon as they are checked.
set -euo pipefail
ROLLBACK=0
[ "${1:-}" = "--rollback" ] && { ROLLBACK=1; shift; }
TAG="${1:?usage: $0 [--rollback] <tag> <site> [site ...]}"
shift
SITES=("$@")
[ ${#SITES[@]} -gt 0 ] || { echo "name at least one site to migrate" >&2; exit 1; }
REGISTRY_IMAGE="${REGISTRY_IMAGE:-ghcr.io/royceltd/royceerp-health}"
DIR="${STACK_DIR:-/opt/royceerp}"
COMPOSE="docker compose -p royceerp -f compose.royceerp.yaml"
log() { echo "$(date '+%H:%M:%S') $*"; }
cd "$DIR"

old=$(sed -n 's/^ *image: royceerp:\(.*\)$/\1/p' compose.royceerp.yaml | head -1)
[ -n "$old" ] || { echo "no royceerp image in compose.royceerp.yaml" >&2; exit 1; }

if ! docker image inspect "royceerp:$TAG" >/dev/null 2>&1; then
	[ $ROLLBACK -eq 1 ] && { echo "royceerp:$TAG is not on this server" >&2; exit 1; }
	log "pulling $REGISTRY_IMAGE:$TAG"
	docker pull -q "$REGISTRY_IMAGE:$TAG"
	docker tag "$REGISTRY_IMAGE:$TAG" "royceerp:$TAG"
fi

for site in "${SITES[@]}"; do
	log "backup $site"
	docker exec royceerp-backend-1 bench --site "$site" backup >/dev/null
done

if [ "$old" != "$TAG" ]; then
	cp -p compose.royceerp.yaml "compose.royceerp.$old.yaml"
	sed -i "s/royceerp:$old/royceerp:$TAG/g" compose.royceerp.yaml
	[ -f royceerp.env ] && sed -i "s/^CUSTOM_TAG=.*/CUSTOM_TAG=$TAG/" royceerp.env
	log "switching royceerp:$old -> royceerp:$TAG"
	$COMPOSE up -d >/dev/null 2>&1
	for _ in $(seq 1 30); do
		docker exec royceerp-backend-1 bench --version >/dev/null 2>&1 && break
		sleep 5
	done
fi

status=0
for site in "${SITES[@]}"; do
	log "migrate $site"
	if docker exec royceerp-backend-1 bench --site "$site" migrate >"migrate-$TAG-$site.log" 2>&1; then
		ping=$(curl -fsS "https://$site/api/method/ping" || true)
		log "$site migrated, ping: $ping"
	else
		status=1
		log "MIGRATE FAILED on $site (migrate-$TAG-$site.log); roll back with:"
		log "  bash $0 --rollback $old $site   (and restore the backup just taken if the data changed)"
		tail -5 "migrate-$TAG-$site.log"
	fi
done

# Keep the running image and two before it; older ones go (each is about 6 GB).
docker images royceerp --format '{{.CreatedAt}}	{{.Tag}}' | sort -r | awk -F'\t' 'NR>3 {print $2}' \
	| while read -r t; do [ "$t" != "$TAG" ] && docker rmi -f "royceerp:$t" "$REGISTRY_IMAGE:$t" >/dev/null 2>&1 || true; done
docker image prune -f >/dev/null
exit $status
