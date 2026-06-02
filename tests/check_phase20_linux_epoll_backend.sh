#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc/net/linux_epoll.uya
test -f src/webrtc_linux_epoll_backend_test.uya
test -f src/webrtc/net/worker.uya

rg -Fq "export struct LinuxEpollBackend" src/webrtc/net/linux_epoll.uya
rg -Fq "export fn linux_epoll_backend_open" src/webrtc/net/linux_epoll.uya
rg -Fq "export fn linux_epoll_backend_register_fd" src/webrtc/net/linux_epoll.uya
rg -Fq "export fn linux_epoll_backend_wait" src/webrtc/net/linux_epoll.uya
rg -Fq "linux_epoll_backend_open" src/webrtc/net/worker.uya
rg -Fq "backend_kind" src/webrtc/net/worker.uya

../uya/bin/uya test src/webrtc_linux_epoll_backend_test.uya
../uya/bin/uya test src/webrtc_net_worker_test.uya
bash tests/check_phase20_net_backend_abstraction.sh
