import hashlib
import struct

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import MARKER_NAME, HuntingResult
from atlantica_bot.report import Process
from atlantica_bot.session import GameSession, LiveState
from atlantica_bot.world import (
    INDEX_COUNT_OFFSET,
    INDEX_VECTOR_OFFSET,
    OWNER_ADDRESS,
    SLOT_COUNT,
    TABLE_OFFSET,
    observe_scene,
    scan_world,
)


class WorldMemory:
    owner = 0x10000000
    manager = 0x20000000
    index = 0x21000000
    vector = 0x22000000

    def __init__(self):
        self.memory = {}
        self.after_read = None
        self.active_slots = []
        self.write(OWNER_ADDRESS, struct.pack("<I", self.owner))
        self.write(0x045079EC, struct.pack("<f", 20))
        self.write(self.owner + 0xB98, struct.pack("<i", 2))
        self.write(self.owner + 0x828, struct.pack("<I", self.manager))
        self.write(self.manager + TABLE_OFFSET, bytes(SLOT_COUNT * 4))
        self.write(self.manager + 0x24, struct.pack("<I", self.index))
        self.write(self.index, struct.pack("<I", 0x5BCC))
        self.write(self.index + 12, bytes(SLOT_COUNT * 12))
        self.write(self.index + INDEX_VECTOR_OFFSET, struct.pack("<II", self.vector, 0))
        self.write(self.vector, bytes(0x5BCC * 4))
        self.actor(1, 100, 8, 10, 20)

    def write(self, address, data):
        self.memory.update({address + i: byte for i, byte in enumerate(data)})

    def activate(self, slot):
        if slot not in self.active_slots:
            self.active_slots.append(slot)
        self.write(self.vector, struct.pack(f"<{len(self.active_slots)}I", *self.active_slots))
        self.write(self.index + INDEX_COUNT_OFFSET, struct.pack("<I", len(self.active_slots)))
        self.write(self.index + (slot + 1) * 12, struct.pack("<I", 1000 + slot))

    def actor(self, slot, kind, map_id, x, y, *, active=True):
        actor = 0x30000000 + slot * 0x10000
        info = 0x40000000 + slot * 0x10000
        self.write(actor, bytes(0x1100))
        self.write(self.manager + TABLE_OFFSET + slot * 4, struct.pack("<I", actor))
        self.write(actor + 0x200, struct.pack("<II", slot, kind))
        self.write(actor + 0x30, struct.pack("<I", info))
        self.write(actor + 0x318, struct.pack("<i", -1))
        self.write(actor + 0x254, struct.pack("<i", -1))
        self.write(info + 0xCA, struct.pack("<hhh", map_id, x, y))
        self.write(actor + 0xB8C, struct.pack("<fff", x, 0, y))
        if active:
            self.activate(slot)
        return actor, info

    def read_memory(self, pid, address, size):
        assert pid == 123
        try:
            data = bytes(self.memory[address + i] for i in range(size))
        except KeyError as exc:
            raise DiagnosticError("Memoria no disponible.") from exc
        if self.after_read is not None:
            self.after_read(address, size)
        return data


@pytest.fixture
def session(executable, monkeypatch):
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr("atlantica_bot.hunting.SUPPORTED_CLIENT_SHA256", digest)
    memory = WorldMemory()
    result = GameSession(memory, Process(123, "Atlantica.exe"), executable, executable.parent)
    monkeypatch.setattr(
        result, "snapshot", lambda: LiveState(False, 0, False, HuntingResult(False, False, False))
    )
    return result


def test_reads_and_ranks_candidates_with_auto_battle_off_and_zero_counter(session):
    session.system.actor(7, 4000, 8, 12, 25)
    session.system.actor(8, 4100, 8, 13, 20)
    view = scan_world(session)
    assert (view.player.map_id, view.player.x, view.player.y) == (8, 10, 20)
    assert [(c.slot, c.grid_distance) for c in view.candidates] == [(8, 3), (7, 7)]
    assert view.observed_entries == 2
    assert view.active_index_entries == 3
    assert view.range_limit_squared == 20
    assert view.candidates[0].distance_squared == 9
    assert not (session.directory / MARKER_NAME).exists()
    assert view.summary()["attack_eligibility_fully_validated"] is False


