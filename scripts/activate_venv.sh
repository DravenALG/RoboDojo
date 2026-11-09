#!/usr/bin/env bash
# Source this file from any directory to activate the local simulator environment.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "Usage: source scripts/activate_venv.sh" >&2
  exit 2
fi

_robodojo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${_robodojo_root}/.venv/bin/activate"
export PYTHONNOUSERSITE=1
export PIP_USER=0
export OMNI_KIT_ACCEPT_EULA=YES
export PYTHONPATH="${_robodojo_root}:${_robodojo_root}/XPolicyLab${PYTHONPATH:+:${PYTHONPATH}}"

# Conda's base EGL override can hide the host's NVIDIA graphics driver.
unset __EGL_VENDOR_LIBRARY_DIRS __EGL_VENDOR_LIBRARY_FILENAMES
if [[ -f /etc/vulkan/icd.d/nvidia_icd.json ]]; then
  export VK_ICD_FILENAMES=/etc/vulkan/icd.d/nvidia_icd.json
  export VK_DRIVER_FILES="${VK_ICD_FILENAMES}"
fi
unset _robodojo_root
