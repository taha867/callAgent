"""The one Temporal workflow-sandbox configuration every real Worker() in this codebase
uses — worker.py (the live process) and every integration test that constructs an in-test
Worker() for a real (non-test-local) workflow.

tests/integration/test_phase0_e2e.py originally built this restriction set privately for
its own test-local Phase0SmokeWorkflow. Phase 1 registers real workflows
(src.calls.workflows.CallSessionWorkflow and friends) in worker.py itself, so the same
passthrough configuration has to live somewhere both worker.py and the test suite can
import it from — otherwise worker.py would run under the SDK's *stricter* default sandbox
restrictions (no "pydantic"/"src" passthrough), which nothing has proven workflow code
against, and a workflow that imports cleanly under pytest could still fail to boot under
`python worker.py` with a sandbox-restriction error at Worker() construction time.

Workflow-defining modules under src/ (src.calls.workflows, src.campaigns.workflows,
src.complaints.workflows) must still keep their own module-level imports limited to
`pydantic` + other `src` modules that are themselves sandbox-safe (no SQLAlchemy/asyncpg
import chains) — this passthrough list makes those two packages importable inside the
sandbox, it does not make arbitrary third-party imports safe.
"""

from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

SANDBOXED_WORKFLOW_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules("pydantic", "src")
)
