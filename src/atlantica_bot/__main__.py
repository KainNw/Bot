from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .errors import DiagnosticError
from .hunting import control_hunting
from .report import diagnose, save_report, self_test
from .windows import WindowsSystem


def positive_pid(value: str) -> int:
    try:
        pid = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("El PID debe ser un número entero.") from exc
    if not 1 <= pid <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("El PID debe estar entre 1 y 4294967295.")
    return pid


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="atlantica-bot",
        description="Control de AutoHunting y diagnóstico del cliente de Atlantica Online.",
    )
    root.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("panel", help="Abrir el panel de inicio, parada y estado en Windows.")
    hunt = commands.add_parser("hunt", help="Controlar el marcador del AutoHunting integrado.")
    hunt.add_argument("action", choices=("start", "stop", "status"))
    hunt.add_argument(
        "--directory",
        type=Path,
        required=True,
        help="Carpeta de trabajo del juego que contiene Atlantica.exe.",
    )
    inspect = commands.add_parser("diagnose", help="Generar un informe del cliente abierto.")
    target = inspect.add_mutually_exclusive_group()
    target.add_argument("--process", default="Atlantica.exe", help="Nombre exacto del ejecutable.")
    target.add_argument(
        "--pid", type=positive_pid, help="PID del cliente en el Administrador de tareas."
    )
    inspect.add_argument("--output", type=Path, help="Archivo JSON nuevo; no sobrescribe archivos.")
    listing = commands.add_parser("processes", help="Mostrar los nombres y PID que coincidan.")
    listing.add_argument("--contains", default="atlantica", help="Parte del nombre del proceso.")
    commands.add_parser("self-test", help="Probar las APIs sobre este proceso, sin usar el juego.")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "panel":
            from .gui import launch_panel

            launch_panel()
            return 0
        if args.command == "hunt":
            result = control_hunting(args.directory, args.action)
            print(
                f"Marcador HuntingMode.txt: {'presente' if result.marker_present else 'ausente'}."
            )
            if result.backup_present:
                print(
                    "El contenido anterior se conserva en HuntingMode.txt.disabled.atlantica-bot."
                )
            print("Cambio aplicado." if result.changed else "Estado consultado; sin cambios.")
            print(
                "Este estado describe el archivo. El cliente necesita Auto Battle y sus "
                "otras condiciones; vuelve a consultar el marcador durante su actualización."
            )
            return 0
        system = WindowsSystem()
        if args.command == "self-test":
            self_test(system)
            print("Prueba local correcta: proceso, ejecutable, módulo y lectura de memoria.")
            return 0
        if args.command == "processes":
            found = [p for p in system.processes() if args.contains.casefold() in p.name.casefold()]
            if not found:
                raise DiagnosticError("No se encontraron procesos con ese nombre.")
            for process in found:
                print(f"{process.pid:>8}  {process.name}")
            return 0
        report = diagnose(system, name=args.process, pid=args.pid)
        output = args.output or Path(f"diagnostico-cliente-{datetime.now():%Y%m%d-%H%M%S-%f}.json")
        save_report(report, output)
        executable = report["executable_on_disk"]
        print(f"Cliente: {executable['name']} ({executable['architecture']}).")
        print(f"Versión: {executable['file_version'] or 'sin recurso de versión'}.")
        print(f"Informe guardado: {output}")
        if report["memory_read"]["status"] != "verified":
            print("Informe parcial: no se pudo verificar la lectura de memoria.", file=sys.stderr)
            return 2
        print("Lectura de cabecera verificada; este diagnóstico no confirma el estado de la caza.")
        return 0
    except (DiagnosticError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
