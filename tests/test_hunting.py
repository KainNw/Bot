import hashlib

import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.hunting import (
    BACKUP_NAME,
    MARKER_NAME,
    _move_without_replacing,
    control_hunting,
)


@pytest.fixture
def game(executable, monkeypatch):
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    monkeypatch.setattr("atlantica_bot.hunting.SUPPORTED_CLIENT_SHA256", digest)
    return executable.parent


def test_full_start_stop_restart_cycle_preserves_original_content(game):
    marker = game / MARKER_NAME
    original = b"pre-existing user content\r\n"
    marker.write_bytes(original)
    assert not control_hunting(game, "start").changed
    stopped = control_hunting(game, "stop")
    assert not stopped.marker_present and stopped.backup_present
    assert not marker.exists()
    assert (game / BACKUP_NAME).read_bytes() == original
    assert not control_hunting(game, "stop").changed
    restarted = control_hunting(game, "start")
    assert restarted.marker_present and not restarted.backup_present
    assert marker.read_bytes() == original
    assert not control_hunting(game, "start").changed


def test_creates_empty_marker_and_preserves_other_mode_files(game):
    hold = game / "HoldMode.txt"
    buff = game / "UseBuffItems.txt"
    hold.write_bytes(b"hold settings")
    buff.write_bytes(b"buff settings")
    assert control_hunting(game, "start").changed
    assert (game / MARKER_NAME).read_bytes() == b""
    assert hold.read_bytes() == b"hold settings"
    assert buff.read_bytes() == b"buff settings"


def test_unknown_build_cannot_create_marker(executable):
    with pytest.raises(DiagnosticError, match="compilación"):
        control_hunting(executable.parent, "start")
    assert not (executable.parent / MARKER_NAME).exists()


def test_conflicting_backup_never_overwrites_either_file(game):
    marker, backup = game / MARKER_NAME, game / BACKUP_NAME
    marker.write_bytes(b"active")
    backup.write_bytes(b"saved")
    assert control_hunting(game, "status").backup_present
    for action in ("start", "stop"):
        with pytest.raises(DiagnosticError, match="ambos archivos"):
            control_hunting(game, action)
    assert marker.read_bytes() == b"active"
    assert backup.read_bytes() == b"saved"


def test_move_does_not_clobber_a_destination_created_concurrently(tmp_path):
    source, destination = tmp_path / "source", tmp_path / "destination"
    source.write_bytes(b"source content")
    destination.write_bytes(b"other content")
    with pytest.raises(FileExistsError):
        _move_without_replacing(source, destination)
    assert source.read_bytes() == b"source content"
    assert destination.read_bytes() == b"other content"


@pytest.mark.parametrize("entry_name", [MARKER_NAME, BACKUP_NAME])
def test_refuses_directories_in_place_of_mode_files(game, entry_name):
    (game / entry_name).mkdir()
    with pytest.raises(DiagnosticError, match="archivo normal"):
        control_hunting(game, "start")


@pytest.mark.parametrize("entry_name", [MARKER_NAME, BACKUP_NAME])
def test_refuses_symlinks_and_preserves_their_targets(game, entry_name):
    target = game / "user-file.txt"
    target.write_bytes(b"must survive")
    try:
        (game / entry_name).symlink_to(target)
    except OSError as exc:
        pytest.skip(f"Este sistema no permite crear enlaces para la prueba: {exc}")
    with pytest.raises(DiagnosticError, match="archivo normal"):
        control_hunting(game, "stop")
    assert target.read_bytes() == b"must survive"


def test_status_does_not_create_marker_or_backup(game):
    before = sorted(p.name for p in game.iterdir())
    result = control_hunting(game, "status")
    assert not result.marker_present and not result.backup_present and not result.changed
    assert sorted(p.name for p in game.iterdir()) == before


def test_cli_marker_status_does_not_instantiate_windows_api(game, monkeypatch, capsys):
    from atlantica_bot.__main__ import main

    def forbid_native_api():
        pytest.fail("El control de archivos no debe abrir procesos.")

    monkeypatch.setattr("atlantica_bot.__main__.WindowsSystem", forbid_native_api)
    assert main(["hunt", "status", "--directory", str(game)]) == 0
    assert "Marcador HuntingMode.txt" in capsys.readouterr().out


def test_cli_marker_changes_check_open_clients_on_windows(game, monkeypatch):
    from atlantica_bot.__main__ import main

    class NoClients:
        def processes(self):
            return []

    monkeypatch.setattr("atlantica_bot.__main__.sys.platform", "win32")
    monkeypatch.setattr("atlantica_bot.__main__.WindowsSystem", NoClients)
    for action in ("start", "stop", "start"):
        assert main(["hunt", action, "--directory", str(game)]) == 0


def test_cli_blocks_shared_marker_even_without_connecting_a_session(game, monkeypatch):
    from atlantica_bot.__main__ import main
    from atlantica_bot.report import Process

    class SharedClients:
        def processes(self):
            return [Process(100, "Atlantica.exe"), Process(200, "Atlantica.exe")]

        def working_directory(self, pid):
            return game

    marker = game / MARKER_NAME
    marker.write_bytes(b"existing settings")
    monkeypatch.setattr("atlantica_bot.__main__.sys.platform", "win32")
    monkeypatch.setattr("atlantica_bot.__main__.WindowsSystem", SharedClients)
    assert main(["hunt", "stop", "--directory", str(game)]) == 1
    assert marker.read_bytes() == b"existing settings"


def test_invalid_directory_returns_error_not_success(tmp_path, capsys):
    from atlantica_bot.__main__ import main

    assert main(["hunt", "start", "--directory", str(tmp_path / "missing")]) == 1
    assert "Error:" in capsys.readouterr().err
