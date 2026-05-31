#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_crypto_test_main.uya
test -d src/webrtc/crypto
test -f src/webrtc/crypto/aes.uya
test -f src/webrtc/crypto/gcm.uya
test -f src/webrtc/crypto/ghash.uya
test -f src/webrtc/crypto/hash.uya
test -f src/webrtc/crypto/hmac.uya
test -f src/webrtc/crypto/kdf.uya
test -f src/webrtc/crypto/random.uya
test -d tests/fixtures/crypto
test -f tests/fixtures/crypto/README.md
test -f tests/fixtures/crypto/sha1_vectors.json
test -f tests/fixtures/crypto/sha256_vectors.json
test -f tests/fixtures/crypto/hmac_sha1_vectors.json
test -f tests/fixtures/crypto/hmac_sha256_vectors.json
test -f tests/fixtures/crypto/wycheproof_like_hmac_sha1.json
test -f tests/fixtures/crypto/wycheproof_like_hmac_sha256.json
test -x tests/crypto_vectors.py

rg -Fq "crypto_test_check_constant_time_compare_edges" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_random_source_failure_paths" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_sha1_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_sha256_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_hmac_sha1_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_hmac_sha256_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_aes_ctr_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_aes_gcm_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_ghash_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_hkdf_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "crypto_test_check_tls12_prf_vectors" src/webrtc_crypto_test_main.uya
rg -Fq "export fn crypto_aes_key_schedule_init" src/webrtc/crypto/aes.uya
rg -Fq "export fn crypto_aes_ctr_xor" src/webrtc/crypto/aes.uya
rg -Fq "export fn crypto_aes_gcm_encrypt" src/webrtc/crypto/gcm.uya
rg -Fq "export fn crypto_aes_gcm_decrypt_and_verify" src/webrtc/crypto/gcm.uya
rg -Fq "export fn crypto_ghash_multiply" src/webrtc/crypto/ghash.uya
rg -Fq "export fn crypto_ghash_digest" src/webrtc/crypto/ghash.uya
rg -Fq "export fn crypto_sha1_digest" src/webrtc/crypto/hash.uya
rg -Fq "export fn crypto_sha256_digest" src/webrtc/crypto/hash.uya
rg -Fq "export fn crypto_hmac_sha1_digest" src/webrtc/crypto/hmac.uya
rg -Fq "export fn crypto_hmac_sha256_digest" src/webrtc/crypto/hmac.uya
rg -Fq "export fn crypto_hkdf_extract_sha256" src/webrtc/crypto/kdf.uya
rg -Fq "export fn crypto_hkdf_expand_sha256" src/webrtc/crypto/kdf.uya
rg -Fq "export fn crypto_tls12_prf_sha256" src/webrtc/crypto/kdf.uya
rg -Fq "export fn crypto_random_fill" src/webrtc/crypto/random.uya
rg -Fq "export fn crypto_random_test_set_fail_open" src/webrtc/crypto/random.uya
rg -Fq "export fn crypto_random_test_set_fail_read" src/webrtc/crypto/random.uya

python3 tests/crypto_vectors.py
../uya/bin/uya run src/webrtc_crypto_test_main.uya
