# ruff: noqa
# Deliberately "bad" fixture code for scripts/ci/check_transcript_redaction.py's meta-test
# — never imported, never collected, never linted.


async def persist_transcript_turn_bad(session, calls_service, raw_text, **kwargs):
    # VIOLATION — raw_text passed straight through, never redacted.
    await calls_service.record_transcript_turn(session, redacted_text=raw_text, **kwargs)


async def persist_transcript_turn_ok(session, calls_service, privacy_service, raw_text, **kwargs):
    result = privacy_service.redact(raw_text, language="en")
    await calls_service.record_transcript_turn(
        session, redacted_text=result.redacted_text, **kwargs
    )  # OK
