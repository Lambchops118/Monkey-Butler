#!/usr/bin/env bash
# Start the whole Butler stack from one place (Linux/macOS twin of butler.cmd).
#
#   ./butler.sh            open the launcher GUI
#   ./butler.sh --no-gui   start everything headless in this terminal
#
# Arguments pass through to `python -m butler.launcher`.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Platform-specific settings (device names etc.) live in butler/config.
# faster-whisper (CTranslate2) loads cuBLAS/cuDNN from the venv's pip wheels.
for lib in "$SCRIPT_DIR"/.venv-runtime/lib/python3.*/site-packages/nvidia/{cublas,cudnn}/lib; do
    [[ -d "$lib" ]] && LD_LIBRARY_PATH="$lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
done
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}"

for py in .venv-runtime/bin/python .venv/bin/python; do
    if [[ -x "$py" ]]; then
        exec "$py" -m butler.launcher "$@"
    fi
done

if command -v python3 >/dev/null 2>&1; then
    exec python3 -m butler.launcher "$@"
fi

echo "No Python interpreter found (.venv-runtime missing and 'python3' not on PATH)." >&2
exit 1
