#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <runtime_dir> [version]" >&2
  echo "Example: $0 /path/to/exports/colt_runtime_v002/runtime v002" >&2
  exit 2
fi

SOURCE_DIR="$(cd "$1" && pwd)"
VERSION="${2:-v002}"
WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_ROOT="${WS_ROOT}/src/colt/colt_bridle/models/runtime"
TARGET_DIR="${TARGET_ROOT}/${VERSION}"
LOADER="${WS_ROOT}/src/colt/colt_bridle/scripts/runtime_package_loader.py"

# 训练机导出的 runtime 包只保留在线推理需要的文件，不复制训练集和 PyTorch 权重。
mkdir -p "${TARGET_DIR}"
rsync -av --delete "${SOURCE_DIR}/" "${TARGET_DIR}/"

python3 "${LOADER}" --check "${TARGET_DIR}"

ln -sfnT "${VERSION}" "${TARGET_ROOT}/current"
echo "Installed runtime ${VERSION}: ${TARGET_DIR}"
echo "Updated current -> ${VERSION}"
