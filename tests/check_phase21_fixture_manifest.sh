#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

manifest="tests/fixtures/codec_bridge_manifest.json"
test -f "$manifest"

python3 - "$manifest" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1])
data = json.loads(manifest_path.read_text(encoding="utf-8"))
if data.get("schema_version") != 1:
    raise SystemExit("unexpected schema_version")

entries = data.get("entries")
if not isinstance(entries, list) or len(entries) < 6:
    raise SystemExit("manifest needs at least six entries")

seen_ids = set()
required = {"id", "path", "source", "sha256", "license", "phase"}
for entry in entries:
    missing = required.difference(entry)
    if missing:
        raise SystemExit(f"entry missing fields: {sorted(missing)}")
    entry_id = entry["id"]
    if entry_id in seen_ids:
        raise SystemExit(f"duplicate id: {entry_id}")
    seen_ids.add(entry_id)
    for field in ("source", "license", "phase"):
        if not isinstance(entry[field], str) or not entry[field].strip():
            raise SystemExit(f"{entry_id} has empty {field}")
    if len(entry["sha256"]) != 64:
        raise SystemExit(f"{entry_id} has invalid sha256 length")
    path = pathlib.Path(entry["path"])
    if not path.is_file():
        raise SystemExit(f"{entry_id} missing file: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        raise SystemExit(f"{entry_id} sha256 mismatch: {digest}")

print(f"validated {len(entries)} codec bridge manifest entries")
PY
