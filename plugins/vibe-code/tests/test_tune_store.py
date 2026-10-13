import stat
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from operator import attrgetter
from pathlib import Path

import msgspec
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from vibe_code_cli.tune.errors import IncompatibleStateError, MalformedAnswerError
from vibe_code_cli.tune.locking import write_atomically
from vibe_code_cli.tune.store import FilePacketPublisher, JsonLoopStore, StateCodec, decode_answer
from vibe_code_cli.tune.tests.io_fakes import (
    INT64,
    SAMPLE_STATES,
    VALID_ANSWERS,
    CounterState,
    FailingRename,
    SampleAnswer,
    SamplePacket,
    SampleState,
    TornStagingFiles,
    truncated_answers,
)

FILE_SETTINGS = settings(deadline=None, max_examples=50)


class AbandonedEditError(Exception):
    pass


class TestStateCodec:
    codec = StateCodec(state_type=SampleState)

    @given(state=SAMPLE_STATES)
    def test_decode_inverts_encode(self, state: SampleState) -> None:
        assert self.codec.decode(self.codec.encode(state)) == state


class TestJsonLoopStore:
    codec = StateCodec(state_type=SampleState)

    def store_in(self, directory: Path) -> JsonLoopStore[SampleState]:
        return JsonLoopStore(path=directory.joinpath('state.json'), codec=self.codec)

    def abandon_edit(self, store: JsonLoopStore[SampleState]) -> None:
        with store.transaction() as session:
            session.read()
            raise AbandonedEditError

    @FILE_SETTINGS
    @given(states=st.lists(SAMPLE_STATES, min_size=1, max_size=3))
    def test_each_commit_is_visible_to_the_next_read(
        self, tmp_path_factory: pytest.TempPathFactory, states: list[SampleState]
    ) -> None:
        store = self.store_in(tmp_path_factory.mktemp('commits'))
        for state in states:
            with store.transaction() as session:
                session.commit(state)
            assert store.read() == state
            with store.transaction() as session:
                assert session.read() == state

    @FILE_SETTINGS
    @given(committed=SAMPLE_STATES, attempted=SAMPLE_STATES)
    def test_a_transaction_that_raises_before_commit_leaves_the_file_unchanged(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        committed: SampleState,
        attempted: SampleState,
    ) -> None:
        store = self.store_in(tmp_path_factory.mktemp('abandoned'))
        with store.transaction() as session:
            session.commit(committed)
        before = store.path.read_bytes()
        with pytest.raises(AbandonedEditError):
            self.abandon_edit(store)
        assert store.path.read_bytes() == before
        with store.transaction() as session:
            session.commit(attempted)
        assert store.read() == attempted


class TestJsonLoopStoreConcurrency:
    threads = 16
    codec = StateCodec(state_type=CounterState)

    def increment(self, store: JsonLoopStore[CounterState], start: threading.Barrier) -> None:
        start.wait()
        with store.transaction() as session:
            current = session.read()
            session.commit(CounterState(value=current.value + 1))

    def test_concurrent_increments_are_never_lost(self, tmp_path: Path) -> None:
        store = JsonLoopStore(path=tmp_path.joinpath('counter.json'), codec=self.codec)
        with store.transaction() as session:
            session.commit(CounterState(value=0))
        start = threading.Barrier(self.threads)
        with ThreadPoolExecutor(max_workers=self.threads) as pool:
            runs = [pool.submit(self.increment, store, start) for _ in range(self.threads)]
        for run in runs:
            run.result()
        assert store.read() == CounterState(value=self.threads)


class TestFilePacketPublisher:
    private_mode = 0o600
    packet_ids = st.from_regex(r'[a-z0-9][a-z0-9-]{0,15}', fullmatch=True)
    packets = st.lists(
        st.builds(SamplePacket, packet_id=packet_ids, state=SAMPLE_STATES),
        max_size=4,
        unique_by=attrgetter('packet_id'),
    )

    @FILE_SETTINGS
    @given(packets=packets)
    def test_published_files_are_private_and_decode_to_their_packet(
        self, tmp_path_factory: pytest.TempPathFactory, packets: list[SamplePacket]
    ) -> None:
        directory = tmp_path_factory.mktemp('packets').joinpath('out')
        publisher = FilePacketPublisher[SamplePacket](directory=directory)
        published = publisher.publish(packets)
        assert [file.packet_id for file in published] == [p.packet_id for p in packets]
        for file, packet in zip(published, packets, strict=True):
            path = Path(file.path)
            assert stat.S_IMODE(path.stat().st_mode) == self.private_mode
            assert msgspec.json.decode(path.read_bytes(), type=SamplePacket) == packet


