SHELL := /bin/bash

BUILD_DIR := build
BIN := $(BUILD_DIR)/webrtc-uya
BENCH_DIR := $(BUILD_DIR)/benchmarks
BENCH_FILE := $(BENCH_DIR)/baseline.jsonl

.PHONY: all build test bench clean

all: build

build: $(BIN)

$(BIN): Makefile src/main.uya
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
	test -x $(BIN)
	./$(BIN) --help >/dev/null
	./$(BIN) version >/dev/null

bench: build
	mkdir -p $(BENCH_DIR)
	printf '%s\n' '{"name":"placeholder","unit":"ns/op","value":0,"allocations":0}' > $(BENCH_FILE)
	test -s $(BENCH_FILE)

clean:
	rm -rf $(BUILD_DIR)
