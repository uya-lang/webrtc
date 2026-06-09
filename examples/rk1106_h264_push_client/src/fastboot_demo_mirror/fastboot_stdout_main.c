#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main uya_fastboot_demo_original_main
#include "fastboot_demo.c"
#undef main

static int setup_stdout_path(void) {
    g_fastboot_out_path = "/proc/self/fd/1";
    return 0;
}

int main(int argc, char **argv) {
    setup_stdout_path();
    return uya_fastboot_demo_original_main(argc, argv);
}
