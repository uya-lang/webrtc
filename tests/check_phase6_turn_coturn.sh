#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

cache_root="/tmp/webrtc-coturn-interop"
deb_root="$cache_root/debs"
pkg_root="$cache_root/pkg"
lib_root="$cache_root/libs"
log_file="$cache_root/turnserver.log"
db_file="$cache_root/turndb.sqlite"
turn_port=34780
relay_min_port=49160
relay_max_port=49169

turn_pid=""

cleanup() {
    if [[ -n "$turn_pid" ]]; then
        kill "$turn_pid" 2>/dev/null || true
        wait "$turn_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT

clear_proxy_env() {
    HTTPS_PROXY= \
    HTTP_PROXY= \
    ALL_PROXY= \
    https_proxy= \
    http_proxy= \
    all_proxy= \
    "$@"
}

bootstrap_coturn() {
    mkdir -p "$deb_root" "$pkg_root" "$lib_root"

    if [[ ! -x "$pkg_root/usr/bin/turnserver" ]]; then
        (
            cd "$deb_root"
            clear_proxy_env apt-get -o Acquire::https::Proxy=false -o Acquire::http::Proxy=false download \
                coturn \
                libpq5 \
                libmariadb3 \
                libevent-core-2.1-7 \
                libevent-extra-2.1-7 \
                libevent-openssl-2.1-7 \
                libevent-pthreads-2.1-7
        )

        rm -rf "$pkg_root" "$lib_root"
        mkdir -p "$pkg_root" "$lib_root"

        dpkg-deb -x "$deb_root"/coturn_*.deb "$pkg_root"
        dpkg-deb -x "$deb_root"/libpq5_*.deb "$lib_root"
        dpkg-deb -x "$deb_root"/libmariadb3_*.deb "$lib_root"
        dpkg-deb -x "$deb_root"/libevent-core-2.1-7_*.deb "$lib_root"
        dpkg-deb -x "$deb_root"/libevent-extra-2.1-7_*.deb "$lib_root"
        dpkg-deb -x "$deb_root"/libevent-openssl-2.1-7_*.deb "$lib_root"
        dpkg-deb -x "$deb_root"/libevent-pthreads-2.1-7_*.deb "$lib_root"

        (
            cd "$lib_root/usr/lib/x86_64-linux-gnu"
            ln -sf libpq.so.5.16 libpq.so.5
            ln -sf libevent_core-2.1.so.7.0.1 libevent_core-2.1.so.7
            ln -sf libevent_extra-2.1.so.7.0.1 libevent_extra-2.1.so.7
            ln -sf libevent_openssl-2.1.so.7.0.1 libevent_openssl-2.1.so.7
            ln -sf libevent_pthreads-2.1.so.7.0.1 libevent_pthreads-2.1.so.7
        )
    fi
}

start_turnserver() {
    mkdir -p "$cache_root"
    : > "$db_file"
    : > "$log_file"

    LD_LIBRARY_PATH="$lib_root/usr/lib/x86_64-linux-gnu:$lib_root/lib/x86_64-linux-gnu" \
        "$pkg_root/usr/bin/turnserver" \
        -n \
        -m 0 \
        -L 127.0.0.1 \
        -E 127.0.0.1 \
        -p "$turn_port" \
        --min-port "$relay_min_port" \
        --max-port "$relay_max_port" \
        --allow-loopback-peers \
        --no-cli \
        -a \
        -u uya:uya-pass \
        -r uya.test \
        -f \
        --no-tls \
        --no-dtls \
        -b "$db_file" \
        -l stdout \
        >"$log_file" 2>&1 &
    turn_pid="$!"

    for _ in $(seq 1 100); do
        if ! kill -0 "$turn_pid" 2>/dev/null; then
            cat "$log_file" >&2
            return 1
        fi
        if rg -q "Relay ports initialization done" "$log_file"; then
            return 0
        fi
        sleep 0.1
    done

    cat "$log_file" >&2
    return 1
}

bootstrap_coturn
start_turnserver

if ! timeout 20s ../uya/bin/uya run src/webrtc_turn_coturn_test_main.uya; then
    cat "$log_file" >&2
    exit 1
fi
