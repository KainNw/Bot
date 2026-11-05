import pytest

from atlantica_bot.errors import DiagnosticError
from atlantica_bot.native_cache import stable_bridge


def fixture_pair(root):
    root.mkdir()
    (root / "AtlanticaBridge.exe").write_bytes(b"own bridge fixture")
    (root / "AtlanticaHook.dll").write_bytes(b"own library fixture")
    return root


def test_same_build_reuses_dll_path_across_independent_panel_extractions(tmp_path):
    first = fixture_pair(tmp_path / "extraction-one")
    second = fixture_pair(tmp_path / "extraction-two")
    cache = tmp_path / "cache"
    path = stable_bridge(first, cache)
    before = path.with_name("AtlanticaHook.dll").stat().st_mtime_ns
    assert stable_bridge(second, cache) == path
    assert path.with_name("AtlanticaHook.dll").stat().st_mtime_ns == before
    assert path.read_bytes() == (first / path.name).read_bytes()


def test_different_native_build_gets_distinct_directory(tmp_path):
    source = fixture_pair(tmp_path / "extracted")
    first = stable_bridge(source, tmp_path / "cache")
    (source / "AtlanticaHook.dll").write_bytes(b"next own library fixture")
    assert stable_bridge(source, tmp_path / "cache") != first
    assert first.with_name("AtlanticaHook.dll").read_bytes() == b"own library fixture"


def test_corrupted_cached_bridge_is_rejected_without_replacing_it(tmp_path):
    source = fixture_pair(tmp_path / "extracted")
    path = stable_bridge(source, tmp_path / "cache")
    path.write_bytes(b"unexpected content")
    with pytest.raises(DiagnosticError, match="No se ejecutó"):
        stable_bridge(source, tmp_path / "cache")
    assert path.read_bytes() == b"unexpected content"
