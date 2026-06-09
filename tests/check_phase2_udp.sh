#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_net_udp_test.uya
test -f src/webrtc_net_worker_test.uya
test -f src/webrtc/net/udp.uya
test -f src/webrtc/net/worker.uya
test -f src/webrtc/net/linux_epoll.uya
test -x tests/udp_loopback_echo.py
test -f benchmarks/baselines/bench_udp_echo.jsonl
test -x tests/udp_bench_baseline.py

rg -q 'test "udp socket config enables bind connect optional and nonblocking"' src/webrtc_net_udp_test.uya
rg -q 'test "udp batch io exposes recvmmsg sendmmsg and fallback entrypoints"' src/webrtc_net_udp_test.uya
rg -q 'test "worker timer heap orders earliest deadlines first"' src/webrtc_net_worker_test.uya
rg -q 'test "transport worker owns epoll timer heap and bounded queues"' src/webrtc_net_worker_test.uya
rg -q 'test "transport worker queues commands and emits events"' src/webrtc_net_worker_test.uya

rg -q "export struct UdpSocketConfig" src/webrtc/net/udp.uya
rg -q "export struct UdpSocket" src/webrtc/net/udp.uya
rg -q "export struct UdpRecvSlot" src/webrtc/net/udp.uya
rg -q "export struct UdpSendSlot" src/webrtc/net/udp.uya
rg -q "export const UDP_IO_BATCH_MAX" src/webrtc/net/udp.uya
rg -q "SYS_recvmmsg" src/webrtc/net/udp.uya
rg -q "SYS_sendmmsg" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_open" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_bind_any" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_bind_loopback" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_connect_optional" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_set_nonblocking" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_recvmmsg" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_sendmmsg" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_recv_fallback" src/webrtc/net/udp.uya
rg -q "export fn udp_socket_send_fallback" src/webrtc/net/udp.uya

rg -q "export struct WorkerTimer" src/webrtc/net/worker.uya
rg -q "export struct WorkerTimerHeap" src/webrtc/net/worker.uya
rg -q "export struct WorkerCommand" src/webrtc/net/worker.uya
rg -q "export struct WorkerEvent" src/webrtc/net/worker.uya
rg -q "export struct TransportWorkerConfig" src/webrtc/net/worker.uya
rg -q "export struct TransportWorker" src/webrtc/net/worker.uya
rg -q "sys_epoll_create1" src/webrtc/net/linux_epoll.uya
rg -q "linux_epoll_backend_open" src/webrtc/net/worker.uya
rg -q "worker_timer_heap_push" src/webrtc/net/worker.uya
rg -q "worker_timer_heap_pop_ready" src/webrtc/net/worker.uya
rg -q "transport_worker_init" src/webrtc/net/worker.uya
rg -q "transport_worker_enqueue_command" src/webrtc/net/worker.uya
rg -q "transport_worker_publish_event" src/webrtc/net/worker.uya
rg -q "transport_worker_pop_event" src/webrtc/net/worker.uya
rg -q "transport_worker_run_once" src/webrtc/net/worker.uya
rg -q "RingQueue" src/webrtc/net/worker.uya

python3 tests/udp_loopback_echo.py
python3 tests/udp_bench_baseline.py
