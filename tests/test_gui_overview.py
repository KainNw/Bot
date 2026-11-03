import sys

import pytest

from atlantica_bot.gui import launch_panel


@pytest.mark.skipif(sys.platform != "win32", reason="The panel uses Windows client APIs")
def test_overview_roster_controls_and_instance_scope_without_connecting_or_saving(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    launch_panel(smoke_test=True)
    assert not (tmp_path / "AtlanticaPanel").exists()
