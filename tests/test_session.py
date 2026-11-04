import hashlib

import pytest

from atlantica_bot.errors import DiagnosticError, SceneChanged
from atlantica_bot.hunting import MARKER_NAME, control_hunting
from atlantica_bot.report import Module, Process
from atlantica_bot.session import GameSession


class FakeLiveSystem:
    def __init__(self, executable):
        self.executable = executable
        self.directory = executable.parent
        self.pid = 100
        self.owner = 0x30000000
        self.auto = 1
        self.condition = 17
        self.hunting = 0
        self.base = 0x400000
        self.mode = "rt\0".encode("utf-16le")
        self.alive = True
        self.reads = []

    def processes(self):
        return [Process(self.pid, "Atlantica.exe")] if self.alive else []

    def executable_path(self, pid):
        if not self.alive or pid != self.pid:
            raise DiagnosticError("El proceso ya no está disponible.")
        return self.executable

    def working_directory(self, pid):
        assert pid == self.pid
        return self.directory

    def main_module(self, pid, name):
        assert (pid, name) == (self.pid, "Atlantica.exe")
        return Module(self.base, 0x15865000)

    def read_memory(self, pid, address, size):
        assert pid == self.pid
        self.reads.append(address)
        values = {
            0x042C3108: self.mode,
            0x04A9290C: self.owner.to_bytes(4, "little"),
            self.owner + 0x16394: bytes([self.auto]),
            self.owner + 0x16398: self.condition.to_bytes(4, "little", signed=True),
            0x04E52C5A: bytes([self.hunting]),
        }
        result = values[address]
        assert len(result) == size
        return result


@pytest.fixture
def live(executable, monkeypatch):
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr("atlantica_bot.hunting.SUPPORTED_CLIENT_SHA256", digest)
    return FakeLiveSystem(executable)


def test_stop_stays_pending_until_client_clears_its_cached_flag(live):
    session = GameSession.connect(live)
    session.start()
    assert "Inicio solicitado" in session.snapshot().label
    live.hunting = 1
    assert "Caza habilitada" in session.snapshot().label
    control_hunting(session.directory, "stop")
    assert "Parada solicitada" in session.snapshot().label
    live.hunting = 0
    assert "Parada confirmada" in session.snapshot().label


def test_auto_battle_off_does_not_claim_cached_marker_stop_confirmed(live):
    session = GameSession.connect(live)
    live.auto = 0
    live.hunting = 1
    assert session.snapshot().label == "Auto Battle apagado"


@pytest.mark.parametrize("auto,condition", [(0, 17), (1, 0), (1, -1)])
def test_start_refuses_game_conditions_without_creating_file(live, auto, condition):
    session = GameSession.connect(live)
    live.auto, live.condition = auto, condition
    with pytest.raises(DiagnosticError):
        session.start()
    assert not (session.directory / MARKER_NAME).exists()


def test_new_pid_requires_reconnect_and_is_detected_without_fixed_pid(live):
    old_session = GameSession.connect(live)
    assert old_session.process.pid == 100
    live.pid = 202
    with pytest.raises(DiagnosticError, match="disponible"):
        old_session.snapshot()
    new_session = GameSession.connect(live)
    assert new_session.process.pid == 202
    assert new_session.snapshot().auto_battle


def test_reused_pid_for_same_executable_requires_reconnect(live):
    live.creation = 1234
    live.process_creation_time = lambda pid: live.creation
    old_session = GameSession.connect(live)
    live.creation = 5678
    with pytest.raises(DiagnosticError, match="instancia"):
        old_session.snapshot()
    assert GameSession.connect(live).creation_time == 5678


def test_reloads_dynamic_owner_pointer_on_every_snapshot(live):
    session = GameSession.connect(live)
    live.owner = 0x40000000
    live.reads.clear()
    assert session.snapshot().auto_battle
    assert 0x40016394 in live.reads
    assert 0x30016394 not in live.reads


def test_process_exit_is_unknown_not_a_successful_stop(live):
    session = GameSession.connect(live)
    live.alive = False
    with pytest.raises(DiagnosticError, match="disponible"):
        session.snapshot()


@pytest.mark.parametrize("base,mode", [(0x500000, "rt\0".encode("utf-16le")), (0x400000, bytes(6))])
def test_refuses_unexpected_runtime_layout(live, base, mode):
    live.base, live.mode = base, mode
    with pytest.raises(DiagnosticError):
        GameSession.connect(live)


def test_directory_change_prevents_starting_in_stale_directory(live, tmp_path):
    session = GameSession.connect(live)
    live.directory = tmp_path / "other"
    live.directory.mkdir()
    with pytest.raises(DiagnosticError, match="carpeta"):
        session.start()
    assert not (session.directory / MARKER_NAME).exists()


@pytest.mark.parametrize("owner", [0, 0xFFFFFFFF])
def test_invalid_owner_is_not_dereferenced(live, owner):
    session = GameSession.connect(live)
    live.owner = owner
    live.reads.clear()
    with pytest.raises(DiagnosticError, match="estado válido"):
        session.snapshot()
    assert live.reads == [0x04A9290C]


def test_state_pointer_change_is_transient_and_the_same_session_can_recover(live, monkeypatch):
    session = GameSession.connect(live)
    original = live.read_memory
    owner_reads = 0

    def changing(pid, address, size):
        nonlocal owner_reads
        if address == 0x04A9290C:
            owner_reads += 1
            if owner_reads == 2:
                return (0x40000000).to_bytes(4, "little")
        return original(pid, address, size)

    monkeypatch.setattr(live, "read_memory", changing)
    with pytest.raises(SceneChanged, match="durante la lectura"):
        session.snapshot()
    assert session.process.pid == 100 and session.snapshot().auto_battle


@pytest.mark.parametrize("field", ["auto", "hunting"])
def test_unstable_flags_do_not_invalidate_the_process_identity(live, field):
    session = GameSession.connect(live)
    setattr(live, field, 255)
    with pytest.raises(SceneChanged):
        session.snapshot()
    setattr(live, field, 0)
    assert not session.snapshot().hunting
