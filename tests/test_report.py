import json

import pytest

from atlantica_bot.errors import DiagnosticError, NativeError
from atlantica_bot.report import Module, Process, diagnose, save_report, select_process


class FakeSystem:
    def __init__(self, path):
        self.path = path
        self.reads = []
        self.signature = b"MZ"
        self.denied = False

    def processes(self):
        return [Process(123, "Atlantica.exe"), Process(456, "Other.exe")]

    def executable_path(self, pid):
        assert pid == 123
        return self.path

    def file_version(self, path):
        assert path == self.path
        return "1.2.3.4"

    def main_module(self, pid, name):
        assert (pid, name) == (123, "Atlantica.exe")
        if self.denied:
            raise DiagnosticError(f"Denied {self.path}")
        return Module(0x140000000, 0x10000)

    def read_memory(self, pid, address, size):
        self.reads.append((pid, address, size))
        return self.signature


def test_report_checks_only_header_and_does_not_include_installation_path(executable):
    system = FakeSystem(executable)
    report = diagnose(system, name="atlantica.EXE")
    assert system.reads == [(123, 0x140000000, 2)]
    assert report["memory_read"] == {"status": "verified", "bytes_verified": 2}
    assert report["executable_on_disk"]["file_version"] == "1.2.3.4"
    assert report["main_module"]["base_address"] == "0x140000000"
    assert report["attack_automation"] == "not_exercised_by_diagnostic"
    assert report["game_mapping"] == "not_configured"
    assert str(executable.parent) not in json.dumps(report)


def test_access_denial_produces_partial_report_without_private_error_text(executable):
    system = FakeSystem(executable)
    system.denied = True
    report = diagnose(system, name="Atlantica.exe")
    assert report["memory_read"]["status"] == "unavailable"
    assert str(executable) not in json.dumps(report)
    assert system.reads == []


def test_bad_memory_signature_is_not_reported_as_verified(executable):
    system = FakeSystem(executable)
    system.signature = b"??"
    report = diagnose(system, name="Atlantica.exe")
    assert report["memory_read"]["status"] == "unavailable"


def test_preserves_native_error_code_and_failure_stage(executable):
    class DeniedSystem(FakeSystem):
        def read_memory(self, pid, address, size):
            raise NativeError("Leer memoria", 5)

    report = diagnose(DeniedSystem(executable), name="Atlantica.exe")
    assert report["memory_read"]["winerror"] == 5
    assert report["memory_read"]["stage"] == "header_read"


def test_duplicate_clients_require_explicit_pid():
    processes = [Process(1, "Atlantica.exe"), Process(2, "Atlantica.exe")]
    with pytest.raises(DiagnosticError, match="--pid"):
        select_process(processes, name="Atlantica.exe", pid=None)
    assert select_process(processes, name="Atlantica.exe", pid=2) == processes[1]


def test_missing_process_is_actionable():
    with pytest.raises(DiagnosticError, match="Abre el juego"):
        select_process([], name="Atlantica.exe", pid=None)


def test_does_not_replace_previous_report(tmp_path):
    target = tmp_path / "report.json"
    save_report({"first": True}, target)
    with pytest.raises(FileExistsError):
        save_report({"second": True}, target)
    assert json.loads(target.read_text()) == {"first": True}


def test_process_exit_aborts_report(executable):
    class ExitingSystem(FakeSystem):
        def executable_path(self, pid):
            if self.reads:
                raise DiagnosticError("El proceso ha terminado.")
            return super().executable_path(pid)

    with pytest.raises(DiagnosticError, match="terminado"):
        diagnose(ExitingSystem(executable), name="Atlantica.exe")
