import hashlib
import json
from zipfile import ZipFile

import pytest

from atlantica_bot.capture import (
    ANCHOR_ADDRESS,
    ANCHOR_BYTES,
    CODE_BLOCKS,
    COMBAT_CODE_BLOCKS,
    COMBAT_READONLY_BLOCKS,
    export_code_context,
)
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import MARKER_NAME, HuntingResult
from atlantica_bot.report import Process
from atlantica_bot.session import GameSession, LiveState
from atlantica_bot.world import GridPosition, LocalState, Observation


class CaptureSystem:
    def __init__(self):
        self.reads = []
        self.anchor = ANCHOR_BYTES
        self.short = False
        self.zero = False
        self.unsupported_table = False
        self.short_combat = False
        self.short_readonly = False

    def read_memory(self, pid, address, size):
        assert pid == 123
        self.reads.append((address, size))
        if address == ANCHOR_ADDRESS:
            return self.anchor
        if address == 0x04A9290C:
            return (0x30000000).to_bytes(4, "little")
        if address == 0x30000000:
            table = 0 if self.unsupported_table else 0x042A0000
            return table.to_bytes(4, "little")
        if address == 0x30000B98:
            return (2).to_bytes(4, "little", signed=True)
        if address == 0x042A0064:
            return (0x00500010).to_bytes(4, "little")
        if (address, size) == (0x00500000, 0x2000):
            return b"\x90" * size
        assert (address, size) in [
            (address, size)
            for _, address, size in CODE_BLOCKS + COMBAT_CODE_BLOCKS + COMBAT_READONLY_BLOCKS
        ]
        if self.short_combat and address == COMBAT_CODE_BLOCKS[0][1]:
            return bytes(size - 1)
        if self.short_readonly and address == COMBAT_READONLY_BLOCKS[0][1]:
            return bytes(size - 1)
        if self.short:
            return bytes(size - 1)
        return bytes(size) if self.zero else bytes([0x90]) * size


@pytest.fixture
def session(executable, monkeypatch):
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr("atlantica_bot.hunting.SUPPORTED_CLIENT_SHA256", digest)
    session = GameSession(
        CaptureSystem(), Process(123, "Atlantica.exe"), executable, executable.parent
    )
    monkeypatch.setattr(
        session, "snapshot", lambda: LiveState(False, 17, False, HuntingResult(False, False, False))
    )
    return session


def test_exports_only_bounded_code_and_manifest_with_auto_battle_off(session, tmp_path):
    output = tmp_path / "context.zip"
    export_code_context(session, output)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(CODE_BLOCKS) + 2
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["state_at_start"]["auto_battle"] is False
        assert str(session.directory) not in json.dumps(manifest)
        assert sum(block["size"] for block in manifest["blocks"]) == 100 * 1024
        assert manifest["dispatch_resolution"] == {
            "owner_context_code": 2,
            "status": "captured",
            "function_address": "00500010",
        }
        for block in manifest["blocks"]:
            data = archive.read(block["file"])
            assert len(data) == block["size"]
            assert hashlib.sha256(data).hexdigest() == block["sha256"]
    assert not (session.directory / MARKER_NAME).exists()


def battle_observation(*, active=True, native=False, pid=123, created=777):
    return Observation(
        pid,
        created,
        2,
        GridPosition(127, 35, 72),
        native,
        LocalState(33, 0 if active else -1, -1, 20496),
    )


def test_combat_export_contains_fixed_code_dependencies_readonly_tables_and_controls(
    session, tmp_path, monkeypatch
):
    session.creation_time = 777
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    output = tmp_path / "battle.zip"
    export_code_context(session, output, include_combat=True)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["schema_version"] == 4 and manifest["purpose"] == "battle_turn_diagnostic"
        assert sum(b["size"] for b in manifest["blocks"]) == 492 * 1024
        assert len(archive.namelist()) == (
            len(CODE_BLOCKS) + len(COMBAT_CODE_BLOCKS) + len(COMBAT_READONLY_BLOCKS) + 2
        )
        for block in manifest["blocks"]:
            data = archive.read(block["file"])
            assert len(data) == block["size"]
            assert hashlib.sha256(data).hexdigest() == block["sha256"]
            address = int(block["address"], 16)
            if block["kind"] == "readonly_constants":
                assert 0x03F85000 <= address < address + block["size"] <= 0x044F9000
            else:
                assert block["kind"] == "code"
                assert 0x00401000 <= address < address + block["size"] <= 0x03F85000
        constants = [b for b in manifest["blocks"] if b["kind"] == "readonly_constants"]
        assert len(constants) == 1 and constants[0]["size"] == 8 * 1024
    combat = manifest["combat"]
    assert combat["before"]["local"]["context_a"] == combat["after"]["local"]["context_a"] == 0
    assert combat["reported_controls"]["magic_shortcuts"] == list("QWERT")
    assert combat["reported_controls"]["loot"] == "X"
    assert not combat["turn_state_verified"] and not combat["turn_execution_available"]
    assert str(session.directory) not in json.dumps(manifest)
    assert not (session.directory / MARKER_NAME).exists()


