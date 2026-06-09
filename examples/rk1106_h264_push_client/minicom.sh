#!/bin/bash

BAUD_RATE=1500000
# BAUD_RATE=115200
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MINICOM_HOME="$SCRIPT_DIR/build/rk1106-h264-push-client"
MINICOM_PROFILE="xyglasses-uart"
MINICOM_CONFIG="$MINICOM_HOME/.minirc.$MINICOM_PROFILE"
MINICOM_UPLOAD_DIR="$MINICOM_HOME"
MINICOM_DOWNLOAD_DIR="$MINICOM_HOME"
CAPTURE_TIMESTAMP="$(date +%F_%H-%M-%S)"
CAPTURE_FILE="$MINICOM_HOME/${CAPTURE_TIMESTAMP}_uart.log"
LATEST_CAPTURE_LINK="$MINICOM_HOME/latest_uart.log"

mkdir -p "$MINICOM_HOME" "$MINICOM_UPLOAD_DIR" "$MINICOM_DOWNLOAD_DIR"
: >"$CAPTURE_FILE"
ln -sfn "$(basename "$CAPTURE_FILE")" "$LATEST_CAPTURE_LINK"

# 检查串口设备是否存在
DEVICE="/dev/ttyUSB0"
if [ ! -e "$DEVICE" ]; then
    echo "错误: 串口设备 $DEVICE 不存在"
    echo "可用的串口设备:"
    ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "未找到 USB 串口设备"
    exit 1
fi

cat >"$MINICOM_CONFIG" <<EOF
# Machine-generated file - use "minicom -s" to change parameters.
pu port             $DEVICE
pu baudrate         $BAUD_RATE
pu bits             8
pu parity           N
pu stopbits         1
pu updir            $MINICOM_UPLOAD_DIR
pu downdir          $MINICOM_DOWNLOAD_DIR
EOF

echo "minicom 上传目录: $MINICOM_UPLOAD_DIR"
echo "minicom 接收目录: $MINICOM_DOWNLOAD_DIR"
echo "minicom 日志文件: $CAPTURE_FILE"
echo "minicom 最新日志: $LATEST_CAPTURE_LINK"

MINICOM_ARGS=(
    "$MINICOM_PROFILE"
    -D "$DEVICE"
    -b "$BAUD_RATE"
    -8
    -C "$CAPTURE_FILE"
    --capturefile-buffer-mode=N
)

# 检查权限
if [ ! -r "$DEVICE" ] || [ ! -w "$DEVICE" ]; then
    echo "警告: 没有权限访问 $DEVICE"
    echo "解决方法:"
    echo "  1. 将用户添加到 dialout 组: sudo usermod -aG dialout $USER"
    echo "  2. 然后重新登录或运行: newgrp dialout"
    echo "  3. 或者使用 sudo 运行此脚本"
    echo ""
    echo "使用 sudo 运行 minicom..."
    sudo env HOME="$MINICOM_HOME" minicom "${MINICOM_ARGS[@]}"
else
    HOME="$MINICOM_HOME" minicom "${MINICOM_ARGS[@]}"
fi
