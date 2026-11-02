"""Control the native AutoHunting file marker without installing extra packages."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from atlantica_bot.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["hunt", *sys.argv[1:]]))