class TestTruncatedState:
    def test_truncated_file_is_an_incompatible_state(self, tmp_path: Path) -> None:
        path = tmp_path.joinpath('state.json')
        path.write_bytes(b'{"value": ')
        store = JsonLoopStore(path=path, codec=StateCodec(state_type=CounterState))
        with pytest.raises(IncompatibleStateError):
            store.read()


class TestWriteAtomically:
    rewrites = st.tuples(st.binary(), st.binary())

    def target_holding(self, directory: Path, data: bytes) -> Path:
        path = directory.joinpath('state.json')
        path.write_bytes(data)
        return path

    @FILE_SETTINGS
    @given(rewrite=rewrites)
    def test_a_completed_write_leaves_exactly_the_new_bytes(
        self, tmp_path_factory: pytest.TempPathFactory, rewrite: tuple[bytes, bytes]
    ) -> None:
        old, new = rewrite
        directory = tmp_path_factory.mktemp('complete')
        path = self.target_holding(directory, old)
        write_atomically(path, new)
        assert path.read_bytes() == new
        assert list(directory.iterdir()) == [path]

    @FILE_SETTINGS
    @given(rewrite=rewrites, kept=st.integers(min_value=0, max_value=64))
    def test_a_write_failing_midway_leaves_the_old_bytes_and_no_staging_file(
        self,
        tmp_path_factory: pytest.TempPathFactory,
        rewrite: tuple[bytes, bytes],
        kept: int,
    ) -> None:
        old, new = rewrite
        directory = tmp_path_factory.mktemp('torn')
        path = self.target_holding(directory, old)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(tempfile, 'NamedTemporaryFile', TornStagingFiles(kept_bytes=kept))
            with pytest.raises(OSError, match='simulated full disk'):
                write_atomically(path, new)
        assert path.read_bytes() == old
        assert list(directory.iterdir()) == [path]

    @FILE_SETTINGS
    @given(rewrite=rewrites)
    def test_a_failed_rename_leaves_the_old_bytes_and_no_staging_file(
        self, tmp_path_factory: pytest.TempPathFactory, rewrite: tuple[bytes, bytes]
    ) -> None:
        old, new = rewrite
        directory = tmp_path_factory.mktemp('rename')
        path = self.target_holding(directory, old)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(Path, 'replace', FailingRename())
            with pytest.raises(OSError, match='simulated failed rename'):
                write_atomically(path, new)
        assert path.read_bytes() == old
        assert list(directory.iterdir()) == [path]


class TestModePreserved:
    shared_mode = 0o644

    def test_rewrite_keeps_the_target_permissions(self, tmp_path: Path) -> None:
        path = tmp_path.joinpath('SKILL.md')
        path.write_bytes(b'old')
        path.chmod(self.shared_mode)
        write_atomically(path, b'new')
        assert stat.S_IMODE(path.stat().st_mode) == self.shared_mode


class TestDecodeAnswer:
    packet_id = 'packet-7'
    json_scalars = st.none() | st.booleans() | INT64 | st.text()
    not_booleans = st.none() | INT64 | st.text() | st.lists(INT64)
    non_matching = st.one_of(
        st.recursive(json_scalars, st.lists, max_leaves=8).map(msgspec.json.encode),
        st.builds(dict, approved=not_booleans, reason=st.text()).map(msgspec.json.encode),
        st.builds(dict, reason=st.text()).map(msgspec.json.encode),
        truncated_answers(),
    )

    @given(data=non_matching)
    def test_non_matching_bytes_raise_malformed_answer(self, data: bytes) -> None:
        with pytest.raises(MalformedAnswerError, match=self.packet_id):
            decode_answer(self.packet_id, data, SampleAnswer)

    @given(data=st.binary())
    def test_arbitrary_bytes_decode_or_raise_malformed_answer(self, data: bytes) -> None:
        with suppress(MalformedAnswerError):
            assert isinstance(decode_answer(self.packet_id, data, SampleAnswer), SampleAnswer)

    @given(answer=VALID_ANSWERS)
    def test_matching_bytes_decode_to_the_answer(self, answer: SampleAnswer) -> None:
        encoded = msgspec.json.encode(answer)
        assert decode_answer(self.packet_id, encoded, SampleAnswer) == answer
