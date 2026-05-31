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
