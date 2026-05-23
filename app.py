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


GRID_W, GRID_H = 160, 90
SCALE = 8  # window = 1280×720
TARGET_FPS = 60

# After CCW rotation + horizontal mirror, the visible image is
# (GRID_W) tall × (2 * GRID_H) wide — i.e. the frequency axis runs
# bottom→top and bars extend outward from a vertical center axis.
MIRROR_H = GRID_W
MIRROR_W = 2 * GRID_H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", help="Input device name or index (e.g. 'BlackHole 2ch')")
    ap.add_argument("--ruleset", default="conway11", choices=VARIANTS.keys())
    ap.add_argument("--samplerate", type=int, default=44100)
    args = ap.parse_args()

    capture = AudioCapture(device=args.device, samplerate=args.samplerate)
    capture.start()

    audio_render = BarMeter(samplerate=args.samplerate)
    ruleset = VARIANTS[args.ruleset]((GRID_H, GRID_W))

    pygame.init()
    screen = pygame.display.set_mode((GRID_W * SCALE, GRID_H * SCALE))
    pygame.display.set_caption(f"MagicalMusicMirror — {args.ruleset}")
    clock = pygame.time.Clock()
    src_surface = pygame.Surface((MIRROR_W, MIRROR_H))

    # Compute one-time scale that fits the rotated+mirrored frame inside the
    # window with integer pixel scaling (chunky look). Black-letterboxed on
    # the sides since the rotated aspect (9:8-ish) is narrower than 16:9.
    window_w, window_h = screen.get_size()
    scale = max(1, min(window_w // MIRROR_W, window_h // MIRROR_H))
    scaled_w, scaled_h = MIRROR_W * scale, MIRROR_H * scale
    x_off = (window_w - scaled_w) // 2
    y_off = (window_h - scaled_h) // 2

    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False

            audio_frame = capture.latest()
            audio_layer = audio_render.render(audio_frame, (GRID_H, GRID_W))
            ruleset_out = ruleset.step(prev_frame=None, audio_layer=audio_layer)
            final = compose(audio_layer, ruleset_out, mode=ruleset.compose_mode)

            # Rotate 90° CCW (bars become horizontal, low freq at bottom),
            # then mirror: concat original|fliplr so bars extend outward
            # from the vertical center axis.
            rotated = np.rot90(final, k=1)
            mirrored = np.concatenate([rotated, np.fliplr(rotated)], axis=1)

            pygame.surfarray.blit_array(src_surface, np.transpose(mirrored, (1, 0, 2)))
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
