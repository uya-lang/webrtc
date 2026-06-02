#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -x tests/aiortc_interop.py

venv_root="${TMPDIR:-/tmp}/webrtc-aiortc-venv"

if [[ ! -x "$venv_root/bin/python" ]]; then
    python3 -m venv "$venv_root"
fi

if ! "$venv_root/bin/python" - <<'PY'
try:
    import aiortc  # noqa: F401
    import av  # noqa: F401
except Exception:
    raise SystemExit(1)
PY
then
    "$venv_root/bin/python" -m pip install aiortc
fi

"$venv_root/bin/python" tests/aiortc_interop.py

echo "Phase 17 aiortc interop checks passed"
