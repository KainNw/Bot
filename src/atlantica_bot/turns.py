from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from .battle import BattleFrame, BattleTrial, BattleUnit
from .profiles import ACTION_LABELS, TARGET_LABELS, BotProfile, Mercenary, member_label


def unit_key(unit: BattleUnit) -> tuple:
    return unit.identity, unit.member_slot


def loot_key(frame: BattleFrame, target: BattleUnit) -> tuple:
    ctx = frame.context
    return ctx.pid, ctx.creation_time, ctx.context, "loot", *unit_key(target)


def roster_rows(
    profile: BotProfile, frame: BattleFrame | None, orders: dict | None = None
) -> list[dict]:
    plans = {m.slot: m for m in profile.mercenaries}
    units = {u.member_slot: u for u in frame.units if u.world_slot == 1} if frame else {}
    priorities = {m.slot: n for n, m in enumerate(profile.mercenaries, 1)}
    rows = []
    for slot in range(1, 10):
        plan, unit = plans[slot], units.get(slot)
        rows.append(
            {
                "slot": slot,
                "label": member_label(slot),
                "name": plan.name,
                "enabled": plan.enabled,
                "priority": priorities[slot],
                "present": unit is not None if frame else None,
                "alive": unit.life > 0 if unit else None,
                "kind_id": unit.kind_id if unit else None,
                "life": unit.life if unit is not None and unit.life >= 0 else None,
                "target": TARGET_LABELS[plan.target],
                "opening_action": ACTION_LABELS[plan.action] if plan.enabled else "Sin orden",
                "later_action": (
                    "Ataque básico" if profile.magic_first_turn_only else ACTION_LABELS[plan.action]
                )
                if plan.enabled
                else "Sin orden",
                "last_order": (orders or {}).get(str(slot), {}).get("message", "Sin orden"),
            }
        )
    return rows


@dataclass
class PendingTurn:
    trial: BattleTrial
    sent_at: float
    source_value: int | None
    seen_busy: bool = False
    changed: bool = False
    idle_since: float | None = None


