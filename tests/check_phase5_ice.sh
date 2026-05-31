#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

test -f src/webrtc_ice_test.uya
test -d src/webrtc/ice
test -f src/webrtc/ice/candidate.uya
test -f src/webrtc/ice/checklist.uya
test -f src/webrtc/ice/agent.uya
test -f src/webrtc/ice/gather.uya

rg -Fq 'test "ice candidate model owns transport address and related address metadata"' src/webrtc_ice_test.uya
rg -Fq 'test "candidate pair model tracks checklist state nomination and timing fields"' src/webrtc_ice_test.uya
rg -Fq 'test "ice agent model keeps owned credentials candidate pools and selected pair slot"' src/webrtc_ice_test.uya
rg -Fq 'test "ice helpers expose stable default state for future gathering and checklist work"' src/webrtc_ice_test.uya
rg -Fq 'test "candidate pair helpers follow RFC 8445 priority order and compatibility gates"' src/webrtc_ice_test.uya
rg -Fq 'test "checklist rebuild sorts compatible pairs and seeds one waiting pair per foundation"' src/webrtc_ice_test.uya
rg -Fq 'test "checklist rebuild filters incompatible pairs and selected pair survives trickle remote updates"' src/webrtc_ice_test.uya
rg -Fq 'test "checklist rebuild rejects fixed pair capacity without leaving partial state"' src/webrtc_ice_test.uya
rg -Fq 'test "connectivity check transaction builds authenticated binding requests and marks pair in progress"' src/webrtc_ice_test.uya
rg -Fq 'test "role conflict request resolution follows RFC 8445 tie breaker rules"' src/webrtc_ice_test.uya
rg -Fq 'test "regular nomination waits for a valid pair and marks a successful nomination"' src/webrtc_ice_test.uya
rg -Fq 'test "connectivity check success response updates pair timing consent and validity"' src/webrtc_ice_test.uya
rg -Fq 'test "aggressive nomination mode allows use-candidate on the first controlling check"' src/webrtc_ice_test.uya
rg -Fq 'test "ice state change events queue unique snapshots for nomination and trickle transitions"' src/webrtc_ice_test.uya
rg -Fq 'test "dual agents complete selected pair across nomination request and success response"' src/webrtc_ice_test.uya
rg -Fq 'test "local trickle candidate addition reopens completed state until checklist rebuild"' src/webrtc_ice_test.uya
rg -Fq 'test "ice state change events track consent disconnect failure and recovery"' src/webrtc_ice_test.uya
rg -Fq 'test "consent freshness on selected pair schedules periodic binding checks without leaving completed state"' src/webrtc_ice_test.uya
rg -Fq 'test "consent freshness timeout transitions selected pair through disconnected and failed"' src/webrtc_ice_test.uya
rg -Fq 'test "consent freshness recovery restores selected pair after disconnected retry succeeds"' src/webrtc_ice_test.uya
rg -Fq 'test "role conflict error responses switch roles refresh tie breaker and requeue the pair"' src/webrtc_ice_test.uya
rg -Fq 'test "non-role-conflict error responses fail the pair and stale checklist transactions are rejected"' src/webrtc_ice_test.uya
rg -Fq 'test "candidate priority helpers follow RFC 8445 formula and reject invalid inputs"' src/webrtc_ice_test.uya
rg -Fq 'test "remote candidate addition upserts transport tuple and copies related metadata"' src/webrtc_ice_test.uya
rg -Fq 'test "remote candidate addition keeps distinct component and transport tuples"' src/webrtc_ice_test.uya
rg -Fq 'test "remote candidate addition rejects invalid candidates and clears stale entries"' src/webrtc_ice_test.uya
rg -Fq 'test "remote candidate addition enforces fixed pool capacity"' src/webrtc_ice_test.uya
rg -Fq 'test "host candidate helpers copy bounded address foundation and equality state"' src/webrtc_ice_test.uya
rg -Fq 'test "host and srflx gathering assign candidate priorities by type component and network cost"' src/webrtc_ice_test.uya
rg -Fq 'test "host candidate gathering from descriptors deduplicates per component and prunes stale host entries"' src/webrtc_ice_test.uya
rg -Fq 'test "host candidate gathering skips unspecified addresses and zero-port bindings"' src/webrtc_ice_test.uya
rg -Fq 'test "srflx candidate gathering builds binding request and adds related base metadata from success response"' src/webrtc_ice_test.uya
rg -Fq 'test "srflx candidate gathering deduplicates repeated mapped addresses and host regather prunes stale srflx entries"' src/webrtc_ice_test.uya
rg -Fq 'test "srflx candidate gathering rejects mismatched transaction ids and non-success responses"' src/webrtc_ice_test.uya

