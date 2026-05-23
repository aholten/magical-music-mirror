from dataclasses import dataclass


@dataclass(frozen=True)
class Gene:
    index: int
    name: str
    description: str
    options: tuple[str, ...]
