#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -d tests/fixtures/crypto
test -f tests/fixtures/crypto/README.md
test -f tests/fixtures/crypto/sha1_vectors.json
test -f tests/fixtures/crypto/sha256_vectors.json
test -f tests/fixtures/crypto/hmac_sha1_vectors.json
test -f tests/fixtures/crypto/hmac_sha256_vectors.json
test -f tests/fixtures/crypto/wycheproof_like_hmac_sha1.json
test -f tests/fixtures/crypto/wycheproof_like_hmac_sha256.json
test -x tests/crypto_vectors.py

python3 tests/crypto_vectors.py
