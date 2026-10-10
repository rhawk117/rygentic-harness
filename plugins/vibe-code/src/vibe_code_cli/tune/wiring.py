from dataclasses import dataclass
from pathlib import Path

from vibe_code_cli.tune.collisions import DEFAULT_THRESHOLD, Bm25CollisionDetector
from vibe_code_cli.tune.domain.state import LoopState
from vibe_code_cli.tune.domain.values import Judge
from vibe_code_cli.tune.routing import ClaudeCodeRouterFactory
from vibe_code_cli.tune.services import PublishingService, RoutingService, TuningService
from vibe_code_cli.tune.store import FilePacketPublisher, JsonLoopStore, StateCodec

PACKET_FOLDER = 'packets'
STATE_CODEC = StateCodec(state_type=LoopState)


@dataclass(slots=True, kw_only=True, frozen=True)
class Settings:
    state: Path
    claude: str | None = None
    collision_threshold: float = DEFAULT_THRESHOLD


@dataclass(slots=True, kw_only=True, frozen=True)
class TuneServices:
    tuning: TuningService
    routing: RoutingService
    publishing: PublishingService


def build_services(settings: Settings) -> TuneServices:
    store = JsonLoopStore(path=settings.state, codec=STATE_CODEC)
    collisions = Bm25CollisionDetector(threshold=settings.collision_threshold)
    packets = FilePacketPublisher(directory=settings.state.parent.joinpath(PACKET_FOLDER))
    routers = {Judge.CLAUDE_CODE: ClaudeCodeRouterFactory(executable=settings.claude)}
    return TuneServices(
        tuning=TuningService(store=store, packets=packets, collisions=collisions),
        routing=RoutingService(store=store, routers=routers),
        publishing=PublishingService(store=store, collisions=collisions),
    )
