"""Bundle the panel and dependency-free diagnostic sources."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "dist" / "atlantica-panel-fuentes.zip"
    files = [
        root / name
        for name in (
            "README.md",
            "diagnosticar.py",
            "controlar_caza.py",
            "panel_caza.py",
            "diagnosticar_cliente.bat",
            "pyproject.toml",
            "uv.lock",
            ".gitignore",
            ".gitattributes",
        )
    ]
    for directory in ("src", "tests", "tools"):
        files.extend(sorted((root / directory).rglob("*.py")))
    files.extend(sorted((root / "docs").rglob("*.md")))
    files.extend(sorted((root / "native").glob("*")))
    files.extend(sorted((root / ".github" / "workflows").glob("*.yml")))
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in files:
            name = (Path("AtlanticaPanel") / path.relative_to(root)).as_posix()
            if path.suffix == ".bat":
                content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
                archive.writestr(name, content)
            else:
                archive.write(path, name)
    print(output)


if __name__ == "__main__":
    main()
