SHELL := /bin/bash

EXAMPLE_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO_ROOT := $(abspath $(EXAMPLE_DIR)/../..)

SDK ?= /media/winger/_dde_home/winger/wingo/work/rk/builder/rv1103b_clean/rv1103b_linux_ipc_sdk
CROSS_BIN ?= $(SDK)/tools/linux/toolchain/arm-rockchip831-linux-uclibcgnueabihf/bin
CROSS_PREFIX ?= $(CROSS_BIN)/arm-rockchip831-linux-uclibcgnueabihf-
CROSS_CC ?= $(CROSS_PREFIX)gcc
STRIP ?= $(CROSS_PREFIX)strip

UYA ?= $(REPO_ROOT)/../uya/bin/uya
UYA_LIB ?= $(REPO_ROOT)/../uya/lib
MEDIA_OUT ?= $(SDK)/media/out
MPI_INC ?= $(MEDIA_OUT)/include
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
AUDIO_SHIM_C := $(EXAMPLE_DIR)/src/rk1106_g711_audio_shim.c
HELPER_C := $(EXAMPLE_DIR)/src/rk1106_h264_capture_helper.c
HELPER := $(BUILD_DIR)/rk1106_h264_capture_helper
FASTBOOT_MIRROR_C := $(EXAMPLE_DIR)/src/fastboot_demo_mirror/fastboot_demo.c
FASTBOOT_MIRROR := $(BUILD_DIR)/fastboot_demo_mirror
FASTBOOT_FIFO := $(BUILD_DIR)/fastboot_h264_fifo

TARGET_OS ?= linux
TARGET_ARCH ?= arm
RK_CFLAGS ?= -std=c99 -O2 -fno-builtin -U__ARM_NEON -marm -Wno-incompatible-pointer-types -Wno-implicit-function-declaration
RK_LDFLAGS ?= -lm -pthread
HOST_TARGET_OS ?= linux
HOST_TARGET_ARCH ?= x86_64
HOST_CC ?= cc
HOST_CFLAGS ?= -std=c99 -O2 -fno-builtin -Wno-incompatible-pointer-types -Wno-implicit-function-declaration
HOST_LDFLAGS ?= -lm -pthread

.PHONY: all package host clean check-tools check-cross-tools check-host-tools check-host-encoder-tools strip helper fastboot-mirror

all: package

check-host-tools:
	test -x "$(UYA)"
	test -d "$(UYA_LIB)"

check-host-encoder-tools: check-host-tools
	command -v ffmpeg >/dev/null

check-cross-tools: check-host-tools
	test -x "$(CROSS_CC)"
	test -d "$(MPP_INC)"
	test -d "$(MPI_INC)"
	test -d "$(MPP_LIB)"

check-tools: check-cross-tools

$(BUILD_DIR):
	mkdir -p "$@"

$(SENDER_C): $(REPO_ROOT)/src/webrtc_rk1106_h264_sender_main.uya \
		$(REPO_ROOT)/src/webrtc/crypto/p256.uya \
		$(REPO_ROOT)/src/webrtc/dtls/server.uya \
		$(REPO_ROOT)/src/webrtc/media/direct_sender.uya \
		$(REPO_ROOT)/src/webrtc/media/direct_session.uya \
		$(REPO_ROOT)/src/webrtc/media/direct_runtime.uya \
		$(REPO_ROOT)/src/webrtc/media/model.uya \
		$(REPO_ROOT)/src/webrtc/media/rk1106_g711_audio.uya \
		$(REPO_ROOT)/src/webrtc/media/fastboot_h264_codec.uya \
		$(UYA_LIB)/tls/crypto/ec.uya \
		$(UYA_LIB)/tls/crypto/ec_p256.uya \
		$(AUDIO_SHIM_C) | $(BUILD_DIR) check-host-tools
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(TARGET_OS)" TARGET_ARCH="$(TARGET_ARCH)" UYA_ROOT="$(UYA_LIB)" \
		"$(UYA)" build "src/webrtc_rk1106_h264_sender_main.uya" \
			--no-split-c --c99 -o "$@"
	python3 "$(PATCH_UYA_C99)" "$@"
	python3 "$(EXAMPLE_DIR)/tools/patch_arm_pthread_create_stub.py" "$@"

