import hashlib

import pytest

from atlantica_bot.clients import ClientWindow, control_native_marker, marker_scope
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import MARKER_NAME
from atlantica_bot.report import Process


class Clients:
    def __init__(self, directories):
        self.directories = directories

    def processes(self):
        return [Process(pid, "Atlantica.exe") for pid in self.directories]

    def working_directory(self, pid):
        directory = self.directories[pid]
        if directory is None:
            raise DiagnosticError("Acceso denegado")
        return directory


@pytest.mark.parametrize("action", ["start", "stop"])
def test_three_clients_sharing_a_folder_cannot_modify_each_others_marker(
    executable, monkeypatch, action
):
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr("atlantica_bot.hunting.SUPPORTED_CLIENT_SHA256", digest)
    directory = executable.parent
    marker = directory / MARKER_NAME
    marker.write_bytes(b"user settings")
    system = Clients({100: directory, 200: directory, 300: directory})
    with pytest.raises(DiagnosticError, match="comparten"):
        control_native_marker(system, directory, action)
    assert marker.read_bytes() == b"user settings"
    assert marker_scope(system, directory).sharing == (100, 200, 300)


def test_unknown_client_directory_prevents_marker_changes(executable):
    system = Clients({100: executable.parent, 200: None})
    assert not marker_scope(system, executable.parent).allowed
    with pytest.raises(DiagnosticError, match="comprobar la carpeta"):
        control_native_marker(system, executable.parent, "start")
    assert not (executable.parent / MARKER_NAME).exists()


def test_separate_installations_have_separate_marker_scopes(executable, tmp_path):
    other = tmp_path / "second"
    other.mkdir()
    scope = marker_scope(Clients({100: executable.parent, 200: other}), executable.parent)
    assert scope.allowed
    assert scope.sharing == (100,)


def test_window_labels_distinguish_identical_titles_and_sanitize_line_breaks():
    a = ClientWindow(100, 0x1234, "Atlantica\nOnline")
    b = ClientWindow(200, 0x4567, "Atlantica\nOnline")
    assert a.label != b.label
    assert "PID 100" in a.label and "1234" in a.label
    assert "\n" not in a.label
