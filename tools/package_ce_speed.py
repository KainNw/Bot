"""Package our CE Lua experiment; never bundle Cheat Engine or the game."""

from __future__ import annotations

import argparse
import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path


def package(output: Path) -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    source = (root / "tools/cheat_engine/atlantica_speed_trial.lua").read_text(encoding="utf-8")
    table = ET.Element("CheatTable", CheatEngineTableVersion="45")
    ET.SubElement(table, "CheatEntries")
    ET.SubElement(table, "UserdefinedSymbols")
    ET.SubElement(table, "LuaScript").text = source
    output.mkdir(parents=True, exist_ok=True)
    files = [
        output / name
        for name in ("Atlantica-SpeedTrial.CT", "atlantica_speed_trial.lua", "LEEME.md")
    ]
    ET.indent(table, space="  ")
    files[0].write_bytes(ET.tostring(table, encoding="utf-8", xml_declaration=True))
    files[1].write_text(source, encoding="utf-8", newline="\n")
    files[2].write_text(
        (root / "docs/ce-speed-trial.md").read_text(encoding="utf-8"),
        encoding="utf-8",
        newline="\n",
    )
    checksum = output / "SHA256.txt"
    checksum.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in files
        ),
        encoding="ascii",
    )
    return [*files, checksum]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/Atlantica-SpeedTrial-CE"))
    args = parser.parse_args()
    for path in package(args.output):
        print(path)


if __name__ == "__main__":
    main()
