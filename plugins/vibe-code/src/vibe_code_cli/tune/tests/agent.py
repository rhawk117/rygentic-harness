from dataclasses import dataclass, field

import msgspec

from vibe_code_cli.tune.schemas import JudgePacket, JudgeWork, ProposePacket
from vibe_code_cli.tune.services import TuningService
from vibe_code_cli.tune.tests.fakes import MemoryPacketPublisher, overlapping_skills, words

MAX_STEPS = 60

type JudgeAnswer = dict[str, list[str]]


def union_of_words(texts: tuple[str, ...]) -> frozenset[str]:
    return frozenset(word for text in texts for word in words(text))


@dataclass(slots=True, kw_only=True)
class ScriptedAgent:
    judged_requests: list[str] = field(default_factory=list)
    proposals: list[ProposePacket] = field(default_factory=list)

    def judge(self, packet: JudgePacket) -> JudgeAnswer:
        self.judged_requests.extend(packet.requests.values())
        return {
            key: overlapping_skills(packet.skills, request)
            for key, request in packet.requests.items()
        }

    def propose(self, packet: ProposePacket) -> str:
        self.proposals.append(packet)
        current = words(packet.current)
        gained = union_of_words(packet.missed)
        lost = union_of_words(packet.false_triggers)
        drafts = ((current | gained) - lost, current | gained, current - lost)
        tried = {packet.current, *packet.rejected}
        fresh = (f'Use for {" ".join(sorted(draft))}.' for draft in drafts)
        fallback = f'{packet.current} Attempt {len(tried)}.'
        return next((text for text in fresh if text not in tried), fallback)

    def answer_judging(
        self, work: JudgeWork, tuning: TuningService, packets: MemoryPacketPublisher
    ) -> None:
        for published in work.packets:
            answer = self.judge(packets.packets[published.packet_id])
            tuning.submit(published.packet_id, msgspec.json.encode(answer))

    def answer_proposal(self, work: ProposePacket, tuning: TuningService) -> None:
        proposal = {'description': self.propose(work)}
        tuning.submit(work.packet_id, msgspec.json.encode(proposal))

    def step(self, tuning: TuningService, packets: MemoryPacketPublisher) -> str:
        work = tuning.next_work()
        if isinstance(work, JudgeWork):
            self.answer_judging(work, tuning, packets)
        if isinstance(work, ProposePacket):
            self.answer_proposal(work, tuning)
        return work.kind

    def drive(self, tuning: TuningService, packets: MemoryPacketPublisher) -> list[str]:
        kinds: list[str] = []
        for _step in range(MAX_STEPS):
            kinds.append(self.step(tuning, packets))
            if kinds[-1] == 'done':
                break
        return kinds
