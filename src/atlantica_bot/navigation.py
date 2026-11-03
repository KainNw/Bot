from dataclasses import asdict, dataclass

from .errors import DiagnosticError
from .limits import MAX_SEARCH_RADIUS, MIN_SEARCH_RADIUS
from .world import GridPosition, WorldView


def grid_distance(first: GridPosition, second: GridPosition) -> int:
    return abs(first.x - second.x) + abs(first.y - second.y)


def calibrated_radius(view: WorldView, identity: tuple[int, int, int]) -> int:
    if view.scene_code != 2 or view.player is None:
        raise DiagnosticError("Vuelve al mapa para calibrar el radio.")
    targets = [
        c
        for c in view.candidates
        if c.identity == identity
        and c.map_id == view.player.map_id
        and 0 < c.x <= 32767
        and 0 < c.y <= 32767
    ]
    if len(targets) != 1:
        raise DiagnosticError("El objetivo cambió; actualiza la lista antes de calibrar.")
    target = targets[0]
    distance = grid_distance(view.player, GridPosition(target.map_id, target.x, target.y))
    if distance > MAX_SEARCH_RADIUS:
        raise DiagnosticError("Ese mob está fuera del máximo de 500 casillas.")
    return max(MIN_SEARCH_RADIUS, min(MAX_SEARCH_RADIUS, distance + 2))


@dataclass(frozen=True)
class ApproachSettings:
    enabled: bool = False
    radius: int = 60
    timeout: float = 20
    stall_timeout: float = 5

    def __post_init__(self) -> None:
        if (
            type(self.enabled) is not bool
            or type(self.radius) is not int
            or not MIN_SEARCH_RADIUS <= self.radius <= MAX_SEARCH_RADIUS
            or not 5 <= self.timeout <= 30
            or not 2 <= self.stall_timeout <= self.timeout
        ):
            raise DiagnosticError("Revisa el radio de acercamiento (5–500 casillas).")

    def contains(self, origin: GridPosition, position: GridPosition) -> bool:
        return position.map_id == origin.map_id and grid_distance(origin, position) <= self.radius

    def summary(self) -> dict:
        return asdict(self)
