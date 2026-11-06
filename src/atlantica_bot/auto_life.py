from __future__ import annotations

import struct

from .errors import DiagnosticError, SceneChanged
from .native_action import _request
from .world import OWNER_ADDRESS, Reader


def binding(session) -> tuple:
    r = Reader(session)
    owner = r.u32(OWNER_ADDRESS)
    world = r.u32(owner + 0x828)
    player = r.u32(world + 0x2C)
    if r.u32(player + 0x200) != 1 or r.u32(player + 0x2C) != world:
        raise SceneChanged("Auto Life: el personaje está cambiando.")
    if r.i32(player + 0x318) != -1 or r.i32(player + 0x254) != -1:
        raise SceneChanged("Auto Life espera fuera de combate.")
    info = r.u32(player + 0x30)
    identity = struct.unpack("<3I", r.read(player + 0x204, 12))
    return owner, world, player, info, identity


def try_auto_life(session, window, profile, signal) -> tuple[dict, tuple]:
    profile.validate()
    before = binding(session)
    _, _, player, info, identity = before
    arguments = {
        "life-player": player,
        "life-info": info,
        "life-key": int(profile.auto_life_key[1:]),
        "life-threshold": profile.auto_life_threshold,
        **dict(zip(("actor-kind", "actor-serial", "actor-unique"), identity, strict=True)),
    }
    if binding(session) != before:
        raise SceneChanged("Auto Life: la formación cambió antes de la consulta.")
    report = _request(session, window, None, operation=19, cancellation=signal, auto_life=arguments)
    if report["status"] not in (55, 56, 57, 58) or report.get("exception") != 0:
        raise DiagnosticError(report["message"])
    data = report.get("auto_life", {})
    if not isinstance(data, dict):
        raise DiagnosticError("La respuesta de Auto Life está incompleta.")
    rows = data.get("members")
    if (
        data.get("key") != arguments["life-key"]
        or data.get("threshold") != profile.auto_life_threshold
        or type(data.get("low_mask")) is not int
        or not 0 <= data["low_mask"] < 512
        or not isinstance(rows, list)
        or len(rows) != 9
        or any(
            not isinstance(row, dict)
            or row.get("slot") != index
            or any(
                type(row.get(field)) is not int for field in ("slot", "kind", "hp", "mp", "max_mp")
            )
            for index, row in enumerate(rows, 1)
        )
    ):
        raise DiagnosticError("Auto Life devolvió datos incompletos; no se repetirá la tecla.")
    report["potion_confirmed"] = False
    return report, before


class AutoLife:
    def __init__(self, profile):
        self.profile = profile
        self.next_check = 0.0
        self.pending = None
        self.disabled = False
        self.report = {
            "enabled": profile.auto_life_enabled,
            "resource": "mp",
            "threshold": profile.auto_life_threshold,
            "key": profile.auto_life_key,
            "outside_battle_only": True,
            "requests": 0,
            "recoveries_observed": 0,
            "message": "Esperando mapa" if profile.auto_life_enabled else "Desactivado",
        }

    def tick(self, session, window, signal, now: float) -> bool:
        """Return True only while holding a short map pause for potion observation."""
        if not self.profile.auto_life_enabled or self.disabled:
            return False
        try:
            if self.pending is not None:
                request, expected, sent = self.pending
                if binding(session) != expected:
                    raise DiagnosticError("Auto Life: cambió el personaje durante la comprobación.")
                rows = request["auto_life"]["members"]
                reader = Reader(session)
                recovered = any(
                    request["auto_life"]["low_mask"] & (1 << (row["slot"] - 1))
                    and reader.i32(expected[3] + 0x4108 + (row["slot"] - 1) * 0x488 + 0x50)
                    > row["mp"]
                    for row in rows
                )
                if recovered:
                    self.pending = None
                    self.next_check = now + 3
                    self.report["recoveries_observed"] += 1
                    self.report["message"] = "Recuperación de MP observada"
                    return False
                if now - sent < 10:
                    return True
                raise DiagnosticError(
                    "Auto Life pausado: no se observó recuperación de MP. "
                    "Revisa la tecla y la poción."
                )
            if now < self.next_check:
                return False
            self.next_check = now + 2
            request, expected = try_auto_life(session, window, self.profile, signal)
            self.report.update(last_request=request, message=request["message"])
            if request["status"] == 56:
                self.report["requests"] += 1
                self.pending = request, expected, now
                return True
        except SceneChanged:
            return False
        except (DiagnosticError, OSError) as exc:
            self.disabled = True
            self.pending = None
            self.report.update(message=str(exc), paused=True)
        return False
