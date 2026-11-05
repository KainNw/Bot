import struct
from types import SimpleNamespace

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.identity import NAME_ANCHORS, NAME_OFFSET, MainIdentity, read_main_identity
from atlantica_bot.world import OWNER_ADDRESS


class IdentityMemory:
    owner, world, actor, info = 0x10000000, 0x20000000, 0x30000000, 0x40000000

    def __init__(self):
        self.data, self.created, self.reads = {}, {123: 777, 456: 888}, []
        self.after_read = None
        for pid, name in ((123, "MainUno"), (456, "MainDos")):
            for address, data in NAME_ANCHORS:
                self.write(pid, address, data)
            for address, value in (
                (OWNER_ADDRESS, self.owner),
                (self.owner + 0xB98, 2),
                (self.owner + 0x828, self.world),
                (self.world + 0x2C, self.actor),
                (self.actor + 0x200, 1),
                (self.actor + 0x2C, self.world),
                (self.actor + 0x30, self.info),
            ):
                self.word(pid, address, value)
            self.write(pid, self.actor + 0x204, struct.pack("<III", 2075, 70000000 + pid, 0))
            self.name(pid, name)

    def write(self, pid, address, data):
        self.data.update({(pid, address + index): byte for index, byte in enumerate(data)})

    def word(self, pid, address, value):
        self.write(pid, address, struct.pack("<I", value))

    def name(self, pid, value):
        self.write(pid, self.info + NAME_OFFSET, value.encode("utf-16le").ljust(48, b"\0"))

    def process_creation_time(self, pid):
        return self.created[pid]

    def read_memory(self, pid, address, size):
        self.reads.append((pid, address, size))
        try:
            result = bytes(self.data[pid, address + index] for index in range(size))
        except KeyError as exc:
            raise DiagnosticError("Fixture memory unavailable") from exc
        if self.after_read:
            self.after_read(pid, address, size)
        return result


@pytest.fixture
def session():
    return SimpleNamespace(
        system=IdentityMemory(), process=SimpleNamespace(pid=123), creation_time=777
    )


def test_name_belongs_to_local_slot_one_and_selected_instance(session):
    result = read_main_identity(session)
    assert result == MainIdentity(123, 777, session.system.actor, (2075, 70000123, 0), "MainUno")
    assert all(pid == 123 for pid, _, _ in session.system.reads)
    assert max(size for _, _, size in session.system.reads) == 48
    session.process.pid, session.creation_time = 456, 888
    assert read_main_identity(session).name == "MainDos"


@pytest.mark.parametrize("name", ["Héroe_12", "戦士1", "Main Uno", "A" * 23])
def test_accepts_terminated_printable_unicode_names(session, name):
    session.system.name(123, name)
    assert read_main_identity(session).name == name


@pytest.mark.parametrize("name", ["", " A", "A ", "A\nB", "A\u202eB", "!!!", "A" * 24])
def test_malformed_name_is_not_displayed_as_a_detected_main(session, name):
    session.system.name(123, name)
    with pytest.raises(DiagnosticError):
        read_main_identity(session)


def test_invalid_utf16_is_rejected(session):
    session.system.write(123, session.system.info + NAME_OFFSET, b"\x00\xd8" + bytes(46))
    with pytest.raises(DiagnosticError):
        read_main_identity(session)


def test_does_not_read_an_unverified_name_route(session):
    address, _ = NAME_ANCHORS[0]
    session.system.write(123, address, b"\xcc")
    with pytest.raises(DiagnosticError, match="ruta del nombre"):
        read_main_identity(session)
    assert all(
        address != session.system.info + NAME_OFFSET for _, address, _ in session.system.reads
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("scene", 0),
        ("slot", 2),
        ("backlink", 0x20010000),
        ("info", 0),
        ("serial", 0),
    ],
)
def test_login_and_nonlocal_objects_do_not_supply_a_main_name(session, field, value):
    memory = session.system
    address = {
        "scene": memory.owner + 0xB98,
        "slot": memory.actor + 0x200,
        "backlink": memory.actor + 0x2C,
        "info": memory.actor + 0x30,
        "serial": memory.actor + 0x208,
    }[field]
    memory.word(123, address, value)
    with pytest.raises(DiagnosticError):
        read_main_identity(session)


@pytest.mark.parametrize("change", ["name", "actor_identity", "info", "process"])
def test_changes_between_reads_cannot_produce_a_mixed_identity(session, change):
    memory = session.system

    def mutate(pid, address, size):
        if address != memory.info + NAME_OFFSET:
            return
        memory.after_read = None
        if change == "name":
            memory.name(pid, "OtroMain")
        elif change == "actor_identity":
            memory.word(pid, memory.actor + 0x208, 999999)
        elif change == "info":
            memory.word(pid, memory.actor + 0x30, memory.info + 0x1000)
        else:
            memory.created[pid] += 1

    memory.after_read = mutate
    with pytest.raises(DiagnosticError):
        read_main_identity(session)


def test_reused_pid_is_rejected_before_reading_any_memory(session):
    session.system.created[123] += 1
    with pytest.raises(DiagnosticError, match="instancia"):
        read_main_identity(session)
    assert session.system.reads == []
