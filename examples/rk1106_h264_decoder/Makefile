SHELL := /bin/bash

EXAMPLE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(EXAMPLE_DIR)/../..)

SDK ?= /home/winger/rk1106/builder/rv1103b_linux_ipc_sdk
CROSS_BIN ?= $(SDK)/tools/linux/toolchain/arm-rockchip831-linux-uclibcgnueabihf/bin
CROSS_PREFIX ?= $(CROSS_BIN)/arm-rockchip831-linux-uclibcgnueabihf-
CROSS_CC ?= $(CROSS_PREFIX)gcc
STRIP ?= $(CROSS_PREFIX)strip

UYA ?= $(REPO_ROOT)/uya/bin/uya
UYA_LIB ?= $(REPO_ROOT)/uya/lib
MEDIA_OUT ?= $(SDK)/media/out
MPP_INC ?= $(MEDIA_OUT)/include/rockchip
MPP_LIB ?= $(MEDIA_OUT)/lib
PATCH_UYA_C99 ?= $(REPO_ROOT)/examples/rk1106_v4l2_push_client/tools/patch_uya_c99_for_rk_uclibc.py

BUILD_DIR ?= $(EXAMPLE_DIR)/build
PACKAGE_DIR := $(BUILD_DIR)/rk1106-h264-decoder

DECODER_C := $(BUILD_DIR)/webrtc_rk1106_h264_decoder.c
DECODER := $(BUILD_DIR)/webrtc_rk1106_h264_decoder
HOST_DECODER_C := $(BUILD_DIR)/webrtc_rk1106_h264_decoder_host.c
HOST_DECODER := $(BUILD_DIR)/webrtc_rk1106_h264_decoder_host
SHIM_C := $(EXAMPLE_DIR)/src/rk1106_h264_decoder_shim.c

TARGET_OS ?= linux
TARGET_ARCH ?= arm
RK_CFLAGS ?= -std=c99 -O2 -fno-builtin -U__ARM_NEON -marm -Wno-incompatible-pointer-types
RK_LDFLAGS ?= -lm -pthread -Wl,-rpath,'$$ORIGIN/lib'
HOST_TARGET_OS ?= linux
HOST_TARGET_ARCH ?= x86_64
HOST_CC ?= cc
HOST_CFLAGS ?= -std=c99 -O2 -fno-builtin -Wno-incompatible-pointer-types
HOST_LDFLAGS ?= -lm -pthread

.PHONY: all package host clean check-tools check-cross-tools check-host-tools strip

all: package

check-host-tools:
	test -x "$(UYA)"
	test -d "$(UYA_LIB)"

check-cross-tools: check-host-tools
	test -x "$(CROSS_CC)"
	test -d "$(MPP_INC)"
	test -d "$(MPP_LIB)"

check-tools: check-cross-tools

$(BUILD_DIR):
	mkdir -p "$@"

$(DECODER_C): $(REPO_ROOT)/src/webrtc_rk1106_h264_decoder_main.uya $(REPO_ROOT)/src/webrtc/media/rk1106_h264_decoder.uya | $(BUILD_DIR) check-host-tools
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(TARGET_OS)" TARGET_ARCH="$(TARGET_ARCH)" UYA_ROOT="$(UYA_LIB)" \
		"$(UYA)" build "src/webrtc_rk1106_h264_decoder_main.uya" \
			--no-split-c --c99 -o "$@"
	python3 "$(PATCH_UYA_C99)" "$@"

$(DECODER): $(DECODER_C) $(SHIM_C) | check-cross-tools
	"$(CROSS_CC)" $(RK_CFLAGS) -DUYA_RK1106_H264_DECODER_ENABLE_MPP \
		-I"$(MPP_INC)" -o "$@" "$(DECODER_C)" "$(SHIM_C)" \
		-L"$(MPP_LIB)" -lrockchip_mpp $(RK_LDFLAGS)

$(HOST_DECODER_C): $(REPO_ROOT)/src/webrtc_rk1106_h264_decoder_main.uya $(REPO_ROOT)/src/webrtc/media/rk1106_h264_decoder.uya | $(BUILD_DIR) check-host-tools
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(HOST_TARGET_OS)" TARGET_ARCH="$(HOST_TARGET_ARCH)" UYA_ROOT="$(UYA_LIB)" \
		"$(UYA)" build "src/webrtc_rk1106_h264_decoder_main.uya" \
			--no-split-c --c99 -o "$@"

$(HOST_DECODER): $(HOST_DECODER_C) $(SHIM_C)
	"$(HOST_CC)" $(HOST_CFLAGS) -o "$@" "$(HOST_DECODER_C)" "$(SHIM_C)" $(HOST_LDFLAGS)

host: $(HOST_DECODER)
	@printf 'host fallback decoder ready: %s\n' "$(HOST_DECODER)"

strip: $(DECODER)
	"$(STRIP)" "$(DECODER)" || true

package: $(DECODER) README.md
	rm -rf "$(PACKAGE_DIR)"
	mkdir -p "$(PACKAGE_DIR)/lib"
	cp "$(DECODER)" "$(PACKAGE_DIR)/"
	cp README.md "$(PACKAGE_DIR)/"
	if [ -e "$(MPP_LIB)/librockchip_mpp.so" ]; then cp -P "$(MPP_LIB)"/librockchip_mpp.so* "$(PACKAGE_DIR)/lib/"; else cp -P "$(MPP_LIB)"/librockchip_mpp.so* "$(PACKAGE_DIR)/lib/"; fi
	chmod +x "$(PACKAGE_DIR)/webrtc_rk1106_h264_decoder"
	@printf 'package ready: %s\n' "$(PACKAGE_DIR)"

clean:
	rm -rf "$(BUILD_DIR)"