def test_incomplete_method_tables_are_not_saved_as_a_complete_battle_capture(
    session, tmp_path, monkeypatch
):
    session.creation_time = 777
    session.system.short_readonly = True
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError, match="incompleta"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


@pytest.mark.parametrize(
    "sample",
    [
        battle_observation(active=False),
        battle_observation(native=True),
        battle_observation(pid=999),
        battle_observation(created=888),
    ],
)
def test_combat_export_rejects_wrong_scene_mode_or_instance_before_code_reads(
    session, tmp_path, monkeypatch, sample
):
    session.creation_time = 777
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: sample)
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError):
        export_code_context(session, output, include_combat=True)
    assert not output.exists() and session.system.reads == []


def test_battle_ending_during_export_does_not_create_mislabelled_archive(
    session, tmp_path, monkeypatch
):
    session.creation_time = 777
    samples = iter((battle_observation(), battle_observation(active=False)))
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: next(samples))
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError, match="combate cambió"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


def test_incomplete_battle_code_is_not_saved(session, tmp_path, monkeypatch):
    session.creation_time = 777
    session.system.short_combat = True
    monkeypatch.setattr("atlantica_bot.capture.observe_scene", lambda _: battle_observation())
    output = tmp_path / "battle.zip"
    with pytest.raises(DiagnosticError, match="incompleta"):
        export_code_context(session, output, include_combat=True)
    assert not output.exists()


def test_unsupported_dynamic_table_is_reported_without_exporting_arbitrary_memory(
    session, tmp_path
):
    session.system.unsupported_table = True
    output = tmp_path / "context.zip"
    export_code_context(session, output)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["dispatch_resolution"]["status"] == "unavailable"
        assert len(archive.namelist()) == len(CODE_BLOCKS) + 1


def test_existing_output_is_not_overwritten(session, tmp_path):
    output = tmp_path / "existing.zip"
    output.write_bytes(b"user file")
    with pytest.raises(FileExistsError):
        export_code_context(session, output)
    assert output.read_bytes() == b"user file"


def test_export_includes_same_instance_history_without_profile_names_or_arbitrary_fields(
    session, tmp_path
):
    session.creation_time = 777
    report = {
        "pid": 123,
        "detector": {"instance_creation_time": 777},
        "events": [{"event": "attack_not_confirmed", "elapsed_seconds": 30}],
        "target_history": [{"slot": 6, "identity": [14801, 67723769, 0]}],
        "native_attack": {"enabled": True, "requests": 1, "search_radius": 60},
        "profile": {"name": "private-mercenary-label"},
        "directory": "private-installation-path",
    }
    output = tmp_path / "context.zip"
    export_code_context(session, output, bot_context=report)
    with ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["bot_context"]["events"] == report["events"]
    assert manifest["bot_context"]["target_history"] == report["target_history"]
    assert manifest["bot_context"]["native_attack"] == report["native_attack"]
    assert "private-mercenary-label" not in json.dumps(manifest)
    assert "private-installation-path" not in json.dumps(manifest)


@pytest.mark.parametrize("pid,created", [(999, 777), (123, 888)])
def test_foreign_context_is_rejected_before_code_read_or_file_creation(
    session, tmp_path, pid, created
):
    session.creation_time = 777
    output = tmp_path / "context.zip"
    with pytest.raises(DiagnosticError, match="otra instancia"):
        export_code_context(
            session,
            output,
            bot_context={
                "pid": pid,
                "detector": {"instance_creation_time": created},
            },
        )
    assert not output.exists() and session.system.reads == []


@pytest.mark.parametrize("failure", ["anchor", "short", "zero"])
def test_bad_or_incomplete_memory_never_creates_an_archive(session, tmp_path, failure):
    if failure == "anchor":
        session.system.anchor = bytes(len(ANCHOR_BYTES))
    else:
        setattr(session.system, failure, True)
    output = tmp_path / "context.zip"
    with pytest.raises(DiagnosticError):
        export_code_context(session, output)
    assert not output.exists()


def test_process_exit_during_capture_does_not_leave_a_valid_report(session, tmp_path, monkeypatch):
    def snapshot():
        if session.system.reads:
            raise DiagnosticError("El cliente se cerró durante la lectura.")
        return LiveState(False, 17, False, HuntingResult(False, False, False))

    monkeypatch.setattr(session, "snapshot", snapshot)
    output = tmp_path / "context.zip"
    with pytest.raises(DiagnosticError, match="cerró"):
        export_code_context(session, output)
    assert not output.exists()


def test_changed_build_is_rejected_before_reading_code(session, tmp_path):
    session.executable.write_bytes(b"different client")
    with pytest.raises(DiagnosticError, match="compilación"):
        export_code_context(session, tmp_path / "context.zip")
    assert session.system.reads == []
