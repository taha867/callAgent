"""Imports ONLY `enum` — nothing else, matching the convention every other constants.py in
this repo follows (see src/calls/constants.py's docstring). qa/ owns no Temporal workflow
itself, but keeping this module import-clean costs nothing and keeps every constants.py
uniform.

DemoJourneyId — the 9 mandatory demo journeys, spec §29-30, phases/phase-4-demo-hardening.md.

AdversarialScenarioId — the phase file's adversarial/failure-injection checklist (lines
35-70), deduped from 34 raw bullets down to 28 canonical members: several raw bullets
describe the same underlying mechanism twice in different words (see
.claude/specs/phase-4-backend-spec.md §2's dedup table) — most notably "STT uncertainty /
low confidence", "Persistent low STT confidence -> DTMF fallback", and "Three consecutive
low-STT turns -> DTMF fallback" all collapse onto DTMF_FALLBACK_TRIGGERED (voice/dtmf.py's
MAX_CONSECUTIVE_LOW_STT_TURNS=3 counter), and "LLM timeout mid-call" / "LLM/STT/TTS timeout
mid-call" collapse onto VENDOR_TIMEOUT_MID_CALL.

PHASE_5_BLOCKED_SCENARIOS mirrors calls/constants.py::FUTURE_GLOBAL_INTERRUPTS's existing
convention exactly: reserved names for scenarios with no corresponding backend code yet
(src/risk/, PrivacyRequest, RecordingConsent, CommunicationSuppression all don't exist —
confirmed via read-only exploration before writing this spec/plan) — not driven by any
Phase 4 code path.
"""

from enum import StrEnum


class DemoJourneyId(StrEnum):
    DEMO_1_SUCCESSFUL_STATUS_UPDATE = "DEMO_1_SUCCESSFUL_STATUS_UPDATE"
    DEMO_2_CUSTOMER_BUSY = "DEMO_2_CUSTOMER_BUSY"
    DEMO_3_WRONG_PERSON = "DEMO_3_WRONG_PERSON"
    DEMO_4_AUTHENTICATION_FAILURE = "DEMO_4_AUTHENTICATION_FAILURE"
    DEMO_5_DOCUMENT_STATUS_DISPUTE = "DEMO_5_DOCUMENT_STATUS_DISPUTE"
    DEMO_6_DELAYED_CLAIM_DISSATISFIED_CUSTOMER = "DEMO_6_DELAYED_CLAIM_DISSATISFIED_CUSTOMER"
    DEMO_7_MULTI_TURN_QUESTIONS = "DEMO_7_MULTI_TURN_QUESTIONS"
    DEMO_8_HUMAN_COMPLAINT_ESCALATION = "DEMO_8_HUMAN_COMPLAINT_ESCALATION"
    DEMO_9_NO_ANSWER = "DEMO_9_NO_ANSWER"


class AdversarialScenarioId(StrEnum):
    BARGE_IN = "BARGE_IN"
    SILENCE_UNCLEAR = "SILENCE_UNCLEAR"
    ANGRY_DISTRESSED = "ANGRY_DISTRESSED"
    CODE_SWITCHING_EN_AR = "CODE_SWITCHING_EN_AR"
    WRONG_PERSON = "WRONG_PERSON"
    AUTH_REFUSED = "AUTH_REFUSED"
    AUTH_INCORRECT_BOTH_ATTEMPTS = "AUTH_INCORRECT_BOTH_ATTEMPTS"
    CONTRADICTORY_STATEMENTS = "CONTRADICTORY_STATEMENTS"
    SYSTEM_DATA_UNAVAILABLE = "SYSTEM_DATA_UNAVAILABLE"
    TELEPHONY_FAILURE_MID_CALL = "TELEPHONY_FAILURE_MID_CALL"
    VENDOR_TIMEOUT_MID_CALL = "VENDOR_TIMEOUT_MID_CALL"
    JAILBREAK_SYSTEM_OVERRIDE = "JAILBREAK_SYSTEM_OVERRIDE"
    PROMPT_EXTRACTION_ATTEMPT = "PROMPT_EXTRACTION_ATTEMPT"
    UNPROMPTED_PII_DISCLOSURE = "UNPROMPTED_PII_DISCLOSURE"
    DTMF_FALLBACK_TRIGGERED = "DTMF_FALLBACK_TRIGGERED"
    INVALID_UNAUTHORIZED_CLI = "INVALID_UNAUTHORIZED_CLI"
    CONCURRENT_CALL_COLLISION = "CONCURRENT_CALL_COLLISION"
    CONTACT_WINDOW_BLACKOUT = "CONTACT_WINDOW_BLACKOUT"
    ANSWER_SEIZURE_TIMEOUT = "ANSWER_SEIZURE_TIMEOUT"
    BACKEND_TIMEOUT_POST_AUTH = "BACKEND_TIMEOUT_POST_AUTH"
    IDEMPOTENCY_REPLAY = "IDEMPOTENCY_REPLAY"
    OTP_ABUSE_LIFECYCLE = "OTP_ABUSE_LIFECYCLE"
    WORKER_RESTART_MID_SESSION = "WORKER_RESTART_MID_SESSION"
    CALL_DROP_PRE_POST_AUTH = "CALL_DROP_PRE_POST_AUTH"
    # Phase 5-blocked (see PHASE_5_BLOCKED_SCENARIOS below) — present so the checklist stays
    # complete and reviewable, not silently dropped.
    DSAR_REQUEST = "DSAR_REQUEST"
    MINOR_ANSWERED = "MINOR_ANSWERED"
    COMMUNICATION_SUPPRESSION_REQUEST = "COMMUNICATION_SUPPRESSION_REQUEST"
    RECORDING_CONSENT_REFUSED = "RECORDING_CONSENT_REFUSED"
    FRAUD_SIGNAL_COVERT_ROUTING = "FRAUD_SIGNAL_COVERT_ROUTING"
    VULNERABLE_CUSTOMER_DISCLOSURE = "VULNERABLE_CUSTOMER_DISCLOSURE"
    LEGAL_SENSITIVITY_EVIDENCE_HOLD = "LEGAL_SENSITIVITY_EVIDENCE_HOLD"
    SIM_SWAP_RISK_SIGNAL = "SIM_SWAP_RISK_SIGNAL"


PHASE_5_BLOCKED_SCENARIOS: frozenset[str] = frozenset(
    {
        AdversarialScenarioId.DSAR_REQUEST,
        AdversarialScenarioId.MINOR_ANSWERED,
        AdversarialScenarioId.COMMUNICATION_SUPPRESSION_REQUEST,
        AdversarialScenarioId.RECORDING_CONSENT_REFUSED,
        AdversarialScenarioId.FRAUD_SIGNAL_COVERT_ROUTING,
        AdversarialScenarioId.VULNERABLE_CUSTOMER_DISCLOSURE,
        AdversarialScenarioId.LEGAL_SENSITIVITY_EVIDENCE_HOLD,
        AdversarialScenarioId.SIM_SWAP_RISK_SIGNAL,
    }
)


class DefectStatus(StrEnum):
    OPEN = "OPEN"
    FIX_APPLIED = "FIX_APPLIED"
    COMPILED = "COMPILED"
    WONT_FIX = "WONT_FIX"


class CompiledArtifactType(StrEnum):
    REGRESSION_TEST = "REGRESSION_TEST"
    GUARD_PHRASE_RULE = "GUARD_PHRASE_RULE"
    TOOL_ALLOWLIST_RULE = "TOOL_ALLOWLIST_RULE"
    NON_NEGOTIABLE_RULE = "NON_NEGOTIABLE_RULE"
