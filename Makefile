SHELL := /bin/bash

BUILD_DIR := build
BIN := $(BUILD_DIR)/webrtc-uya
BENCH_DIR := $(BUILD_DIR)/benchmarks
BENCH_FILE := $(BENCH_DIR)/baseline.jsonl
BENCH_RUNNER := benchmarks/run.sh

.PHONY: all build test bench clean

all: build

build: $(BIN)

$(BIN): Makefile src/main.uya src/webrtc/time.uya
	mkdir -p $(BUILD_DIR)
	rm -f $@
	{ \
		printf '%s\n' '#!/usr/bin/env bash'; \
		printf '%s\n' 'set -euo pipefail'; \
		printf '%s\n' ''; \
		printf '%s\n' 'script_dir="$$(cd "$$(dirname "$$0")" && pwd)"; repo_root="$$(cd "$$script_dir/.." && pwd)"'; \
		printf '%s\n' 'case "$${1:-}" in'; \
		printf '%s\n' '  ""|--help|-h)'; \
		printf '%s\n' '    printf "%s\n" "webrtc-uya placeholder CLI" "Usage:" "  webrtc-uya [--help|-h]" "  webrtc-uya version" "  webrtc-uya dump-stats"'; \
		printf '%s\n' '    ;;'; \
		printf '%s\n' '  version)'; \
		printf '%s\n' '    printf "%s\n" "webrtc-uya 0.0.0-placeholder"'; \
		printf '%s\n' '    ;;'; \
		printf '%s\n' '  dump-stats)'; \
		printf '%s\n' '    exec "$${repo_root}/../uya/bin/uya" run "$${repo_root}/src/webrtc_dump_stats_main.uya"'; \
		printf '%s\n' '    ;;'; \
		printf '%s\n' '  *)'; \
		printf '%s\n' '    printf "unknown command: %s\n" "$${1:-}" >&2'; \
		printf '%s\n' '    exit 1'; \
		printf '%s\n' '    ;;'; \
		printf '%s\n' 'esac'; \
	} > $@
	chmod +x $@

test: build
	test -f src/main.uya
	test -f src/webrtc/binary.uya
	test -f src/webrtc/time.uya
	test -f src/webrtc/bench.uya
	test -f src/webrtc/ring.uya
	test -f src/webrtc/testing.uya
	test -d tests
	test -d benchmarks
	test -f benchmarks/main.uya
	test -f benchmarks/bench_arena_ring.uya
	test -x $(BENCH_RUNNER)
	test -f tests/main_test.uya
	test -f src/webrtc_binary_test.uya
	test -f src/webrtc_ring_test.uya
	test -f src/webrtc_arena_test.uya
	test -f src/webrtc_bench_test.uya
	test -f src/webrtc_ice_test.uya
	test -f src/webrtc_dtls_test_main.uya
	test -f src/webrtc_turn_test_main.uya
	test -x tests/check_phase7_crypto.sh
	test -x tests/check_phase8_dtls.sh
	test -x tests/check_phase12_rtp.sh
	test -x tests/check_phase13_sctp.sh
	test -x tests/check_phase15_congestion.sh
	test -x tests/check_phase15_pacer.sh
	test -x tests/check_phase15_rtp_sender_pacer.sh
	test -x tests/check_phase16_stats_types.sh
	test -x tests/check_phase16_stats_collect.sh
	test -x tests/check_phase16_get_stats.sh
	test -x tests/check_phase16_dump_stats.sh
	test -x tests/check_phase16_trace_ring.sh
	rg -q "export struct ByteReader" src/webrtc/binary.uya
	rg -q "export struct ByteWriter" src/webrtc/binary.uya
	rg -q "export fn read_be_u16" src/webrtc/binary.uya
	rg -q "export fn write_le_u32" src/webrtc/binary.uya
	rg -q "export fn checked_align_up_usize" src/webrtc/binary.uya
	rg -q "export fn constant_time_bytes_equal" src/webrtc/binary.uya
	rg -q "export fn monotonic_now" src/webrtc/time.uya
	rg -q "export struct BenchmarkSample" src/webrtc/bench.uya
	rg -q "export fn benchmark_jsonl_write_line" src/webrtc/bench.uya
	rg -q "CLOCK_MONOTONIC" src/webrtc/time.uya
	rg -q "export struct SlabTransferToken" src/webrtc/arena.uya
	rg -q "export struct PacketCloneBudget" src/webrtc/arena.uya
	rg -q "export fn packet_ref_take_slab_token" src/webrtc/arena.uya
	rg -q "export fn packet_arena_clone_to_owner" src/webrtc/arena.uya
	rg -q "export fn ring_queue_init" src/webrtc/ring.uya
	rg -q "export fn ring_queue_push" src/webrtc/ring.uya
	rg -q "export fn ring_queue_pop" src/webrtc/ring.uya
	rg -q "high_watermark" src/webrtc/ring.uya
	rg -q "export struct AllocationCounterSnapshot" src/webrtc/testing.uya
	rg -q "export fn allocation_counter_expect_delta" src/webrtc/testing.uya
	rg -q 'test "tests entry imports core webrtc modules"' tests/main_test.uya
	rg -q 'test "byte reader rejects truncated reads and slice overruns"' src/webrtc_binary_test.uya
	rg -q 'test "byte writer rejects fixed buffer overflow and backfill overruns"' src/webrtc_binary_test.uya
	rg -q 'test "packet arena clone budget tracks clone stats and rejects overflow"' src/webrtc_arena_test.uya
	rg -Fq '@align_of(PacketRef)' src/webrtc_arena_test.uya
	rg -q 'test "ring queue counter helper captures depth and drops"' src/webrtc_ring_test.uya
	rg -q 'test "benchmark jsonl helper formats arena ring sample"' src/webrtc_bench_test.uya
	rg -q 'test "ring queue preserves FIFO order across wraparound"' src/webrtc_ring_test.uya
	rg -q 'test "ring queue rejects full and empty operations"' src/webrtc_ring_test.uya
	rg -q 'test "packet arena copies payload into owned slab"' src/webrtc_arena_test.uya
	rg -q 'test "packet arena rejects oversize payload and exhausted arena"' src/webrtc_arena_test.uya
	bash tests/check_phase2_udp.sh
	bash tests/check_phase3_sdp.sh
	bash tests/check_phase4_stun.sh
	bash tests/check_phase5_ice.sh
	bash tests/check_phase6_turn.sh
	bash tests/check_phase7_crypto.sh
	bash tests/check_phase8_dtls.sh
	bash tests/check_phase12_rtp.sh
	bash tests/check_phase13_sctp.sh
	bash tests/check_phase15_congestion.sh
	bash tests/check_phase15_pacer.sh
	bash tests/check_phase15_rtp_sender_pacer.sh
	bash tests/check_phase16_stats_types.sh
	bash tests/check_phase16_stats_collect.sh
	bash tests/check_phase16_get_stats.sh
	bash tests/check_phase16_dump_stats.sh
	bash tests/check_phase16_trace_ring.sh
	test -x $(BIN)
	./$(BIN) --help >/dev/null
	./$(BIN) version >/dev/null

