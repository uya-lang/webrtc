#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_ice_test.uya
test -d src/webrtc/ice
test -f src/webrtc/ice/candidate.uya
test -f src/webrtc/ice/checklist.uya
test -f src/webrtc/ice/agent.uya

rg -Fq 'test "ice candidate model owns transport address and related address metadata"' src/webrtc_ice_test.uya
rg -Fq 'test "candidate pair model tracks checklist state nomination and timing fields"' src/webrtc_ice_test.uya
rg -Fq 'test "ice agent model keeps owned credentials candidate pools and selected pair slot"' src/webrtc_ice_test.uya
rg -Fq 'test "ice helpers expose stable default state for future gathering and checklist work"' src/webrtc_ice_test.uya

rg -Fq "export const ICE_MAX_FOUNDATION_BYTES" src/webrtc/ice/candidate.uya
rg -Fq "export const ICE_COMPONENT_RTP" src/webrtc/ice/candidate.uya
rg -Fq "export const ICE_CANDIDATE_TRANSPORT_UDP" src/webrtc/ice/candidate.uya
rg -Fq "export struct IceTransportAddress" src/webrtc/ice/candidate.uya
rg -Fq "export struct IceCandidate" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_candidate_init" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_candidate_has_related_address" src/webrtc/ice/candidate.uya

rg -Fq "export const ICE_CANDIDATE_PAIR_STATE_FROZEN" src/webrtc/ice/checklist.uya
rg -Fq "export const ICE_CANDIDATE_PAIR_STATE_SUCCEEDED" src/webrtc/ice/checklist.uya
rg -Fq "export struct CandidatePair" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_init" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_is_selected" src/webrtc/ice/checklist.uya

rg -Fq "export const ICE_MAX_LOCAL_CANDIDATES" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_MAX_REMOTE_CANDIDATES" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_MAX_CANDIDATE_PAIRS" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_AGENT_ROLE_CONTROLLING" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_AGENT_STATE_NEW" src/webrtc/ice/agent.uya
rg -Fq "export struct IceCredentials" src/webrtc/ice/agent.uya
rg -Fq "export struct IceAgent" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_init" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_has_selected_pair" src/webrtc/ice/agent.uya
