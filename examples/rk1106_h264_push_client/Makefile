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
MEDIA_OUT ?= $(SDK)/media/out
MPP_INC ?= $(MEDIA_OUT)/include/rockchip
MPP_LIB ?= $(MEDIA_OUT)/lib
PATCH_UYA_C99 ?= $(REPO_ROOT)/examples/rk1106_v4l2_push_client/tools/patch_uya_c99_for_rk_uclibc.py

BUILD_DIR ?= $(EXAMPLE_DIR)/build
PACKAGE_DIR := $(BUILD_DIR)/rk1106-h264-push-client

SENDER_C := $(BUILD_DIR)/rk1106_h264_sender.c
SENDER := $(BUILD_DIR)/rk1106_h264_sender
HOST_SENDER_C := $(BUILD_DIR)/rk1106_h264_sender_host.c
HOST_SENDER := $(BUILD_DIR)/rk1106_h264_sender_host
SHIM_C := $(EXAMPLE_DIR)/src/rk1106_h264_encoder_shim.c

TARGET_OS ?= linux
TARGET_ARCH ?= arm
RK_CFLAGS ?= -std=c99 -O2 -fno-builtin -U__ARM_NEON -marm -Wno-incompatible-pointer-types -Wno-implicit-function-declaration
RK_LDFLAGS ?= -lm -pthread -Wl,-rpath,'$$ORIGIN/lib'
HOST_TARGET_OS ?= linux
HOST_TARGET_ARCH ?= x86_64
HOST_CC ?= cc
HOST_CFLAGS ?= -std=c99 -O2 -fno-builtin -Wno-incompatible-pointer-types -Wno-implicit-function-declaration
HOST_LDFLAGS ?= -lm -pthread

.PHONY: all package host clean check-tools check-cross-tools check-host-tools check-host-encoder-tools strip

all: package

check-host-tools:
	test -x "$(UYA)"
	test -d "$(UYA_LIB)"

check-host-encoder-tools: check-host-tools
	command -v ffmpeg >/dev/null

check-cross-tools: check-host-tools
	test -x "$(CROSS_CC)"
	test -d "$(MPP_INC)"
	test -d "$(MPP_LIB)"

check-tools: check-cross-tools

$(BUILD_DIR):
	mkdir -p "$@"

$(SENDER_C): $(REPO_ROOT)/src/webrtc_rk1106_h264_sender_main.uya $(REPO_ROOT)/src/webrtc/media/rk1106_h264_encoder.uya | $(BUILD_DIR) check-host-tools
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(TARGET_OS)" TARGET_ARCH="$(TARGET_ARCH)" UYA_ROOT="$(UYA_LIB)" \
		"$(UYA)" build "src/webrtc_rk1106_h264_sender_main.uya" \
			--no-split-c --c99 -o "$@"
	python3 "$(PATCH_UYA_C99)" "$@"
	python3 "$(EXAMPLE_DIR)/tools/patch_arm_pthread_create_stub.py" "$@"

$(SENDER): $(SENDER_C) $(SHIM_C) | check-cross-tools
	"$(CROSS_CC)" $(RK_CFLAGS) -DUYA_RK1106_H264_ENCODER_ENABLE_MPP \
		-I"$(MPP_INC)" -o "$@" "$(SENDER_C)" "$(SHIM_C)" \
		-L"$(MPP_LIB)" -lrockchip_mpp $(RK_LDFLAGS)

$(HOST_SENDER_C): $(REPO_ROOT)/src/webrtc_rk1106_h264_sender_main.uya $(REPO_ROOT)/src/webrtc/media/rk1106_h264_encoder.uya | $(BUILD_DIR) check-host-tools
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(HOST_TARGET_OS)" TARGET_ARCH="$(HOST_TARGET_ARCH)" UYA_ROOT="$(UYA_LIB)" \
		"$(UYA)" build "src/webrtc_rk1106_h264_sender_main.uya" \
			--no-split-c --c99 -o "$@"

$(HOST_SENDER): $(HOST_SENDER_C) $(SHIM_C) | check-host-encoder-tools
	"$(HOST_CC)" $(HOST_CFLAGS) -o "$@" "$(HOST_SENDER_C)" "$(SHIM_C)" $(HOST_LDFLAGS)

host: $(HOST_SENDER)
	@printf 'host fallback sender ready: %s\n' "$(HOST_SENDER)"

strip: $(SENDER)
	"$(STRIP)" "$(SENDER)" || true

package: $(SENDER) board_run.sh host/manual_preview.html host/signaling_server.py README.md
	rm -rf "$(PACKAGE_DIR)"
	mkdir -p "$(PACKAGE_DIR)/host" "$(PACKAGE_DIR)/lib"
	cp "$(SENDER)" "$(PACKAGE_DIR)/"
	cp board_run.sh "$(PACKAGE_DIR)/"
	cp host/manual_preview.html "$(PACKAGE_DIR)/host/"
	cp host/signaling_server.py "$(PACKAGE_DIR)/host/"
	cp README.md "$(PACKAGE_DIR)/"
	if [ -e "$(MPP_LIB)/librockchip_mpp.so" ]; then cp -P "$(MPP_LIB)"/librockchip_mpp.so* "$(PACKAGE_DIR)/lib/"; else cp -P "$(MPP_LIB)"/librockchip_mpp.so* "$(PACKAGE_DIR)/lib/"; fi
	chmod +x "$(PACKAGE_DIR)/board_run.sh" "$(PACKAGE_DIR)/rk1106_h264_sender"
	@printf 'package ready: %s\n' "$(PACKAGE_DIR)"

clean:
	rm -rf "$(BUILD_DIR)"
