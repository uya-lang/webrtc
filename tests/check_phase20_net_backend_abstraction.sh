#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/net/backend.uya
test -f src/webrtc_net_backend_test.uya
test -f src/webrtc/net/udp.uya

rg -Fq "export struct NetBackendDescriptor" src/webrtc/net/backend.uya
rg -Fq "NET_BACKEND_KIND_LINUX_EPOLL" src/webrtc/net/backend.uya
rg -Fq "NET_BACKEND_KIND_MACOS_KQUEUE" src/webrtc/net/backend.uya
rg -Fq "NET_BACKEND_KIND_WINDOWS_IOCP" src/webrtc/net/backend.uya
rg -Fq "NET_BACKEND_CAP_BATCH_RECV" src/webrtc/net/backend.uya
rg -Fq "export fn net_backend_select" src/webrtc/net/backend.uya
rg -Fq "backend_kind" src/webrtc/net/udp.uya
rg -Fq "export fn udp_socket_config_backend" src/webrtc/net/udp.uya

"${UYA:-./uya/bin/uya}" test src/webrtc_net_backend_test.uya
bash tests/check_phase2_udp.sh