@pytest.mark.parametrize(
    "reason", ["different_map", "kind_range", "state", "flag", "status_a", "status_b"]
)
def test_known_selector_rejections_are_not_returned_as_candidates(session, reason):
    memory = session.system
    actor, info = memory.actor(7, 4000, 8, 12, 25)
    if reason == "different_map":
        memory.write(info + 0xCA, struct.pack("<h", 9))
    elif reason == "kind_range":
        memory.write(actor + 0x204, struct.pack("<I", 100))
    elif reason == "state":
        memory.write(actor + 0x38, b"\x22")
    elif reason == "flag":
        memory.write(actor + 0x388, b"\x10")
    else:
        memory.write(actor + (0x318 if reason == "status_a" else 0x254), struct.pack("<i", 0))
    view = scan_world(session)
    assert view.candidates == ()
    assert sum(dict(view.rejected_by).values()) == 1


def test_unknown_scene_is_not_reported_as_an_empty_valid_world(session):
    memory = session.system
    memory.write(memory.owner + 0xB98, struct.pack("<i", 3))
    view = scan_world(session)
    assert view.player is None
    assert view.scene_code == 3


def test_observer_does_not_read_map_actor_objects_during_battle(session):
    memory = session.system
    memory.write(memory.owner + 0xB98, struct.pack("<i", 1))
    memory.write(memory.owner + 0x828, bytes(4))
    result = observe_scene(session)
    assert result.scene_code == 1 and result.player is None
    assert result.pid == session.process.pid and not result.native_active


def test_observer_reads_local_context_even_when_scene_code_remains_two(session):
    memory = session.system
    actor = 0x30010000
    memory.write(actor + 0x318, struct.pack("<i", 7))
    memory.write(actor + 0x254, struct.pack("<i", 3))
    result = observe_scene(session)
    assert result.scene_code == 2
    assert result.local.context_a == 7 and result.local.context_b == 3
    assert result.summary()["local"]["context_a"] == 7


def test_observer_rejects_local_context_changed_during_observation(session):
    memory = session.system
    address = 0x30010000 + 0x318

    def change_context(read_address, size):
        if read_address == address:
            memory.write(address, struct.pack("<i", 7))

    memory.after_read = change_context
    with pytest.raises(DiagnosticError, match="cambió durante la observación"):
        observe_scene(session)


def test_optional_link_diagnostic_can_be_unavailable_without_losing_valid_context(session):
    session.system.write(0x30010000 + 0x14, struct.pack("<I", 0x55550000))
    result = observe_scene(session)
    assert result.local.context_a == result.local.context_b == -1
    assert result.local.linked_state is None


def test_navigation_observation_reads_route_destination_and_flags(session):
    actor = 0x30010000
    session.system.write(actor + 0x1012, bytes([1, 0]) + struct.pack("<Ihhh", 1234, 8, 14, 25))
    session.system.write(actor + 0xB78, bytes([1]))
    result = observe_scene(session, include_navigation=True)
    assert result.navigation.key == (actor, 1234, 8, 14, 25)
    assert result.navigation.active and result.navigation.moving


@pytest.mark.parametrize("active_raw,moving_raw", [(0, 255), (2, 0), (255, 2), (1, 255)])
def test_noncanonical_navigation_bytes_are_preserved_without_dropping_observation(
    session, active_raw, moving_raw
):
    actor = 0x30010000
    session.system.write(
        actor + 0x1012, bytes([active_raw, 0]) + struct.pack("<Ihhh", 1234, -1, 0, 0)
    )
    session.system.write(actor + 0xB78, bytes([moving_raw]))
    observation = observe_scene(session, include_navigation=True)
    assert observation.scene_code == 2 and observation.player.map_id == 8
    assert observation.navigation.active is (active_raw == 1)
    assert observation.navigation.moving is (False if moving_raw == 0 else None)
    assert observation.summary()["navigation"]["active_raw"] == active_raw
    assert observation.summary()["navigation"]["moving_raw"] == moving_raw


def test_moving_observation_allows_grid_progress_but_keeps_scene_validation(session):
    info = 0x40010000
    memory = session.system

    def move_after_read(address, size):
        if address == info + 0xCA:
            memory.write(info + 0xCA, struct.pack("<hhh", 8, 11, 20))

    memory.after_read = move_after_read
    result = observe_scene(session, allow_player_movement=True)
    assert result.player.map_id == 8
    memory.write(info + 0xCA, struct.pack("<hhh", 8, 10, 20))
    with pytest.raises(DiagnosticError, match="cambió durante la observación"):
        observe_scene(session)