rg -Fq "export const ICE_MAX_FOUNDATION_BYTES" src/webrtc/ice/candidate.uya
rg -Fq "export const ICE_COMPONENT_RTP" src/webrtc/ice/candidate.uya
rg -Fq "export const ICE_CANDIDATE_TRANSPORT_UDP" src/webrtc/ice/candidate.uya
rg -Fq "export struct IceTransportAddress" src/webrtc/ice/candidate.uya
rg -Fq "export struct IceCandidate" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_candidate_init" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_candidate_has_related_address" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_transport_address_set" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_transport_address_equal" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_candidate_set_foundation" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_candidate_type_preference" src/webrtc/ice/candidate.uya
rg -Fq "export fn ice_candidate_priority_from_parts" src/webrtc/ice/candidate.uya

rg -Fq "export const ICE_CANDIDATE_PAIR_STATE_FROZEN" src/webrtc/ice/checklist.uya
rg -Fq "export const ICE_CANDIDATE_PAIR_STATE_SUCCEEDED" src/webrtc/ice/checklist.uya
rg -Fq "export struct CandidatePair" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_init" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_priority" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_compute_priority" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_can_form" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_foundation_equal" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_sort_by_priority_desc" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_seed_initial_states" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_note_check_sent" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_note_check_succeeded" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_note_consent_observed" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_note_check_failed" src/webrtc/ice/checklist.uya
rg -Fq "export fn candidate_pair_is_selected" src/webrtc/ice/checklist.uya

rg -Fq "export const ICE_MAX_LOCAL_CANDIDATES" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_MAX_REMOTE_CANDIDATES" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_MAX_CANDIDATE_PAIRS" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_AGENT_ROLE_CONTROLLING" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_AGENT_STATE_NEW" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_AGENT_STATE_EVENT_QUEUE_CAPACITY" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_MAX_CONNECTIVITY_CHECK_USERNAME_BYTES" src/webrtc/ice/agent.uya
rg -Fq "export const ICE_STUN_ERROR_ROLE_CONFLICT" src/webrtc/ice/agent.uya
rg -Fq "export struct IceCredentials" src/webrtc/ice/agent.uya
rg -Fq "export struct IceConnectivityCheckTransaction" src/webrtc/ice/agent.uya
rg -Fq "export struct IceConnectivityCheckResult" src/webrtc/ice/agent.uya
rg -Fq "export struct IceRoleConflictResult" src/webrtc/ice/agent.uya
rg -Fq "export struct IceStateChangeEvent" src/webrtc/ice/agent.uya
rg -Fq "export struct IceAgent" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_credentials_set" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_credentials_is_configured" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_init" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_clear_checklist" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_clear_remote_candidates" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_add_remote_candidate" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_rebuild_checklist" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_trickle_is_complete" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_state_change_event_len" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_pop_state_change_event" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_note_local_gathering_started" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_note_local_gathering_complete" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_note_remote_gathering_started" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_note_remote_gathering_complete" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_resolve_role_conflict_request" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_connectivity_check_transaction_init" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_connectivity_check_build_binding_request" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_connectivity_check_handle_response" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_consent_check_transaction_init" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_consent_tick" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_select_checklist_pair" src/webrtc/ice/agent.uya
rg -Fq "export fn ice_agent_has_selected_pair" src/webrtc/ice/agent.uya

rg -Fq "export const ICE_MAX_INTERFACE_NAME_BYTES" src/webrtc/ice/gather.uya
rg -Fq "extern \"libc\" fn getifaddrs" src/webrtc/ice/gather.uya
rg -Fq "extern \"libc\" fn inet_ntop" src/webrtc/ice/gather.uya
rg -Fq "export struct IceHostPortBinding" src/webrtc/ice/gather.uya
rg -Fq "export struct IceHostInterfaceDescriptor" src/webrtc/ice/gather.uya
rg -Fq "export struct IceHostGatherResult" src/webrtc/ice/gather.uya
rg -Fq "export struct IceSrflxGatherTransaction" src/webrtc/ice/gather.uya
rg -Fq "export struct IceSrflxGatherResult" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_host_interface_descriptor_set_name" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_host_interface_descriptor_set_host" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_agent_prune_host_candidates" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_agent_prune_srflx_candidates" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_agent_add_host_candidate" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_srflx_gather_transaction_init" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_srflx_build_binding_request" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_agent_add_srflx_candidate" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_agent_gather_srflx_candidate_from_response" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_agent_gather_host_candidates_from_descriptors" src/webrtc/ice/gather.uya
rg -Fq "export fn ice_agent_gather_host_candidates" src/webrtc/ice/gather.uya
rg -Fq "ICE_CANDIDATE_TYPE_HOST" src/webrtc/ice/gather.uya
rg -Fq "ICE_CANDIDATE_TYPE_SRFLX" src/webrtc/ice/gather.uya
rg -Fq "stun_parse_xor_mapped_address" src/webrtc/ice/gather.uya
rg -Fq "stun_builder_init_binding_request" src/webrtc/ice/gather.uya
