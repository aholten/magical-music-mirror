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
# Each layout owns:
#   render_shape: (H, W) that AudioRender + RenderRuleset draw onto
#   transform:    callable(np.ndarray) -> np.ndarray, applied per frame to
#                 produce the displayed image
#   output_shape: (H, W) of the transform output, used for sizing the pygame
#                 source surface and computing the window-fit scale
#
# Conway runs at render_shape; the transform only ever combines copies of the
# composed frame, so the two halves of a mirror are pixel-identical except
# for the layout's translation/rotation.


def butterfly_transform(frame: np.ndarray) -> np.ndarray:
    """Rotate 90° CCW + horizontal mirror. Bars extend outward from a
    vertical center line; bass at bottom, treble at top."""
    rotated = np.rot90(frame, k=1)
    return np.concatenate([rotated, np.fliplr(rotated)], axis=1)


def dual_mirror_transform(frame: np.ndarray) -> np.ndarray:
    """Stack the rendered half-frame against its 180° rotation. Bottom
    visualizer: bass-left/treble-right, bars grow up toward the middle.
    Top visualizer: treble-left/bass-right, bars grow down toward the
    middle. Both visualizers reach only as far as the horizontal midline."""
    return np.concatenate([np.rot90(frame, k=2), frame], axis=0)


LAYOUTS = {
    "butterfly": {
        "render_shape": (90, 160),
        "transform": butterfly_transform,
        "output_shape": (160, 180),
    },
    "dual-mirror": {
        "render_shape": (45, 160),
        "transform": dual_mirror_transform,
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
    render_h, render_w = layout["render_shape"]
    out_h, out_w = layout["output_shape"]
    transform = layout["transform"]

    capture = AudioCapture(device=args.device, samplerate=args.samplerate)
    capture.start()

    audio_render = BarMeter(samplerate=args.samplerate)
    ruleset = VARIANTS[args.ruleset]((render_h, render_w))

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
            audio_layer = audio_render.render(audio_frame, (render_h, render_w))
            ruleset_out = ruleset.step(prev_frame=None, audio_layer=audio_layer)
            final = compose(audio_layer, ruleset_out, mode=ruleset.compose_mode)
            display = transform(final)

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
