import hashlib
import json
from zipfile import ZipFile

import pytest

from atlantica_bot.capture import ANCHOR_ADDRESS, ANCHOR_BYTES, CODE_BLOCKS, export_code_context
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import MARKER_NAME, HuntingResult
from atlantica_bot.report import Process
from atlantica_bot.session import GameSession, LiveState


class CaptureSystem:
    def __init__(self):
        self.reads = []
        self.anchor = ANCHOR_BYTES
        self.short = False
        self.zero = False
        self.unsupported_table = False

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
        assert (address, size) in [(address, size) for _, address, size in CODE_BLOCKS]
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
        assert sum(block["size"] for block in manifest["blocks"]) == 48 * 1024
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
