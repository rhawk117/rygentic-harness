from dataclasses import dataclass

from vibe_code_cli.tune.errors import RoutingFailedError
from vibe_code_cli.tune.routing.transcript import SessionTranscript


@dataclass(slots=True, kw_only=True, frozen=True)
class SessionPolicy:
    def summarize_stderr(self, stderr: str) -> str:
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        if not lines:
            return ""

        return lines[-1]

    def failure_detail(self, transcript: SessionTranscript, stderr: str) -> str:
        if detail := transcript.failure_detail:
            return detail

        return self.summarize_stderr(stderr)

    def get_listing_problem(
        self,
        transcript: SessionTranscript,
        request: str,
        team: frozenset[str],
    ) -> RoutingFailedError | None:
        if not (missing := transcript.unlisted(team)):
            return None

        names = ", ".join(missing)
        return RoutingFailedError(request, f"staged skills were not listed: {names}")

    def get_outcome_problem(
        self,
        transcript: SessionTranscript,
        request: str,
        stderr: str,
    ) -> RoutingFailedError | None:
        if transcript.finished:
            return None

        return RoutingFailedError(request, self.failure_detail(transcript, stderr))
