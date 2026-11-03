import struct
from dataclasses import replace
from types import SimpleNamespace

import pytest

from atlantica_bot.battle import (
    OWN_TURN_ANCHOR,
    UNIT_LOOKUP_ANCHOR,
    BattleTrial,
    read_battle_frame,
)
from atlantica_bot.battle_context import NormalBattleContext
from atlantica_bot.errors import DiagnosticError, SceneChanged


@pytest.fixture
def battle_memory(monkeypatch):
    data = {}
    control = SimpleNamespace(turn_reads=0, change_turn=False)

    def put(address, value):
        data.update({address + i: byte for i, byte in enumerate(value)})

    def word(address, value):
        put(address, struct.pack("<I", value))

    def read(pid, address, size):
        assert pid == 200
        if address == 0x706C74:
            control.turn_reads += 1
            if control.change_turn and control.turn_reads > 1:
                return struct.pack("<I", 13)
        try:
            return bytes(data[address + i] for i in range(size))
        except KeyError as exc:
            raise DiagnosticError("Lectura incompleta simulada") from exc

    context = NormalBattleContext(
        200,
        123456,
        0x500000,
        (209, 8888, 0),
        0x600000,
        0,
        0x700000,
        0x042D8AA4,
        0x10215B8,
        (),
        client_object=0x900000,
    )
    monkeypatch.setattr("atlantica_bot.battle.read_normal_battle", lambda _: context)
    put(0x5A4519, UNIT_LOOKUP_ANCHOR)
    put(0x5A2955, OWN_TURN_ANCHOR)
    word(0x6025E0, 0x900000)
    word(0x60234C, 3)
    word(0x706C5C, 0)
    word(0x706C74, 12)
    word(0x706C60, 123450)
    identities = ((209, 8888, 0), (5633, 9999, 0), (210, 3333, 0))
    put(0x7000B4, b"".join(struct.pack("<3I", *i) for i in identities) + bytes(36))
    put(0x70011A, struct.pack("<6h", 0, 1, 0, -1, -1, -1))
    word(0x50002C, 0x400000)
    word(0x4A9290C, 0x300000)
    word(0x300830, 0x800000)
    put(0x800000, struct.pack("<II", 0x1000000, 450))
    put(0x9000D4, bytes(100))
    put(0x900138, bytes(400))
    for index, world_slot, member, identity, life in (
        (1, 1, 0, identities[0], 100),
        (2, 6, 0, identities[1], 40),
        (3, 2, 0, identities[2], 100),
        (4, 6, 1, identities[1], 0),
    ):
        unit = 0xA00000 + index * 0x1000
        actor = 0x500000 + (world_slot - 1) * 0x1000
        info = 0x1000000 + world_slot * 0x215B8
        record = info + 0x4108 + member * 0x488
        put(0x9000D4 + index, b"\x01")
        word(0x900138 + index * 4, unit)
        put(unit + 4, struct.pack("<ii", world_slot, member))
        word(unit + 0x21C, info)
        word(unit + 0x230, record)
        word(unit + 0x20, 0x8000)
        put(unit + 0x508, b"\x01")
        word(0x400028 + world_slot * 4, actor)
        put(actor + 0x204, struct.pack("<3I", *identity))
        word(actor + 0x30, info)
        word(actor + 0x200, world_slot)
        word(actor + 0x2C, 0x400000)
        word(record + 8, 2318 if world_slot == 1 else 5000)
        word(record + 0x4C, life)
    session = SimpleNamespace(
        system=SimpleNamespace(read_memory=read),
        process=SimpleNamespace(pid=200),
        creation_time=123456,
    )
    return session, SimpleNamespace(put=put, word=word, data=data, control=control)


def test_battle_frame_separates_own_members_enemies_allies_and_dead_units(battle_memory):
    session, _ = battle_memory
    view = read_battle_frame(session)
    assert view.own_turn and view.phase == 3
    assert len(view.units) == 4
    assert [(u.world_slot, u.member_slot) for u in view.sources] == [(1, 1)]
    assert [(u.world_slot, u.member_slot) for u in view.enemies] == [(6, 1)]
    assert view.enemies[0].identity == (5633, 9999, 0)
    trial = BattleTrial(view, view.sources[0], view.enemies[0])
    trial.validate()
    assert trial.arguments()["turn-tick"] == 123450
    assert trial.arguments()["mercenary"] == 1
    assert not view.summary()["turn_execution_available"]
    assert not view.summary()["keyboard_slot_mapping_verified"]


def test_reused_turn_during_snapshot_is_rejected_without_partial_targets(battle_memory):
    session, memory = battle_memory
    memory.control.change_turn = True
    with pytest.raises(SceneChanged, match="turno cambió"):
        read_battle_frame(session)


def test_unit_info_alias_mismatch_invalidates_the_battle_read(battle_memory):
    session, memory = battle_memory
    memory.word(0xA02000 + 0x230, 0xA00000)
    with pytest.raises(SceneChanged, match="registro de miembro"):
        read_battle_frame(session)


def test_ambiguous_participant_identity_is_not_treated_as_a_target(battle_memory):
    session, memory = battle_memory
    memory.put(0x7000B4 + 24, struct.pack("<3I", 5633, 88888, 0))
    with pytest.raises(DiagnosticError, match="ambiguas"):
        read_battle_frame(session)


@pytest.mark.parametrize("address", [0x5A4519, 0x5A2955])
def test_changed_unit_code_rejects_the_layout_before_following_the_collection(
    battle_memory, address
):
    session, memory = battle_memory
    memory.put(address, b"\x00")
    with pytest.raises(DiagnosticError, match="código analizado"):
        read_battle_frame(session)


def test_other_group_turn_is_read_but_cannot_create_an_attack_trial(battle_memory):
    session, memory = battle_memory
    memory.word(0x706C5C, 1)
    view = read_battle_frame(session)
    assert not view.own_turn
    with pytest.raises(DiagnosticError, match="turno del grupo"):
        BattleTrial(view, view.sources[0], view.enemies[0]).validate()


def test_an_ally_can_never_be_submitted_as_the_enemy(battle_memory):
    session, _ = battle_memory
    view = read_battle_frame(session)
    ally = next(u for u in view.units if u.world_slot == 2)
    with pytest.raises(DiagnosticError, match="enemigo vivos"):
        BattleTrial(view, view.sources[0], ally).validate()


@pytest.mark.parametrize("state,flags", [(30, 0x8000), (1, 0)])
def test_busy_or_non_attacking_member_cannot_create_a_trial(battle_memory, state, flags):
    session, memory = battle_memory
    memory.put(0xA01000 + 0x508, bytes([state]))
    memory.word(0xA01000 + 0x20, flags)
    view = read_battle_frame(session)
    with pytest.raises(DiagnosticError, match="estado nativo"):
        BattleTrial(view, view.sources[0], view.enemies[0]).validate()


def test_trial_deduplication_key_does_not_change_when_only_enemy_selection_changes(battle_memory):
    session, _ = battle_memory
    view = read_battle_frame(session)
    first = BattleTrial(view, view.sources[0], view.enemies[0])
    other = replace(first.target, member_slot=3)
    second = BattleTrial(replace(view, units=(*view.units, other)), first.source, other)
    second.validate()
    assert first.key() == second.key()
