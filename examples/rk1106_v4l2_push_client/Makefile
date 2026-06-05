SHELL := /bin/bash

EXAMPLE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(EXAMPLE_DIR)/../..)

SDK ?= /home/winger/rk1106/builder/rv1103b_linux_ipc_sdk
CROSS_BIN ?= $(SDK)/tools/linux/toolchain/arm-rockchip831-linux-uclibcgnueabihf/bin
CROSS_PREFIX ?= $(CROSS_BIN)/arm-rockchip831-linux-uclibcgnueabihf-
CROSS_CC ?= $(CROSS_PREFIX)gcc
STRIP ?= $(CROSS_PREFIX)strip

UYA ?= $(REPO_ROOT)/../uya/bin/uya
UYA_LIB ?= $(REPO_ROOT)/../uya/lib
VP8_REPO ?= $(REPO_ROOT)/../vp8
UYA_VP8_FORCE_SCALAR ?= 1

BUILD_DIR ?= $(EXAMPLE_DIR)/build
STAGE_ROOT := $(BUILD_DIR)/stage-uya-vp8
PACKAGE_DIR := $(BUILD_DIR)/rk1106-v4l2-push-client

UYA_SENDER_C := $(BUILD_DIR)/uya_vp8_direct_sender.c
UYA_SENDER := $(BUILD_DIR)/uya_vp8_direct_sender
HOST_SENDER_C := $(BUILD_DIR)/uya_vp8_direct_sender_host.c
HOST_SENDER := $(BUILD_DIR)/uya_vp8_direct_sender_host

TARGET_OS ?= linux
TARGET_ARCH ?= arm
RK_CFLAGS ?= -std=c99 -O2 -fno-builtin -U__ARM_NEON -marm
RK_LDFLAGS ?= -lm -pthread
HOST_TARGET_OS ?= linux
HOST_TARGET_ARCH ?= x86_64
HOST_CC ?= cc
HOST_CFLAGS ?= -std=c99 -O2 -fno-builtin -Wno-implicit-function-declaration
HOST_LDFLAGS ?= -lm -pthread

.PHONY: all package host clean check-tools check-stage-tools check-cross-tools strip

all: package

check-stage-tools:
	test -x "$(UYA)"
	test -d "$(UYA_LIB)"
	test -d "$(VP8_REPO)/src/vp8"

check-cross-tools: check-stage-tools
	test -x "$(CROSS_CC)"

check-tools: check-cross-tools

$(BUILD_DIR):
	mkdir -p "$@"

$(STAGE_ROOT)/.ready: tools/stage_uya_vp8_sender.py $(REPO_ROOT)/src/webrtc_uya_vp8_direct_sender_main.uya | $(BUILD_DIR) check-stage-tools
	python3 "$<" \
		--repo-root "$(REPO_ROOT)" \
		--vp8-repo "$(VP8_REPO)" \
		--uya-lib "$(UYA_LIB)" \
		--stage-root "$(STAGE_ROOT)" \
		--force-scalar "$(UYA_VP8_FORCE_SCALAR)"

$(UYA_SENDER_C): $(STAGE_ROOT)/.ready tools/patch_uya_c99_for_rk_uclibc.py
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(TARGET_OS)" TARGET_ARCH="$(TARGET_ARCH)" UYA_ROOT="$(STAGE_ROOT)/lib" \
		"$(UYA)" build "$(STAGE_ROOT)/src/webrtc_uya_vp8_direct_sender_main.uya" \
			--no-split-c --c99 -o "$@"
	python3 "$(EXAMPLE_DIR)/tools/patch_uya_c99_for_rk_uclibc.py" "$@"

$(UYA_SENDER): $(UYA_SENDER_C) | check-tools
	"$(CROSS_CC)" $(RK_CFLAGS) -Wno-implicit-function-declaration -o "$@" "$<" $(RK_LDFLAGS)

$(HOST_SENDER_C): $(STAGE_ROOT)/.ready | check-stage-tools
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(HOST_TARGET_OS)" TARGET_ARCH="$(HOST_TARGET_ARCH)" UYA_ROOT="$(STAGE_ROOT)/lib" \
		"$(UYA)" build "$(STAGE_ROOT)/src/webrtc_uya_vp8_direct_sender_main.uya" \
			--no-split-c --c99 -o "$@"

$(HOST_SENDER): $(HOST_SENDER_C)
	"$(HOST_CC)" $(HOST_CFLAGS) -o "$@" "$<" $(HOST_LDFLAGS)

host: $(HOST_SENDER)
	@printf 'host sender ready: %s\n' "$(HOST_SENDER)"

strip: $(UYA_SENDER)
	"$(STRIP)" "$(UYA_SENDER)" || true

package: $(UYA_SENDER) board_run.sh host/manual_preview.html host/signaling_server.py README.md
	rm -rf "$(PACKAGE_DIR)"
	mkdir -p "$(PACKAGE_DIR)/host"
	cp "$(UYA_SENDER)" "$(PACKAGE_DIR)/"
	cp board_run.sh "$(PACKAGE_DIR)/"
	cp host/manual_preview.html "$(PACKAGE_DIR)/host/"
	cp host/signaling_server.py "$(PACKAGE_DIR)/host/"
	cp README.md "$(PACKAGE_DIR)/"
	chmod +x "$(PACKAGE_DIR)/board_run.sh" "$(PACKAGE_DIR)/uya_vp8_direct_sender"
	@printf 'package ready: %s\n' "$(PACKAGE_DIR)"

clean:
	rm -rf "$(BUILD_DIR)"
