#!/usr/bin/env bash
# Copies a built image from one server to another, through this machine, without a
# registry and without putting a GitHub token on the hospital's server. The hospital
# then runs exactly the image already tested on the pilot (same image ID).
#
#   bash ship-image.sh royce-test vilcom-bethesda 16-hke0.29.0
#
# Both arguments are ssh hosts this machine can reach (~/.ssh/config); the user on each
# needs sudo or the docker group. About 2 GB crosses this machine's connection twice
# (down from the source, up to the target), zstd-compressed.
set -euo pipefail
SRC="${1:?usage: $0 <source ssh host> <target ssh host> <tag>}"
DST="${2:?usage: $0 <source ssh host> <target ssh host> <tag>}"
TAG="${3:?usage: $0 <source ssh host> <target ssh host> <tag>}"
IMG="royceerp:$TAG"

src_id=$(ssh "$SRC" "sudo docker image inspect $IMG --format '{{.Id}}'") \
    || { echo "$IMG is not on $SRC" >&2; exit 1; }
ssh "$DST" "command -v zstd >/dev/null" || { echo "zstd missing on $DST (setup-server.sh installs it)" >&2; exit 1; }
echo "copying $IMG ($src_id) from $SRC to $DST ..."
start=$(date +%s)
ssh "$SRC" "sudo docker save $IMG | zstd -T0 -3 -q" | ssh "$DST" "zstd -d -q | sudo docker load"
dst_id=$(ssh "$DST" "sudo docker image inspect $IMG --format '{{.Id}}'")
[ "$src_id" = "$dst_id" ] || { echo "image ID differs on $DST: $dst_id" >&2; exit 1; }
echo "done in $(( $(date +%s) - start ))s; same image ID on both servers"
