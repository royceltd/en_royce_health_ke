#!/usr/bin/env bash
# Builds the hospital image on THIS server (the pilot's build.sh, same app list).
# Prefer ship-image.sh for a hospital: it copies the image already tested on the pilot,
# and no GitHub token ever touches the hospital's server. Use this only when the pilot
# can't be reached. Every app is pinned to a tag in apps.health.json (the hospital release
# manifest), so a build here has the same code as the pilot's image of the same release.
#
#   sudo bash build-image.sh /opt/royceerp/hospital.env
#
# Asks for a fine-grained, read-only GitHub token (royceltd repos). The token exists
# only in memory and in a temporary apps.json that is deleted when the build ends.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1090
source "${1:-/opt/royceerp/hospital.env}"
: "${IMAGE_TAG:?}" "${FRAPPE_DOCKER_COMMIT:?}" "${FRAPPE_BRANCH:?}"
cd /opt/royceerp
[ -d frappe_docker ] || git clone -q https://github.com/frappe/frappe_docker.git frappe_docker
git -C frappe_docker -c advice.detachedHead=false checkout -q "$FRAPPE_DOCKER_COMMIT"
read -rsp "GitHub token (read-only, royceltd repos): " TOKEN; echo
APPS=$(mktemp /dev/shm/apps.XXXXXX.json)
trap 'rm -f "$APPS"' EXIT
sed "s/TOKEN/$TOKEN/" "$HERE/apps.health.json" > "$APPS"
unset TOKEN
cd frappe_docker
docker build \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH="$FRAPPE_BRANCH" \
  --build-arg=CACHE_BUST="$(date +%s)" \
  --secret=id=apps_json,src="$APPS" \
  --tag="royceerp:$IMAGE_TAG" \
  --file=images/layered/Containerfile . 2>&1 | tee "/opt/royceerp/build-$IMAGE_TAG.log"
echo "BUILD_DONE royceerp:$IMAGE_TAG"