bench: build
	mkdir -p $(BENCH_DIR)
	test -d benchmarks
	test -f benchmarks/main.uya
	test -f benchmarks/bench_arena_ring.uya
	test -f benchmarks/bench_sdp_parse.uya
	test -f benchmarks/bench_stun_parse.uya
	test -f benchmarks/bench_crypto_phase7.uya
	test -f benchmarks/bench_jitter.uya
	test -f benchmarks/bench_congestion.uya
	test -f benchmarks/bench_datachannel.uya
	test -f benchmarks/baselines/bench_jitter.jsonl
	test -f benchmarks/baselines/bench_congestion.jsonl
	test -f benchmarks/baselines/bench_datachannel.jsonl
	test -x $(BENCH_RUNNER)
	./$(BENCH_RUNNER) $(BENCH_FILE)
	python3 tests/jitter_bench_baseline.py
	python3 tests/congestion_bench_baseline.py
	test -s $(BENCH_FILE)
	rg -q '"name":"placeholder"' $(BENCH_FILE)
	rg -q '"name":"bench_arena_ring"' $(BENCH_FILE)
	rg -q '"name":"bench_sdp_parse"' $(BENCH_FILE)
	rg -q '"name":"bench_stun_parse"' $(BENCH_FILE)
	rg -q '"name":"bench_hmac_sha1"' $(BENCH_FILE)
	rg -q '"name":"bench_hmac_sha256"' $(BENCH_FILE)
	rg -q '"name":"bench_aes_ctr"' $(BENCH_FILE)
	rg -q '"name":"bench_ghash"' $(BENCH_FILE)
	rg -q '"name":"bench_jitter"' $(BENCH_FILE)
	rg -q '"name":"bench_congestion_bandwidth_drop"' $(BENCH_FILE)
	rg -q '"name":"bench_congestion_bandwidth_recovery"' $(BENCH_FILE)
	rg -q '"name":"bench_congestion_queue_delay"' $(BENCH_FILE)
	rg -q '"name":"bench_congestion_loss"' $(BENCH_FILE)
	rg -q '"name":"bench_congestion_jitter"' $(BENCH_FILE)
	rg -q '"name":"bench_retransmission_cache"' $(BENCH_FILE)

clean:
	rm -rf $(BUILD_DIR)
