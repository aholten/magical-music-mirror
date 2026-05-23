import numpy as np


def compose(audio_layer: np.ndarray, ruleset_output: np.ndarray, mode: str) -> np.ndarray:
    """Combine an audio pixel layer with a ruleset output into a final RGB frame.

    audio_layer: (H, W, 3) uint8.
    ruleset_output: (H, W) bool — True = alive / surviving cell.
    mode: "gated" → audio masked by survival; "underlay" → audio paints over alive cells,
          dead-cell pixels show the ruleset's own color (a dim gray).
    """
    if mode == "gated":
        return audio_layer * ruleset_output[..., None].astype(np.uint8)
    if mode == "underlay":
        underlay = np.where(ruleset_output[..., None], np.uint8(40), np.uint8(0))
        underlay = np.broadcast_to(underlay, audio_layer.shape).astype(np.uint8)
        audio_present = audio_layer.any(axis=-1, keepdims=True)
        return np.where(audio_present, audio_layer, underlay)
    raise ValueError(f"unknown compose mode: {mode}")
