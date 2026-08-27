# ruff: noqa
# Deliberately "bad" fixture code for scripts/ci/check_no_raw_prompt_concat.py's
# meta-test — never imported, never collected, never linted.


def build_system_prompt(ctx, transcript):
    return f"You are an insurance agent. Caller said: {transcript}"  # VIOLATION


def build_system_prompt_ok(ctx):
    return f"Stage: {ctx.claim_stage}"  # OK — no raw-text identifier involved