def test_nonfinite_range_is_not_presented_as_attackable(session):
    session.system.write(0x045079EC, struct.pack("<f", float("nan")))
    assert scan_world(session).range_limit_squared is None


def test_unreadable_actor_keeps_partial_result_and_counts_failure(session):
    memory = session.system
    memory.actor(7, 4000, 8, 12, 25)
    memory.write(memory.manager + TABLE_OFFSET + 8 * 4, struct.pack("<I", 0x55550000))
    memory.activate(8)
    view = scan_world(session)
    assert len(view.candidates) == 1
    assert view.read_errors == 1


def test_reused_slot_is_discarded(session):
    memory = session.system
    _, info = memory.actor(7, 4000, 8, 12, 25)

    def change_slot(address, size):
        if address == info + 0xCA:
            memory.write(memory.manager + TABLE_OFFSET + 7 * 4, struct.pack("<I", 0))

    memory.after_read = change_slot
    view = scan_world(session)
    assert view.candidates == ()
    assert view.changed_entries == 1


def test_inactive_table_pointers_are_not_dereferenced_or_reported_as_changes(session):
    memory = session.system
    memory.actor(7, 4000, 8, 12, 25)
    memory.actor(8, 4100, 8, 11, 20, active=False)
    memory.write(memory.manager + TABLE_OFFSET + 9 * 4, struct.pack("<I", 0xDEADC000))
    view = scan_world(session)
    assert [candidate.slot for candidate in view.candidates] == [7]
    assert view.inactive_entries == 2
    assert view.changed_entries == view.read_errors == 0
    assert view.observed_entries == 1


def test_stable_slot_mismatch_is_not_a_detected_change(session):
    memory = session.system
    actor, _ = memory.actor(7, 4000, 8, 12, 25)
    memory.write(actor + 0x200, struct.pack("<I", 123))
    view = scan_world(session)
    assert view.candidates == ()
    assert dict(view.rejected_by) == {"slot_mismatch": 1}
    assert view.changed_entries == 0


@pytest.mark.parametrize("problem", ["count", "duplicate", "range", "membership"])
def test_malformed_or_inconsistent_active_index_is_rejected(session, problem):
    memory = session.system
    if problem == "count":
        memory.write(memory.index + INDEX_COUNT_OFFSET, struct.pack("<I", 0x5BCD))
    elif problem == "duplicate":
        memory.write(memory.index + INDEX_COUNT_OFFSET, struct.pack("<I", 2))
        memory.write(memory.vector, struct.pack("<II", 1, 1))
    elif problem == "range":
        memory.write(memory.vector, struct.pack("<I", 0x5BCC))
    else:
        memory.write(memory.index + 24, bytes(4))
    with pytest.raises(DiagnosticError, match="índices activos"):
        scan_world(session)


def test_same_size_active_list_change_discards_whole_scan(session):
    memory = session.system
    _, info = memory.actor(7, 4000, 8, 12, 25)
    memory.actor(8, 4100, 8, 13, 20, active=False)

    def change_list(address, size):
        if address == info + 0xCA:
            memory.write(memory.vector + 4, struct.pack("<I", 8))
            memory.write(memory.index + 9 * 12, struct.pack("<I", 1008))

    memory.after_read = change_list
    with pytest.raises(DiagnosticError, match="índices activos cambiaron"):
        scan_world(session)


def test_active_entries_outside_validated_attack_range_are_counted_without_reading(session):
    session.system.activate(500)
    view = scan_world(session)
    assert view.out_of_scope_entries == 1
    assert view.active_index_entries == 2
    assert view.observed_entries == view.read_errors == 0


def test_owner_change_discards_whole_scan(session):
    memory = session.system

    def change_scene(address, size):
        if address == memory.manager + TABLE_OFFSET:
            memory.write(OWNER_ADDRESS, struct.pack("<I", 0x77770000))

    memory.after_read = change_scene
    with pytest.raises(DiagnosticError, match="escena cambió"):
        scan_world(session)


def test_changed_build_is_rejected_before_reading_world(session):
    session.executable.write_bytes(b"updated client")
    with pytest.raises(DiagnosticError, match="compilación"):
        scan_world(session)
