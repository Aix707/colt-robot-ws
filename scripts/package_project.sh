#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT_DIR="$(dirname "${WS_ROOT}")"
WS_NAME="$(basename "${WS_ROOT}")"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT="${1:-${PARENT_DIR}/${WS_NAME}_runtime_${STAMP}.tar.gz}"
STAGE_DIR="$(mktemp -d /tmp/${WS_NAME}_package_XXXXXX)"

cleanup() {
  rm -rf "${STAGE_DIR}"
}

trap cleanup EXIT

mkdir -p "$(dirname "${OUTPUT}")"

rsync -a \
  --exclude=".git" \
  --exclude=".vscode" \
  --exclude=".venv" \
  --exclude=".venv-py311" \
  --exclude=".python311" \
  --exclude=".uv-cache" \
  --exclude="build" \
  --exclude="devel" \
  --exclude="install" \
  --exclude="log" \
  --exclude="__pycache__" \
  --exclude="*.bag" \
  --exclude="*.db3" \
  --exclude="*.mcap" \
  --exclude="*.pcd" \
  --exclude="*.ply" \
  --exclude="*.pt" \
  --exclude="*.pth" \
  --exclude="*.engine" \
  --exclude="*.weights" \
  "${WS_ROOT}/" "${STAGE_DIR}/${WS_NAME}/"

RUNTIME_SRC="${WS_ROOT}/src/colt/colt_bridle/models/runtime/current"
RUNTIME_DST="${STAGE_DIR}/${WS_NAME}/src/colt/colt_bridle/models/runtime/current"
if [[ -e "${RUNTIME_SRC}" ]]; then
  rm -rf "${RUNTIME_DST}"
  mkdir -p "$(dirname "${RUNTIME_DST}")"
  cp -aL "${RUNTIME_SRC}" "${RUNTIME_DST}"
fi

tar -C "${STAGE_DIR}" -czf "${OUTPUT}" "${WS_NAME}"

echo "Package created: ${OUTPUT}"
echo "Runtime current model is packaged as real files under src/colt/colt_bridle/models/runtime/current."
echo "Copy this file to the test machine, then extract it outside the project directory."
