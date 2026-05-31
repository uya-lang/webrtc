#!/usr/bin/env bash
set -euo pipefail

out_file="${1:-build/benchmarks/baseline.jsonl}"
mkdir -p "$(dirname "$out_file")"

cat > "$out_file" <<'EOF'
{"name":"placeholder","suite":"phase0","unit":"ns/op","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_arena_ring","suite":"phase1","unit":"ns/op","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_udp_echo","suite":"phase2","unit":"qps","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_sdp_parse","suite":"phase3","unit":"ns/op","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_stun_parse","suite":"phase4","unit":"ns/packet","value":0,"allocations":0,"high_watermark":0}
EOF

tmp_crypto_out="$(mktemp)"
trap 'rm -f "$tmp_crypto_out"' EXIT
../uya/bin/uya run src/webrtc_crypto_bench_main.uya > "$tmp_crypto_out"
rg '^\{' "$tmp_crypto_out" >> "$out_file"
