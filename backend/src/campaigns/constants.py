"""Imports only stdlib — no config/DB side effects. RetrySchedulerWorkflow
(campaigns/workflows.py, added Batch 13) imports this from inside sandboxed workflow code.
"""

from dataclasses import dataclass
from datetime import timedelta

MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class RetryWindow:
    min_delay: timedelta
    max_delay: timedelta

    def delay_seconds(self, *, random_value: float) -> float:
        """`random_value` is caller-supplied (workflow.random(), never random.random() —
        CLAUDE.md §2.6's determinism rule) so this stays a pure function of its inputs."""
        span = (self.max_delay - self.min_delay).total_seconds()
        return self.min_delay.total_seconds() + random_value * span


# Keyed by the attempt number just made — the value is how long to wait before the NEXT
# attempt. Spec §6.1: attempt 2 retries "later on the same day where permissible, preferably
# at least 2-4 hours later"; attempt 3 is the final automated attempt, given the same window
# shape (a later/different permitted contact period) since the spec doesn't prescribe a
# distinct value for it beyond "another permitted contact period."
ATTEMPT_WINDOWS: dict[int, RetryWindow] = {
    1: RetryWindow(min_delay=timedelta(hours=2), max_delay=timedelta(hours=6)),
    2: RetryWindow(min_delay=timedelta(hours=2), max_delay=timedelta(hours=4)),
}
