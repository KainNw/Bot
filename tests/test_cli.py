import sys

import pytest
from test_report import FakeSystem

from atlantica_bot.__main__ import main, parser
from atlantica_bot.errors import DiagnosticError
from atlantica_bot.report import Process


def test_cli_can_import_and_show_help_without_windows(capsys):
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    assert "diagnose" in capsys.readouterr().out


def test_cli_exposes_readonly_battle_capture():
    args = parser().parse_args(["capture", "--combat", "--pid", "123", "--output", "battle.zip"])
    assert args.combat is True and args.pid == 123


@pytest.mark.parametrize("pid", ["0", "-1", "not-a-pid", "4294967296"])
def test_invalid_pid_is_rejected(pid):
    with pytest.raises(SystemExit) as result:
        parser().parse_args(["diagnose", "--pid", pid])
    assert result.value.code == 2


@pytest.mark.skipif(sys.platform == "win32", reason="Comprueba el error en otros sistemas.")
def test_non_windows_error_has_no_traceback(capsys):
    assert main(["diagnose"]) == 1
    message = capsys.readouterr().err
    assert "Windows" in message
    assert "Traceback" not in message


@pytest.mark.parametrize("denied,expected", [(False, 0), (True, 2)])
def test_cli_preserves_full_and_partial_outcomes(
    monkeypatch, executable, tmp_path, denied, expected
):
    system = FakeSystem(executable)
    system.denied = denied
    monkeypatch.setattr("atlantica_bot.__main__.WindowsSystem", lambda: system)
    output = tmp_path / "report.json"
    assert main(["diagnose", "--output", str(output)]) == expected
    assert output.is_file()


def test_cli_reports_missing_process_without_writing_file(monkeypatch, tmp_path, capsys):
    class MissingSystem:
        def processes(self) -> list[Process]:
            return []

    monkeypatch.setattr("atlantica_bot.__main__.WindowsSystem", MissingSystem)
    output = tmp_path / "report.json"
    assert main(["diagnose", "--output", str(output)]) == 1
    assert not output.exists()
    assert "Abre el juego" in capsys.readouterr().err


def test_cli_self_test_failure_is_nonzero(monkeypatch, capsys):
    monkeypatch.setattr("atlantica_bot.__main__.WindowsSystem", object)

    def fail(_):
        raise DiagnosticError("Prueba fallida.")

    monkeypatch.setattr("atlantica_bot.__main__.self_test", fail)
    assert main(["self-test"]) == 1
    assert "Prueba fallida" in capsys.readouterr().err
