#!/usr/bin/env bash
set -euo pipefail

ROBOT_HOST="${ROBOT_HOST:-robot@10.169.113.176}"
ROBOT_WS="${ROBOT_WS:-/home/robot/colt-robot-ws}"
LOCAL_WS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Syncing ${LOCAL_WS}/ -> ${ROBOT_HOST}:${ROBOT_WS}/"

# 实测机不能访问 GitHub，所以这里把开发机工作空间作为唯一来源同步过去。
ssh "${ROBOT_HOST}" "sudo mkdir -p '${ROBOT_WS}' && sudo chown -R \$(id -un):\$(id -gn) '${ROBOT_WS}'"

rsync -av --delete \
  --exclude build/ \
  --exclude devel/ \
  --exclude install/ \
  --exclude log/ \
  --exclude .catkin_tools/ \
  --exclude .venv/ \
  --exclude .venv-py311/ \
  --exclude venv/ \
  --exclude env/ \
  --exclude .git/ \
  --exclude .vscode/ \
  --exclude __pycache__/ \
  --exclude '*.pyc' \
  --exclude '*.bag' \
  --exclude '*.db3' \
  --exclude '*.mcap' \
  --exclude '*.pt' \
  --exclude '*.pth' \
  --exclude '*.engine' \
  --exclude '*.weights' \
  --exclude '*.pcd' \
  --exclude '*.ply' \
  --exclude '*.npy' \
  --exclude '*.npz' \
  "${LOCAL_WS}/" "${ROBOT_HOST}:${ROBOT_WS}/"

echo "Done. Build on robot with:"
echo "  ssh ${ROBOT_HOST}"
echo "  cd ${ROBOT_WS} && catkin_make && source devel/setup.bash"
