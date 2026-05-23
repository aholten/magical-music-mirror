import numpy as np

from engine.genes import Gene


CONWAY_GENES = [
    Gene(
        index=0,
        name="composition",
        description="How the audio layer combines with the ruleset output.",
        options=("gated", "underlay"),
    ),
    Gene(
        index=1,
        name="state_boundary",
        description="Whether audio pixels feed into the next Conway generation.",
        options=("audio_seeded", "isolated"),
    ),
]


def _vshift(grid: np.ndarray, dy: int) -> np.ndarray:
    """Vertical neighbor shift with zero (dead) padding — no top/bottom wrap."""
    if dy == 0:
        return grid
    out = np.zeros_like(grid)
    if dy == -1:
        out[:-1] = grid[1:]   # row y reads from row y+1; last row sees dead
    else:                     # dy == 1
        out[1:] = grid[:-1]   # row y reads from row y-1; row 0 sees dead
    return out


def _step_conway(grid: np.ndarray) -> np.ndarray:
    """One step of Conway's B3/S23. Horizontal axis wraps; vertical axis
    has hard top/bottom boundaries (cells beyond the edge are dead)."""
    neighbors = sum(
        np.roll(_vshift(grid, dy), dx, axis=1)
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
        if (dy, dx) != (0, 0)
    )
    return ((neighbors == 3) | (grid & (neighbors == 2))).astype(bool)


class ConwayRenderRuleset:
    genes = CONWAY_GENES
    compose_mode: str = "underlay"  # subclass-overridden

    def __init__(self, shape: tuple[int, int], seed_density: float = 0.25):
        h, w = shape
        rng = np.random.default_rng()
        self._grid = rng.random((h, w)) < seed_density

    def step(self, prev_frame: np.ndarray, audio_layer: np.ndarray) -> np.ndarray:
        raise NotImplementedError


class ConwayRenderRuleset11(ConwayRenderRuleset):
    """Underlay + isolated: Conway evolves its own buffer, audio paints over alive cells."""

    compose_mode = "underlay"

    def step(self, prev_frame, audio_layer):
        self._grid = _step_conway(self._grid)
        return self._grid


class ConwayRenderRuleset10(ConwayRenderRuleset):
    """Underlay + audio-seeded: audio brightness births cells, then Conway evolves."""

    compose_mode = "underlay"

    def step(self, prev_frame, audio_layer):
        audio_lum = audio_layer.any(axis=-1)
        self._grid = self._grid | audio_lum
        self._grid = _step_conway(self._grid)
        return self._grid


class ConwayRenderRuleset01(ConwayRenderRuleset):
    """Gated + isolated: survival mask stencils the audio layer."""

    compose_mode = "gated"

    def step(self, prev_frame, audio_layer):
        self._grid = _step_conway(self._grid)
        return self._grid


class ConwayRenderRuleset00(ConwayRenderRuleset):
    """Gated + audio-seeded: audio birth + survival mask gates the audio."""

    compose_mode = "gated"

    def step(self, prev_frame, audio_layer):
        audio_lum = audio_layer.any(axis=-1)
        self._grid = self._grid | audio_lum
        self._grid = _step_conway(self._grid)
        return self._grid


VARIANTS = {
    "conway00": ConwayRenderRuleset00,
    "conway01": ConwayRenderRuleset01,
    "conway10": ConwayRenderRuleset10,
    "conway11": ConwayRenderRuleset11,
}
