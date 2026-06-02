#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f tests/browser_datachannel_interop.py
test -f tests/fixtures/dtls/browser_handshake.json
test -d tests/fixtures/dtls

venv_root="${TMPDIR:-/tmp}/webrtc-playwright-firefox-venv"
browser_root="${HOME}/.cache/ms-playwright"

if [[ ! -x "$venv_root/bin/python" ]]; then
    python3 -m venv "$venv_root"
fi

if ! "$venv_root/bin/python" - <<'PY'
try:
    import playwright  # noqa: F401
except Exception:
    raise SystemExit(1)
PY
then
    "$venv_root/bin/python" -m pip install playwright
fi

if ! find "$browser_root" -type f -path '*/firefox/firefox' -perm -111 | grep -q .; then
    "$venv_root/bin/python" -m playwright install firefox
fi

"$venv_root/bin/python" tests/browser_datachannel_interop.py firefox audio
"$venv_root/bin/python" tests/browser_datachannel_interop.py firefox video

echo "Phase 17 browser Firefox audio/video interop checks passed"
