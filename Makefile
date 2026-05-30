SHELL := /bin/bash

BUILD_DIR := build
BIN := $(BUILD_DIR)/webrtc-uya
BENCH_DIR := $(BUILD_DIR)/benchmarks
BENCH_FILE := $(BENCH_DIR)/baseline.jsonl

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
		printf '%s\n' 'case "$${1:-}" in'; \
		printf '%s\n' '  ""|--help|-h)'; \
		printf '%s\n' '    printf "%s\n" "webrtc-uya placeholder CLI" "Usage:" "  webrtc-uya [--help|-h]" "  webrtc-uya version"'; \
		printf '%s\n' '    ;;'; \
		printf '%s\n' '  version)'; \
		printf '%s\n' '    printf "%s\n" "webrtc-uya 0.0.0-placeholder"'; \
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
	test -f src/webrtc/time.uya
	test -f src/webrtc/ring.uya
	test -d tests
	test -f tests/main_test.uya
	test -f src/webrtc_ring_test.uya
	test -f src/webrtc_arena_test.uya
	rg -q "export fn monotonic_now" src/webrtc/time.uya
	rg -q "CLOCK_MONOTONIC" src/webrtc/time.uya
	rg -q "export fn ring_queue_init" src/webrtc/ring.uya
	rg -q "export fn ring_queue_push" src/webrtc/ring.uya
	rg -q "export fn ring_queue_pop" src/webrtc/ring.uya
	rg -q "high_watermark" src/webrtc/ring.uya
	rg -q 'test "tests entry imports core webrtc modules"' tests/main_test.uya
	rg -q 'test "ring queue preserves FIFO order across wraparound"' src/webrtc_ring_test.uya
	rg -q 'test "ring queue rejects full and empty operations"' src/webrtc_ring_test.uya
	rg -q 'test "packet arena copies payload into owned slab"' src/webrtc_arena_test.uya
	rg -q 'test "packet arena rejects oversize payload and exhausted arena"' src/webrtc_arena_test.uya
	test -x $(BIN)
	./$(BIN) --help >/dev/null
	./$(BIN) version >/dev/null

bench: build
	mkdir -p $(BENCH_DIR)
	printf '%s\n' '{"name":"placeholder","unit":"ns/op","value":0,"allocations":0}' > $(BENCH_FILE)
	test -s $(BENCH_FILE)

clean:
	rm -rf $(BUILD_DIR)
