#!/usr/bin/env bash
set -euo pipefail

WS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${WS_ROOT}/.venv-py311"
PYTHON_INSTALL_DIR="${WS_ROOT}/.python311"
TARGET_PYTHON="${TARGET_PYTHON:-3.11}"
PIP_TUNA="${PIP_TUNA:-https://pypi.tuna.tsinghua.edu.cn/simple}"
TORCH_CPU_INDEX="${TORCH_CPU_INDEX:-https://download.pytorch.org/whl/cpu}"
PYTHON_MIRROR="${PYTHON_MIRROR:-https://mirrors.tuna.tsinghua.edu.cn/github-release/astral-sh/python-build-standalone}"
UV_CACHE_DIR="${UV_CACHE_DIR:-${WS_ROOT}/.uv-cache}"
UV_BIN=""
PYTHON_BIN=""

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
    return
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found, cannot bootstrap uv." >&2
    exit 1
  fi

  if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "python3 -m pip not available." >&2
    echo "Install pip first, for example:" >&2
    echo "  sudo apt-get install -y python3-pip" >&2
    exit 1
  fi

  python3 -m pip install --user -i "${PIP_TUNA}" uv
  UV_BIN="${HOME}/.local/bin/uv"
  if [[ ! -x "${UV_BIN}" ]]; then
    echo "uv install failed: ${UV_BIN} not found" >&2
    exit 1
  fi
}

install_python() {
  ensure_uv
  mkdir -p "${PYTHON_INSTALL_DIR}"
  "${UV_BIN}" python install \
    --mirror "${PYTHON_MIRROR}" \
    --install-dir "${PYTHON_INSTALL_DIR}" \
    "${TARGET_PYTHON}"
  PYTHON_BIN="$(find "${PYTHON_INSTALL_DIR}" -path "*/bin/python${TARGET_PYTHON}" | sort | tail -n 1)"
  if [[ -z "${PYTHON_BIN}" || ! -x "${PYTHON_BIN}" ]]; then
    echo "python${TARGET_PYTHON} install failed under ${PYTHON_INSTALL_DIR}" >&2
    exit 1
  fi
}

create_venv() {
  install_python
  "${PYTHON_BIN}" -m venv --clear "${VENV_DIR}"
}

create_venv

"${VENV_DIR}/bin/python" -m pip install --upgrade \
  -i "${PIP_TUNA}" \
  pip setuptools wheel

"${VENV_DIR}/bin/python" -m pip install \
  -i "${PIP_TUNA}" \
  --extra-index-url "${TORCH_CPU_INDEX}" \
  torch torchvision

"${VENV_DIR}/bin/python" -m pip install \
  -i "${PIP_TUNA}" \
  onnxruntime \
  opencv-python \
  ultralytics \
  supervision \
  simple-pid \
  pyyaml \
  rospkg \
  catkin_pkg

PYTHON_VERSION="$("${VENV_DIR}/bin/python" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
echo "Python 3.11 install dir: ${PYTHON_INSTALL_DIR}"
echo "Python environment is ready: ${VENV_DIR}"
echo "Python version: ${PYTHON_VERSION}"
echo "Next: run scripts/run_project.sh"
