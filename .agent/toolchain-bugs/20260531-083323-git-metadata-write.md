## Summary

The sandbox allows editing tracked files in the workspace but rejects writes inside `.git`, which blocks `git add` and `git commit` for this repo.

## Affected Tasks

- Requirement 10: create a git commit after completing tasks in this run.
- Requirement 11: stage only this round's related files before committing.

## Toolchain Command

`touch .git/codex-write-test`

## Actual Error

`touch: cannot touch '.git/codex-write-test': Read-only file system`

## Expected Behavior

Creating a temporary file under `.git` should succeed so git can create `index.lock`, write objects, and update refs for a normal commit.

## Repro File

`.agent/toolchain-bugs/repros/20260531-083323-git-metadata-write.sh`

## Repro Code

```sh
#!/usr/bin/env bash
set -euo pipefail

touch .git/codex-write-test
```

## Notes

- `git add Makefile docs/todo.md ...` failed earlier with `fatal: Unable to create '.git/index.lock': Read-only file system`.
- Reconfirmed on the first补提交 attempt with `git add Makefile docs/todo.md && git commit -m "tests: gate the loopback UDP echo milestone"`, which failed with `fatal: Unable to create '/media/winger/_dde_data/winger/uya/webrtc/.git/index.lock': Read-only file system`.
- Reconfirmed on the second补提交 attempt with `git add Makefile docs/todo.md src/webrtc/sdp/model.uya src/webrtc/sdp/parse.uya src/webrtc/sdp/write.uya src/webrtc/sdp/jsep.uya src/webrtc_sdp_test.uya tests/check_phase3_sdp.sh tests/check_test_entrypoints.sh tests/fixtures/sdp/README.md tests/fixtures/sdp/chrome_offer.sdp tests/fixtures/sdp/firefox_offer.sdp tests/sdp_fixture_roundtrip.py`, which failed with `fatal: Unable to create '/home/winger/uya/webrtc/.git/index.lock': Read-only file system`.
- Reconfirmed on the third补提交 attempt after re-verifying the Phase 2/3 files with `git add Makefile docs/todo.md src/webrtc/sdp/model.uya src/webrtc/sdp/parse.uya src/webrtc/sdp/write.uya src/webrtc/sdp/jsep.uya src/webrtc_sdp_test.uya tests/check_phase3_sdp.sh tests/fixtures/sdp/README.md tests/fixtures/sdp/chrome_offer.sdp tests/fixtures/sdp/firefox_offer.sdp tests/sdp_fixture_roundtrip.py`, which failed with `fatal: Unable to create '/home/winger/uya/webrtc/.git/index.lock': Read-only file system`.
- Reconfirmed on the fourth补提交 attempt with `git add Makefile docs/todo.md src/webrtc/sdp/model.uya src/webrtc/sdp/parse.uya src/webrtc/sdp/write.uya src/webrtc/sdp/jsep.uya src/webrtc_sdp_test.uya tests/check_phase2_udp.sh tests/check_phase3_sdp.sh tests/check_test_entrypoints.sh tests/fixtures/sdp/README.md tests/fixtures/sdp/chrome_offer.sdp tests/fixtures/sdp/firefox_offer.sdp tests/sdp_fixture_roundtrip.py tests/udp_loopback_echo.py`, which failed with `fatal: Unable to create '/home/winger/uya/webrtc/.git/index.lock': Read-only file system`.
- Reconfirmed in the same fourth补提交 attempt with `git add .agent/toolchain-bugs/20260531-083323-git-metadata-write.md .agent/toolchain-bugs/repros/20260531-083323-git-metadata-write.sh`, which failed with `fatal: Unable to create '/home/winger/uya/webrtc/.git/index.lock': Read-only file system`.
- Reconfirmed on the fifth补提交 attempt with `git add Makefile docs/todo.md src/webrtc/sdp/model.uya src/webrtc/sdp/parse.uya src/webrtc/sdp/write.uya src/webrtc/sdp/jsep.uya src/webrtc_sdp_test.uya tests/check_phase3_sdp.sh tests/check_test_entrypoints.sh tests/fixtures/sdp/README.md tests/fixtures/sdp/chrome_offer.sdp tests/fixtures/sdp/firefox_offer.sdp tests/sdp_fixture_roundtrip.py`, which failed with `fatal: Unable to create '/media/winger/_dde_data/winger/uya/webrtc/.git/index.lock': Read-only file system`.
- Reconfirmed on the sixth补提交 attempt after re-scoping the Phase 3 verification to only the requested fixture/harness/model files with `git add Makefile docs/todo.md src/webrtc/sdp/model.uya tests/check_phase3_sdp.sh tests/check_test_entrypoints.sh tests/fixtures/sdp/README.md tests/fixtures/sdp/chrome_offer.sdp tests/fixtures/sdp/firefox_offer.sdp tests/sdp_fixture_roundtrip.py`, which failed with `fatal: Unable to create '/media/winger/_dde_data/winger/uya/webrtc/.git/index.lock': Read-only file system`.
- A direct sandbox write probe with `touch .git/codex-write-test` also failed with `touch: cannot touch '.git/codex-write-test': Read-only file system`.
- The repo working tree itself remains writable; only `.git` metadata writes are blocked by the environment.
