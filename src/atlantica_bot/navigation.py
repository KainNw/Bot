from dataclasses import asdict, dataclass

from .errors import DiagnosticError
from .world import GridPosition


def grid_distance(first: GridPosition, second: GridPosition) -> int:
    return abs(first.x - second.x) + abs(first.y - second.y)


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
            or not 5 <= self.radius <= 120
            or not 5 <= self.timeout <= 30
            or not 2 <= self.stall_timeout <= self.timeout
        ):
            raise DiagnosticError("Revisa el radio de acercamiento (5–120 casillas).")

    def contains(self, origin: GridPosition, position: GridPosition) -> bool:
        return position.map_id == origin.map_id and grid_distance(origin, position) <= self.radius

    def summary(self) -> dict:
        return asdict(self)
