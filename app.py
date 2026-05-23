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
    grid_surface = pygame.Surface((GRID_W, GRID_H))

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

            pygame.surfarray.blit_array(grid_surface, np.transpose(final, (1, 0, 2)))
            scaled = pygame.transform.scale(grid_surface, screen.get_size())
            screen.blit(scaled, (0, 0))
            pygame.display.flip()
            clock.tick(TARGET_FPS)
    finally:
        capture.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