$(SENDER): $(SENDER_C) $(AUDIO_SHIM_C) | check-cross-tools
	# Sender reads audio G711 frames from a FIFO filled by fastboot_h264_fifo helper.
	# No Rockchip MPI / librockit.a dependency → no sys_bind symbol conflict.
	"$(CROSS_CC)" $(RK_CFLAGS) \
		-I"$(MPI_INC)" -o "$@" "$(SENDER_C)" "$(AUDIO_SHIM_C)" \
		$(RK_LDFLAGS)

MPP_PROBE_C := $(EXAMPLE_DIR)/tools/mpp_probe_main.c
MPP_PROBE := $(BUILD_DIR)/mpp_probe

.PHONY: probe
$(MPP_PROBE): $(MPP_PROBE_C) $(SHIM_C) | $(BUILD_DIR) check-cross-tools
	"$(CROSS_CC)" $(RK_CFLAGS) -DUYA_RK1106_H264_ENCODER_ENABLE_MPP \
		-I"$(MPP_INC)" -o "$@" "$(MPP_PROBE_C)" "$(SHIM_C)" \
		-L"$(MPP_LIB)" -Wl,-Bstatic -lrockchip_mpp -Wl,-Bdynamic \
		$(RK_LDFLAGS)

probe: $(MPP_PROBE)
	@printf 'mpp probe ready: %s\n' "$(MPP_PROBE)"

$(HELPER): $(HELPER_C) | check-cross-tools
	"$(CROSS_CC)" $(RK_CFLAGS) \
		-I"$(MPI_INC)" -I"$(MPP_INC)" -o "$@" "$(HELPER_C)" \
		-L"$(MPP_LIB)" -Wl,-rpath-link,"$(MPP_LIB)" \
		"$(MPP_LIB)/librockit.a" "$(MPP_LIB)/librockchip_mpp.a" "$(MPP_LIB)/librga.a" \
		-lpthread -lm

helper: $(HELPER)
	@printf 'helper ready: %s\n' "$(HELPER)"

$(FASTBOOT_MIRROR): $(FASTBOOT_MIRROR_C) | check-cross-tools
	"$(CROSS_CC)" "$(FASTBOOT_MIRROR_C)" -o "$@" \
		-I"$(MPI_INC)" -I"$(MPP_INC)" -I"$(SDK)/output/out/media_out/include" -I"$(SDK)/project/make_meta/include" \
		-I"$(MEDIA_OUT)/include/libdrm" -I"$(MEDIA_OUT)/include/rkaiq" -I"$(MEDIA_OUT)/include/rkaiq/uAPI" \
		-I"$(MEDIA_OUT)/include/rkaiq/uAPI2" -I"$(MEDIA_OUT)/include/rkaiq/algos" -I"$(MEDIA_OUT)/include/rkaiq/common" \
		-I"$(MEDIA_OUT)/include/rkaiq/xcore" -I"$(MEDIA_OUT)/include/rkaiq/iq_parser" -I"$(MEDIA_OUT)/include/rkaiq/iq_parser_v2" \
		-I"$(MEDIA_OUT)/include/rkaiq/smartIr" -L"$(MPP_LIB)" -Wl,-rpath-link,"$(MPP_LIB)" \
		-Wl,-Bstatic -pthread -lrockit -lrtsp -lrockchip_mpp -lrksysutils -lsmartIr -lrkaudio_detect -lrkaudio_vqe -lrkaudio -lrga \
		-Wl,-Bdynamic -lrkaiq -lstdc++ -lm

