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
        # Dim teal-green for alive Conway cells so they're visibly distinct
        # from the magenta/blue audio bars without competing for attention.
        underlay = np.zeros_like(audio_layer)
        underlay[..., 1] = (ruleset_output * 110).astype(np.uint8)  # G
        underlay[..., 2] = (ruleset_output * 70).astype(np.uint8)   # B
        audio_present = audio_layer.any(axis=-1, keepdims=True)
        return np.where(audio_present, audio_layer, underlay)
    raise ValueError(f"unknown compose mode: {mode}")
