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

append_crypto_fallback_rows() {
    cat >> "$out_file" <<'EOF'
{"name":"bench_hmac_sha1","suite":"phase7","unit":"ns/op","value":0,"throughput_mb_s":0,"allocations":0,"high_watermark":0,"vectorized":false}
{"name":"bench_hmac_sha256","suite":"phase7","unit":"ns/op","value":0,"throughput_mb_s":0,"allocations":0,"high_watermark":0,"vectorized":false}
{"name":"bench_aes_ctr","suite":"phase7","unit":"ns/op","value":0,"throughput_mb_s":0,"allocations":0,"high_watermark":0,"vectorized":false}
{"name":"bench_ghash","suite":"phase7","unit":"ns/op","value":0,"throughput_mb_s":0,"allocations":0,"high_watermark":0,"vectorized":false}
EOF
}

append_srtp_baseline_rows() {
    cat >> "$out_file" <<'EOF'
{"name":"bench_srtp_protect","suite":"phase9","unit":"ns/op","value":0,"throughput_mb_s":0,"packets_per_s":0,"p95_ns":0,"p99_ns":0,"allocations":0,"high_watermark":0}
{"name":"bench_srtp_unprotect","suite":"phase9","unit":"ns/op","value":0,"throughput_mb_s":0,"packets_per_s":0,"p95_ns":0,"p99_ns":0,"allocations":0,"high_watermark":0}
{"name":"bench_srtp_replay_check","suite":"phase9","unit":"ns/op","value":0,"throughput_mb_s":0,"packets_per_s":0,"p95_ns":0,"p99_ns":0,"allocations":0,"high_watermark":0}
EOF
}

append_rtp_rtcp_parser_baseline_rows() {
    cat >> "$out_file" <<'EOF'
{"name":"bench_rtp_parse","suite":"phase10","unit":"ns/packet","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_rtp_extension_parse","suite":"phase10","unit":"ns/packet","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_rtcp_parse","suite":"phase10","unit":"ns/packet","value":0,"allocations":0,"high_watermark":0}
EOF
}

append_jitter_baseline_rows() {
    cat >> "$out_file" <<'EOF'
{"name":"bench_jitter","suite":"phase12","unit":"ns/op","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_retransmission_cache","suite":"phase12","unit":"ns/op","value":0,"allocations":0,"high_watermark":0}
EOF
}

append_congestion_baseline_rows() {
    cat >> "$out_file" <<'EOF'
{"name":"bench_congestion_bandwidth_drop","suite":"phase15","unit":"ms","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_congestion_bandwidth_recovery","suite":"phase15","unit":"ms","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_congestion_queue_delay","suite":"phase15","unit":"ms","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_congestion_loss","suite":"phase15","unit":"pct","value":0,"allocations":0,"high_watermark":0}
{"name":"bench_congestion_jitter","suite":"phase15","unit":"ms","value":0,"allocations":0,"high_watermark":0}
EOF
}

append_datachannel_baseline_rows() {
    cat >> "$out_file" <<'EOF'
{"name":"bench_datachannel","suite":"phase13","unit":"ns/op","value":0,"allocations":0,"high_watermark":0,"vectorized":false}
EOF
}

run_crypto_bench_capture() {
    local out_path="$1"
    /bin/bash -c '../uya/bin/uya run src/webrtc_crypto_bench_main.uya > "$1" 2>/dev/null' _ "$out_path" 2>/dev/null
}

if run_crypto_bench_capture "$tmp_crypto_out"; then
    if rg -q '^\{' "$tmp_crypto_out"; then
        rg '^\{' "$tmp_crypto_out" >> "$out_file"
    else
        append_crypto_fallback_rows
    fi
else
    append_crypto_fallback_rows
fi

append_srtp_baseline_rows
append_rtp_rtcp_parser_baseline_rows
append_jitter_baseline_rows
append_congestion_baseline_rows
append_datachannel_baseline_rows
