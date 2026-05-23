"""MagicalMusicMirror — MVP.

Reads system audio from a loopback input device (BlackHole on macOS) and
visualizes it via a pluggable AudioRender + RenderRuleset pair.
"""

import argparse
import sys

import numpy as np
import pygame

from engine.audio_capture import AudioCapture
from engine.compositor import compose
from themes.audio.bar_meter import BarMeter
from themes.ruleset.conway import VARIANTS


WINDOW_W, WINDOW_H = 1280, 720
TARGET_FPS = 60


# --- Layouts -----------------------------------------------------------------
#
# A layout splits the pipeline in two:
#   audio_shape:     (H, W) AudioRender draws onto (just the audio bars)
#   audio_transform: callable(small_audio) -> output-sized audio frame; produces
#                    the mirrored/rotated bar layout
#   output_shape:    (H, W) of the final visible frame; the RenderRuleset
#                    (Conway) runs at this full size, so its pattern is one
#                    continuous field across the entire screen rather than a
#                    per-half copy.
#
# Compose then mixes the mirrored audio frame and the full-screen ruleset
# frame at output_shape.


def butterfly_transform(audio: np.ndarray) -> np.ndarray:
    """Rotate 90° CCW + horizontal mirror. Bars extend outward from a
    vertical center line; bass at bottom, treble at top."""
    rotated = np.rot90(audio, k=1)
    return np.concatenate([rotated, np.fliplr(rotated)], axis=1)


def dual_mirror_transform(audio: np.ndarray) -> np.ndarray:
    """Stack the rendered half-frame against its 180° rotation. Bottom
    visualizer: bass-left/treble-right, bars grow up toward the middle.
    Top visualizer: treble-left/bass-right, bars grow down toward the
    middle. Both reach only to the horizontal midline."""
    return np.concatenate([np.rot90(audio, k=2), audio], axis=0)


LAYOUTS = {
    "butterfly": {
        "audio_shape": (90, 160),
        "audio_transform": butterfly_transform,
        "output_shape": (160, 180),
    },
    "dual-mirror": {
        "audio_shape": (45, 160),
        "audio_transform": dual_mirror_transform,
        "output_shape": (90, 160),
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", help="Input device name or index (e.g. 'BlackHole 2ch')")
    ap.add_argument("--ruleset", default="conway11", choices=VARIANTS.keys())
    ap.add_argument("--layout", default="dual-mirror", choices=LAYOUTS.keys())
    ap.add_argument("--samplerate", type=int, default=44100)
    args = ap.parse_args()

    layout = LAYOUTS[args.layout]
    audio_h, audio_w = layout["audio_shape"]
    out_h, out_w = layout["output_shape"]
    audio_transform = layout["audio_transform"]

    capture = AudioCapture(device=args.device, samplerate=args.samplerate)
    capture.start()

    audio_render = BarMeter(samplerate=args.samplerate)
    ruleset = VARIANTS[args.ruleset]((out_h, out_w))

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption(f"MagicalMusicMirror — {args.layout} / {args.ruleset}")
    clock = pygame.time.Clock()
    src_surface = pygame.Surface((out_w, out_h))

    scale = max(1, min(WINDOW_W // out_w, WINDOW_H // out_h))
    scaled_w, scaled_h = out_w * scale, out_h * scale
    x_off = (WINDOW_W - scaled_w) // 2
    y_off = (WINDOW_H - scaled_h) // 2

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False

            audio_frame = capture.latest()
            audio_small = audio_render.render(audio_frame, (audio_h, audio_w))
            audio_layer = audio_transform(audio_small)
            ruleset_out = ruleset.step(prev_frame=None, audio_layer=audio_layer)
            display = compose(audio_layer, ruleset_out, mode=ruleset.compose_mode)

            pygame.surfarray.blit_array(src_surface, np.transpose(display, (1, 0, 2)))
            scaled = pygame.transform.scale(src_surface, (scaled_w, scaled_h))
            screen.fill((0, 0, 0))
            screen.blit(scaled, (x_off, y_off))
            pygame.display.flip()
            clock.tick(TARGET_FPS)
    finally:
        capture.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