fastboot-mirror: $(FASTBOOT_MIRROR)
	@printf 'fastboot mirror ready: %s\n' "$(FASTBOOT_MIRROR)"

$(FASTBOOT_FIFO): $(FASTBOOT_MIRROR)
	cp "$(FASTBOOT_MIRROR)" "$@"
	chmod +x "$@"

fastboot-fifo: $(FASTBOOT_FIFO)
	@printf 'fastboot fifo ready: %s\n' "$(FASTBOOT_FIFO)"

$(HOST_SENDER_C): $(REPO_ROOT)/src/webrtc_rk1106_h264_sender_main.uya \
		$(REPO_ROOT)/src/webrtc/crypto/p256.uya \
		$(REPO_ROOT)/src/webrtc/dtls/server.uya \
		$(REPO_ROOT)/src/webrtc/media/direct_sender.uya \
		$(REPO_ROOT)/src/webrtc/media/direct_session.uya \
		$(REPO_ROOT)/src/webrtc/media/direct_runtime.uya \
		$(REPO_ROOT)/src/webrtc/media/model.uya \
		$(REPO_ROOT)/src/webrtc/media/rk1106_g711_audio.uya \
		$(REPO_ROOT)/src/webrtc/media/fastboot_h264_codec.uya \
		$(UYA_LIB)/tls/crypto/ec.uya \
		$(UYA_LIB)/tls/crypto/ec_p256.uya \
		$(AUDIO_SHIM_C) | $(BUILD_DIR) check-host-tools
	cd "$(REPO_ROOT)" && \
		TARGET_OS="$(HOST_TARGET_OS)" TARGET_ARCH="$(HOST_TARGET_ARCH)" UYA_ROOT="$(UYA_LIB)" \
		"$(UYA)" build "src/webrtc_rk1106_h264_sender_main.uya" \
			--no-split-c --c99 -o "$@"

$(HOST_SENDER): $(HOST_SENDER_C) $(SHIM_C) $(AUDIO_SHIM_C) | check-host-encoder-tools
	"$(HOST_CC)" $(HOST_CFLAGS) -o "$@" "$(HOST_SENDER_C)" "$(SHIM_C)" "$(AUDIO_SHIM_C)" $(HOST_LDFLAGS)

host: $(HOST_SENDER)
	@printf 'host fallback sender ready: %s\n' "$(HOST_SENDER)"

strip: $(SENDER)
	"$(STRIP)" "$(SENDER)" || true

package: $(SENDER) $(HELPER) $(FASTBOOT_MIRROR) $(FASTBOOT_FIFO) board_run.sh host/manual_preview.html host/signaling_server.py README.md
	rm -rf "$(PACKAGE_DIR)"
	mkdir -p "$(PACKAGE_DIR)" "$(PACKAGE_DIR)/host"
	cp "$(SENDER)" "$(PACKAGE_DIR)/"
	cp "$(HELPER)" "$(PACKAGE_DIR)/"
	cp "$(FASTBOOT_MIRROR)" "$(PACKAGE_DIR)/"
	cp "$(FASTBOOT_FIFO)" "$(PACKAGE_DIR)/fastboot_h264_fifo"
	cp board_run.sh "$(PACKAGE_DIR)/"
	cp host/manual_preview.html "$(PACKAGE_DIR)/host/"
	cp host/signaling_server.py "$(PACKAGE_DIR)/host/"
	cp README.md "$(PACKAGE_DIR)/"
	chmod +x "$(PACKAGE_DIR)/board_run.sh" "$(PACKAGE_DIR)/rk1106_h264_sender" "$(PACKAGE_DIR)/rk1106_h264_capture_helper" "$(PACKAGE_DIR)/fastboot_demo_mirror" "$(PACKAGE_DIR)/fastboot_h264_fifo"
	@printf 'package ready: %s\n' "$(PACKAGE_DIR)"

clean:
	rm -rf "$(BUILD_DIR)"
