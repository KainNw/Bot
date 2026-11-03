import struct
from types import SimpleNamespace

import pytest

from atlantica_bot.battle_context import (
    CLIENT_OBJECT_ANCHOR,
    CONTEXT_ANCHOR,
    MANAGER_DISPATCH_ANCHOR,
    MEMBER_ANCHOR,
    read_normal_battle,
)
from atlantica_bot.combat import CombatDetector
from atlantica_bot.errors import DiagnosticError, SceneChanged
from atlantica_bot.world import GridPosition, LocalState, Observation


class Memory:
    def __init__(self):
        self.data = {}
        self.reads = []
        self.context_reads = 0
        self.change_context = False

    def put(self, address, data):
        self.data.update({address + i: value for i, value in enumerate(data)})

    def word(self, address, value):
        self.put(address, struct.pack("<I", value))

    def read_memory(self, pid, address, size):
        assert pid == 123
        self.reads.append((address, size))
        if address == 0x600008:
            self.context_reads += 1
            if self.change_context and self.context_reads > 1:
                return struct.pack("<I", 0x700100)
        try:
            return bytes(self.data[address + i] for i in range(size))
        except KeyError as exc:
            raise DiagnosticError("Lectura incompleta simulada") from exc


@pytest.fixture
def normal(monkeypatch):
    memory = Memory()
    memory.put(0x431769, CONTEXT_ANCHOR)
    memory.put(0x4ED38B, MEMBER_ANCHOR)
    memory.put(0x50064F, MANAGER_DISPATCH_ANCHOR)
    memory.put(0x4FDDD7, CLIENT_OBJECT_ANCHOR)
    memory.word(0x4A9290C, 0x300000)
    memory.word(0x300828, 0x400000)
    memory.word(0x40002C, 0x500000)
    memory.word(0x500200, 1)
    memory.word(0x50002C, 0x400000)
    memory.word(0x500318, 0)
    memory.word(0x500254, 0xFFFFFFFF)
    memory.word(0x30091C, 0x600000)
    memory.word(0x600000, 0x04303000)
    memory.word(0x600008, 0x700000)
    memory.word(0x700000, 0x50100001)
    memory.word(0x300000 + 0x16358, 0x900000)
    memory.word(0x900000, 0x04304000)
    memory.word(0x300830, 0x800000)
    memory.put(0x800000, struct.pack("<II", 0x1000000, 450))
    memory.word(0x500030, 0x10215B8)
    memory.put(0x500204, struct.pack("<III", 1001, 543210, 0))
    for slot in range(9):
        member = 0x10215B8 + 0x4108 + slot * 0x488
        memory.word(member + 8, 1001 + slot if slot != 8 else 0)
        memory.put(member + 0x4C, struct.pack("<ii", 100 - slot, 50 - slot))
    observation = Observation(
        123, 777, 2, GridPosition(127, 39, 72), False, LocalState(33, 0, -1, 20496)
    )
    monkeypatch.setattr(
        "atlantica_bot.battle_context.CombatDetector.for_supported_session",
        lambda _: CombatDetector(123, 777, "local_context"),
    )
    monkeypatch.setattr("atlantica_bot.battle_context.observe_scene", lambda _: observation)
    session = SimpleNamespace(system=memory, process=SimpleNamespace(pid=123), creation_time=777)
    return session, memory


def test_normal_context_follows_observed_a_path_and_reads_nine_bounded_member_records(normal):
    session, memory = normal
    result = read_normal_battle(session)
    assert (result.index, result.manager, result.context) == (0, 0x600000, 0x700000)
    assert result.actor_identity == (1001, 543210, 0)
    assert result.method_table_candidate == 0x04303000
    assert result.context_word == 0x50100001
    assert result.client_object == 0x900000
    assert result.client_method_table_candidate == 0x04304000
    assert len(result.members) == 9
    assert result.members[1].kind_id == 1002
    assert result.members[8].kind_id == 0
    assert result.members[1].value_4c == 99
    report = result.summary()
    assert report["route"] == "local_context_a"
    assert not report["turn_state_verified"] and not report["turn_execution_available"]
    assert not report["member_values_semantics_verified"]
    assert not any(address == 0x300000 + 0x16360 for address, _ in memory.reads)


@pytest.mark.parametrize("index,other", [(0xFFFFFFFF, 0), (128, 0xFFFFFFFF), (0, 0)])
def test_unsupported_or_ambiguous_context_does_not_follow_an_unverified_pointer(
    normal, index, other
):
    session, memory = normal
    memory.word(0x500318, index)
    memory.word(0x500254, other)
    with pytest.raises(DiagnosticError):
        read_normal_battle(session)
    assert (0x30091C, 4) not in memory.reads


def test_reused_context_pointer_is_not_reported_as_a_coherent_snapshot(normal):
    session, memory = normal
    memory.change_context = True
    with pytest.raises(SceneChanged, match="combate cambió"):
        read_normal_battle(session)


def test_member_data_must_belong_to_local_actor_and_native_member_collection(normal):
    session, memory = normal
    memory.word(0x500030, 0x10215BC)
    result = read_normal_battle(session)
    assert result.context == 0x700000 and not result.members
    assert "información de los mercenarios" in result.member_read_error
    assert result.summary()["members_status"] == "unavailable"


@pytest.mark.parametrize("address", [0x431769, 0x4ED38B, 0x50064F, 0x4FDDD7])
def test_changed_code_prevents_following_the_layout(normal, address):
    session, memory = normal
    memory.put(address, b"\x00")
    with pytest.raises(DiagnosticError, match="código analizado"):
        read_normal_battle(session)
    assert (0x30091C, 4) not in memory.reads


def test_foreign_instance_observation_is_rejected_before_memory_read(normal, monkeypatch):
    session, memory = normal
    monkeypatch.setattr(
        "atlantica_bot.battle_context.observe_scene",
        lambda _: Observation(999, 888, 2, GridPosition(127, 39, 72)),
    )
    with pytest.raises(DiagnosticError):
        read_normal_battle(session)
    assert not memory.reads


def test_incomplete_member_read_does_not_return_a_partially_labelled_roster(normal):
    session, memory = normal
    del memory.data[0x10215B8 + 0x4108 + 8]
    result = read_normal_battle(session)
    assert not result.members and "incompleta" in result.member_read_error
    assert result.context == 0x700000


def test_mutable_collection_data_word_is_not_used_as_the_context_identity(normal, monkeypatch):
    session, memory = normal
    original = memory.read_memory
    versions = iter((0, 0x120000))

    def read(pid, address, size):
        if address == 0x900000:
            return struct.pack("<I", next(versions))
        return original(pid, address, size)

    monkeypatch.setattr(memory, "read_memory", read)
    before, after = read_normal_battle(session), read_normal_battle(session)
    assert (
        before.client_method_table_candidate == 0
        and after.client_method_table_candidate == 0x120000
    )
    assert before.binding() == after.binding()
