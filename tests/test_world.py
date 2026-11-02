import hashlib
import struct

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import MARKER_NAME, HuntingResult
from atlantica_bot.report import Process
from atlantica_bot.session import GameSession, LiveState
from atlantica_bot.world import OWNER_ADDRESS, SLOT_COUNT, TABLE_OFFSET, scan_world


class WorldMemory:
    owner = 0x10000000
    manager = 0x20000000

    def __init__(self):
        self.memory = {}
        self.after_read = None
        self.write(OWNER_ADDRESS, struct.pack("<I", self.owner))
        self.write(self.owner + 0xB98, struct.pack("<i", 2))
        self.write(self.owner + 0x828, struct.pack("<I", self.manager))
        self.write(self.manager + TABLE_OFFSET, bytes(SLOT_COUNT * 4))
        self.actor(1, 100, 8, 10, 20)

    def write(self, address, data):
        self.memory.update({address + i: byte for i, byte in enumerate(data)})

    def actor(self, slot, kind, map_id, x, y):
        actor = 0x30000000 + slot * 0x10000
        info = 0x40000000 + slot * 0x10000
        self.write(actor, bytes(0x400))
        self.write(self.manager + TABLE_OFFSET + slot * 4, struct.pack("<I", actor))
        self.write(actor + 0x200, struct.pack("<II", slot, kind))
        self.write(actor + 0x30, struct.pack("<I", info))
        self.write(actor + 0x318, struct.pack("<i", -1))
        self.write(actor + 0x254, struct.pack("<i", -1))
        self.write(info + 0xCA, struct.pack("<hhh", map_id, x, y))
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


def test_unreadable_actor_keeps_partial_result_and_counts_failure(session):
    memory = session.system
    memory.actor(7, 4000, 8, 12, 25)
    memory.write(memory.manager + TABLE_OFFSET + 8 * 4, struct.pack("<I", 0x55550000))
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