class TurnEngine:
    """Plan one bounded native request at a time; never infer server acceptance from a queue."""

    def __init__(
        self,
        pid: int,
        creation_time: int,
        profile: BotProfile,
        ledger: set | None = None,
        *,
        execute_orders: bool = True,
    ):
        profile.validate()
        self.pid, self.creation_time, self.profile = pid, creation_time, profile
        self.ledger = ledger if ledger is not None else set()
        self.execute_orders = execute_orders
        self.loot_empty_since: float | None = None
        self.loot_rejected = set()
        self.loot_queued = 0
        self.loot_suspended = False
        self.loot_pause_reason: str | None = None
        self.active = False
        self.fresh_battle = False
        self.turn = None
        self.opening_turn = None
        self.finished_opening = False
        self.consumed = set()
        self.skipped = set()
        self.rejected = set()
        self.fallback = set()
        self.deferred_until = {}
        self.unready_attempts = {}
        self.seen_enemy = False
        self.observed_initial_turn = False
        self.timeline = {}
        self.observed_at: float | None = None
        self.pending: PendingTurn | None = None
        self.inflight: BattleTrial | None = None
        self.last_frame: BattleFrame | None = None
        self.running = True
        self.needs_reconnect = False
        self.message = "Esperando combate."
        self.orders = {}
        self.last_result = {}
        self.events = deque(maxlen=24)
        self.queued = self.observed = self.selections = self.attempts = 0

    def enter(self, *, fresh: bool) -> None:
        if not self.active:
            self.active = True
            self.fresh_battle = fresh
            self.turn = self.opening_turn = None
            self.finished_opening = False
            self.consumed.clear()
            self.skipped.clear()
            self.rejected.clear()
            self.fallback.clear()
            self.deferred_until.clear()
            self.unready_attempts.clear()
            self.seen_enemy = False
            self.observed_initial_turn = False
            self.timeline.clear()
            self.observed_at = None
            self.orders.clear()
            self.loot_empty_since = None
            self.loot_rejected.clear()
            self.loot_suspended = False
            self.loot_pause_reason = None
            self.pending = self.inflight = None

    def leave(self) -> None:
        self.active = False
        self.pending = self.inflight = None
        self.last_frame = None
        self.message = "Fuera de combate."

    def stop(self, message: str, *, uncertain: bool = False) -> None:
        self.running = False
        self.needs_reconnect |= uncertain
        self.message = message

    def _mark(self, event: str, now: float) -> None:
        self.observed_at = now
        self.timeline.setdefault(event, now)

    def note_map(self, now: float) -> None:
        if self.active and self.timeline:
            self._mark("first_map_observed", now)

    def _defer_unready(self, trial: BattleTrial, now: float) -> None:
        # InvokeBattle returns 27–29 before its send path. Other outcomes never use this retry.
        slot = trial.source.member_slot
        count = self.unready_attempts.get(slot, 0) + 1
        self.unready_attempts[slot] = count
        if count >= 3:
            self.skipped.add(slot)
            message = "No disponible tras tres comprobaciones sin envío; omitido en este turno"
        else:
            self.deferred_until[slot] = now + 0.25
            message = "Cliente no listo; esperando una lectura nueva antes de solicitar otra vez"
        self._order(slot, trial.action, message, now)

    def _order(self, slot: int, action: str, message: str, now: float) -> None:
        value = {"slot": slot, "action": action, "message": message, "time": round(now, 3)}
        self.orders[str(slot)] = value
        self.events.append(value)
        self.message = f"{member_label(slot)}: {message}"

    @staticmethod
    def _value(frame: BattleFrame, slot: int) -> int | None:
        return next((m.value_50 for m in frame.context.members if m.slot == slot), None)

    def _observe_pending(self, frame: BattleFrame, now: float) -> bool:
        pending = self.pending
        trial = pending.trial
        source = next((u for u in frame.units if unit_key(u) == unit_key(trial.source)), None)
        target = next((u for u in frame.units if unit_key(u) == unit_key(trial.target)), None)
        busy = source is not None and source.action_state != 1
        pending.seen_busy |= busy
        pending.changed |= (
            source is None
            or source.life <= 0
            or target is None
            or target.life != trial.target.life
            or self._value(frame, trial.source.member_slot) != pending.source_value
        )
        if trial.action == "loot" and target is not None:
            pending.changed |= (
                target.flags != trial.target.flags
                or target.action_state != trial.target.action_state
            )
        if not frame.own_turn or not frame.enemies and trial.action != "loot":
            self.observed += 1
            self.pending = None
            return True
        if (pending.changed or pending.seen_busy) and not busy:
            if pending.idle_since is None:
                pending.idle_since = now
            if now - pending.idle_since >= 0.5:
                self.observed += 1
                self._order(
                    trial.source.member_slot,
                    trial.action,
                    "Cambio observado tras la solicitud",
                    now,
                )
                self.pending = None
                return True
        else:
            pending.idle_since = None
        if now - pending.sent_at >= 12:
            self.stop(
                "No se observó progreso tras la orden de combate; detenido sin repetirla.",
                uncertain=True,
            )
        else:
            self.message = (
                f"{member_label(trial.source.member_slot)}: esperando el resultado de la orden."
            )
        return False

    def _next_loot(self, frame: BattleFrame, now: float) -> BattleTrial | None:
        if self.pending is not None and self.pending.trial.action == "loot":
            if not self._observe_pending(frame, now):
                return None
        if self.loot_suspended:
            self.message = self.loot_pause_reason
            return None
        if not self.profile.collect_remaining_loot or not frame.corpses:
            return None
        if self.loot_empty_since is None:
            self.loot_empty_since = now
        # Give NeoACA the first opportunity. This does not delay the opening magic.
        if now - self.loot_empty_since < 1 or not frame.own_turn:
            self.message = "Esperando la recogida del NeoACA antes de buscar botín restante."
            return None
        if self.pending is not None and not self._observe_pending(frame, now):
            return None
        sources = {u.member_slot: u for u in frame.sources}
        for plan in self.profile.mercenaries:
            source = sources.get(plan.slot)
            if (
                not plan.enabled
                or source is None
                or source.action_state != 1
                or plan.slot in self.skipped
            ):
                continue
            if now < self.deferred_until.get(plan.slot, 0):
                continue
            targets = [
                u
                for u in frame.corpses
                if loot_key(frame, u) not in self.ledger
                and (plan.slot, unit_key(u)) not in self.loot_rejected
            ]
            if not targets:
                continue
            trial = (
                BattleTrial(frame, source, action="select")
                if frame.selected_unit != source.address
                else BattleTrial(frame, source, targets[0], "loot")
            )
            trial.validate()
            self.inflight = trial
            self._order(plan.slot, trial.action, "Preparando recogida de botín restante", now)
            return trial
        self.message = "Sin recogidas pendientes disponibles; esperando el final del combate."
        return None

    def _targets(
        self, frame: BattleFrame, plan: Mercenary, source: BattleUnit, action: str
    ) -> tuple:
        if action == "basic" or plan.target == "enemy":
            targets = frame.enemies
        elif plan.target == "self":
            targets = (source,)
        else:
            slot = int(plan.target.removeprefix("slot_"))
            targets = tuple(u for u in frame.sources if u.member_slot == slot)
        return tuple(
            u for u in targets if (source.member_slot, action, unit_key(u)) not in self.rejected
        )

    def next(self, frame: BattleFrame, now: float) -> BattleTrial | None:
        if not self.running or not self.active:
            return None
        if (frame.context.pid, frame.context.creation_time) != (self.pid, self.creation_time):
            self.stop("La lectura de turnos pertenece a otra instancia.", uncertain=True)
            return None
        self.last_frame = frame
        self._mark("first_frame", now)
        prefix = (
            self.pid,
            self.creation_time,
            frame.context.context,
            frame.turn_number,
            frame.turn_tick,
        )
        if len(self.ledger) > 2048:
            keep = {loot_key(frame, u) for u in frame.corpses}
            self.ledger.intersection_update(
                {key for key in self.ledger if key[:5] == prefix or key in keep}
            )
        if self.inflight is not None:
            self.stop("Hay una orden sin respuesta; no se permite otra.", uncertain=True)
            return None
        if frame.phase != 3 or frame.turn_number == 0xFFFFFFFF:
            self.message = "Esperando la fase de combate."
            return None
        self.observed_initial_turn |= frame.turn_number == 0
        turn = (frame.context.context, frame.turn_number, frame.turn_tick, frame.turn_group)
        if turn != self.turn:
            if self.pending is not None:
                self.observed += 1
                self.pending = None
            if self.opening_turn is not None and turn != self.opening_turn:
                self.finished_opening = True
            self.turn = turn
            self.consumed.clear()
            self.skipped.clear()
            self.rejected.clear()
            self.fallback.clear()
            self.deferred_until.clear()
            self.unready_attempts.clear()
        if frame.own_turn:
            self._mark("first_own_turn", now)
        if frame.enemies:
            self.loot_empty_since = None
            self.seen_enemy = True
            self._mark("first_enemies", now)
        if not frame.enemies:
            if self.pending is not None and self.pending.trial.action != "loot":
                self.observed += 1
                self.pending = None
            if self.seen_enemy:
                self._mark("first_no_enemies_after_seen", now)
                self.message = "Sin enemigos vivos; esperando el final de la batalla."
            else:
                self.message = "Esperando que el cliente publique los enemigos del combate."
            return self._next_loot(frame, now)
        if self.pending is not None and not self._observe_pending(frame, now):
            return None
        if not self.execute_orders:
            self.message = "Turnos manuales; la recogida esperará a que no queden enemigos vivos."
            return None
        if not frame.own_turn:
            self.message = "Esperando el turno de tu grupo."
            return None
        if self.opening_turn is None and not self.finished_opening:
            if self.fresh_battle or self.observed_initial_turn:
                self.opening_turn = turn
            else:
                self.finished_opening = True
        opening = self.opening_turn == turn and not self.finished_opening
        sources = {u.member_slot: u for u in frame.sources}
        for plan in self.profile.mercenaries:
            source = sources.get(plan.slot)
            if not plan.enabled or source is None or plan.slot in self.consumed | self.skipped:
                continue
            if (*prefix, plan.slot) in self.ledger:
                continue
            if now < self.deferred_until.get(plan.slot, 0):
                self.message = f"{member_label(plan.slot)}: esperando que el cliente esté listo."
                return None
            if source.action_state != 1:
                self.message = f"{member_label(plan.slot)}: esperando que termine su animación."
                return None
            action = plan.action if opening or not self.profile.magic_first_turn_only else "basic"
            if plan.slot in self.fallback:
                action = "basic"
            if action != "basic":
                if frame.selected_unit != source.address:
                    trial = BattleTrial(frame, source, action="select")
                    trial.validate()
                    self.inflight = trial
                    self._order(plan.slot, "select", "Seleccionando en el juego", now)
                    return trial
                if frame.magic_error or "QWERT".index(action) >= len(frame.magic_actions):
                    if plan.fallback_basic:
                        self.fallback.add(plan.slot)
                        action = "basic"
                    else:
                        self.skipped.add(plan.slot)
                        self._order(plan.slot, action, "Magia no disponible en su barra", now)
                        continue
            targets = self._targets(frame, plan, source, action)
            if not targets:
                if action != "basic" and plan.fallback_basic:
                    self.fallback.add(plan.slot)
                    self._order(plan.slot, action, "Objetivo de magia ausente; usará básico", now)
                    return None
                else:
                    self.skipped.add(plan.slot)
                continue
            if action == "basic" and not source.flags & 0x8000:
                self.skipped.add(plan.slot)
                continue
            trial = BattleTrial(frame, source, targets[0], action)
            trial.validate()
            self.inflight = trial
            self._order(plan.slot, action, f"Solicitando {ACTION_LABELS[action]}", now)
            return trial
        self.message = "Esperando unidades disponibles o el siguiente turno del juego."
        return None

    def record(self, trial: BattleTrial, report: dict, now: float) -> None:
        if (
            self.inflight != trial
            or report.get("pid") != self.pid
            or report.get("operation") != trial.operation
        ):
            self.stop("Respuesta de otra orden de combate.", uncertain=True)
            return
        self.inflight = None
        self.last_result = dict(report)
        self.observed_at = now
        code = report["status"]
        if (
            code == 31
            and trial.operation != 7
            or code == 26
            and trial.operation != 6
            or code == 32
            and trial.operation != 8
            or code == 36
            and trial.operation != 9
        ):
            self.stop("La respuesta no corresponde al tipo de orden.", uncertain=True)
            return
        if code == 31:
            self._mark("first_selection", now)
            self.selections += 1
            self._order(trial.source.member_slot, "select", "Seleccionado; leyendo su barra", now)
            return
        self.attempts += 1
        slot = trial.source.member_slot
        if code == 36:
            self.loot_queued += 1
            self.ledger.add(loot_key(trial.frame, trial.target))
            self.pending = PendingTurn(trial, now, self._value(trial.frame, slot))
            self._order(slot, "loot", "Recogida encolada; esperando cambios en el cliente", now)
        elif code == 37:
            self.loot_rejected.add((slot, unit_key(trial.target)))
            self._order(slot, "loot", "Recogida rechazada sin envío", now)
        elif code in (26, 32):
            self._mark("first_order_queued", now)
            self.queued += 1
            self.consumed.add(slot)
            self.ledger.add(trial.key())
            self.pending = PendingTurn(trial, now, self._value(trial.frame, slot))
            self._order(slot, trial.action, f"{ACTION_LABELS[trial.action]} encolado", now)
        elif code == 30:
            error = report.get("battle", {}).get("native_error", [0])[0]
            if error == 0x1C1:
                self.skipped.add(slot)
            else:
                self.rejected.add((slot, trial.action, unit_key(trial.target)))
            self._order(slot, trial.action, "Básico rechazado por el cliente", now)
        elif code in (34, 35):
            plan = next(m for m in self.profile.mercenaries if m.slot == slot)
            if plan.fallback_basic:
                self.fallback.add(slot)
            else:
                self.skipped.add(slot)
            self._order(slot, trial.action, "Magia rechazada sin envío", now)
        elif code == 27:
            self._defer_unready(trial, now)
        elif code in (28, 29):
            self._defer_unready(trial, now)
        elif code == 33:
            if trial.operation == 9 or (
                trial.operation == 7
                and self.profile.collect_remaining_loot
                and not trial.frame.enemies
            ):
                # 33 is returned before an action is sent. Do not fight the selection
                # or stop hunting because an optional collection could not be sent.
                self.loot_suspended = True
                self.loot_pause_reason = (
                    "Cambió la selección; recogida restante en pausa hasta el siguiente combate."
                )
                self._order(slot, "loot", self.loot_pause_reason, now)
            else:
                self.stop("La selección del juego cambió; bot detenido para revisar el equipo.")
        elif code == 13:
            self.stop("Orden de combate cancelada.")
        else:
            self.stop(
                report.get("message", "Orden de combate sin resultado confirmado."), uncertain=True
            )

    def summary(self) -> dict:
        return {
            "enabled": True,
            "execute_orders": self.execute_orders,
            "loot": {
                "enabled": self.profile.collect_remaining_loot,
                "queued": self.loot_queued,
                "paused": self.loot_suspended,
                "pause_reason": self.loot_pause_reason,
                "neo_grace_seconds": 1,
                "bonus_detection_verified": False,
                "collection_confirmed": False,
            },
            "active": self.active,
            "running": self.running,
            "message": self.message,
            "needs_reconnect": self.needs_reconnect,
            "queued": self.queued,
            "observed_changes": self.observed,
            "attempts": self.attempts,
            "selections": self.selections,
            "unready_attempts": dict(self.unready_attempts),
            "seen_enemy": self.seen_enemy,
            "observed_initial_turn": self.observed_initial_turn,
            "timing_seconds": {
                key: round(value - self.timeline["first_frame"], 3)
                for key, value in self.timeline.items()
            }
            if self.timeline
            else {},
            "last_observed_seconds": round(self.observed_at - self.timeline["first_frame"], 3)
            if self.timeline and self.observed_at is not None
            else None,
            "frame": {
                "phase": self.last_frame.phase,
                "context_index": self.last_frame.context.index,
                "turn_number": self.last_frame.turn_number,
                "turn_tick": self.last_frame.turn_tick,
                "turn_group": self.last_frame.turn_group,
                "local_group": self.last_frame.local_group,
                "own_turn": self.last_frame.own_turn,
                "enemy_count": len(self.last_frame.enemies),
                "selected_unit": self.last_frame.selected_unit,
                "magic_error": self.last_frame.magic_error,
                "units": [asdict(unit) for unit in self.last_frame.units],
            }
            if self.last_frame
            else None,
            "opening_turn": self.opening_turn,
            "magic_first_turn_only": self.profile.magic_first_turn_only,
            "orders": dict(self.orders),
            "last_result": dict(self.last_result),
            "recent_events": list(self.events),
            "roster": roster_rows(self.profile, self.last_frame, self.orders),
            "pending": {
                "slot": self.pending.trial.source.member_slot,
                "action": self.pending.trial.action,
                "target": asdict(self.pending.trial.target),
            }
            if self.pending
            else None,
        }
