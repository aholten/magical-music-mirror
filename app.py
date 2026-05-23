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

# Night-sky background and warm pale-yellow alive color. Alive pixels start
# at ALIVE_COLOR (age 0) and linearly blend toward BG_COLOR as they age,
# reaching the background after --fade-ticks frames — so persistent regions
# slowly "fade into the night". On death, age resets to 0 and the pixel
# disappears into the background until something brings it back to life.
BG_COLOR = (10, 14, 36)
ALIVE_COLOR = (250, 240, 190)


def _build_fade_table(alive_rgb: tuple, bg_rgb: tuple, ticks: int) -> np.ndarray:
    """Linear-blend table: table[i] is the color at age i (clamped to ticks).

    Index 0 = full alive color; index `ticks` = full background.
    """
    ticks = max(1, ticks)
    ages = np.arange(ticks + 1, dtype=np.float32).reshape(-1, 1)
    t = ages / ticks  # 0 → 1 across the table
    alive = np.array(alive_rgb, dtype=np.float32).reshape(1, 3)
    bg = np.array(bg_rgb, dtype=np.float32).reshape(1, 3)
    return ((1 - t) * alive + t * bg).clip(0, 255).astype(np.uint8)


def _build_warp_map(h: int, w: int, zoom: float, focal_y: int, focal_x: int):
    """Precompute integer source-index arrays for a per-frame zoom-outward
    warp. Sampling prev[warp_ys, warp_xs] gives a copy scaled by `zoom`
    around the focal point: content recedes away from focal each tick."""
    ys, xs = np.indices((h, w))
    src_ys = (focal_y + (ys - focal_y) / zoom).astype(np.int32)
    src_xs = (focal_x + (xs - focal_x) / zoom).astype(np.int32)
    np.clip(src_ys, 0, h - 1, out=src_ys)
    np.clip(src_xs, 0, w - 1, out=src_xs)
    return src_ys, src_xs


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
    ap.add_argument(
        "--fade-ticks",
        type=int,
        default=120,
        help="Frames an alive pixel takes to fade from ALIVE_COLOR to BG_COLOR. "
        "Smaller = quicker fade (snappy/strobey). Larger = slower fade (smoother trails). "
        "At 60 fps: 60=1s, 120=2s, 300=5s, 600=10s.",
    )
    ap.add_argument(
        "--warp-zoom",
        type=float,
        default=1.04,
        help="Per-frame zoom factor for the warp-drive echo. 1.0 = no motion, "
        "1.02 = subtle drift outward, 1.04 = noticeable hyperspace pull, "
        "1.08 = aggressive (echoes fly off-screen fast).",
    )
    ap.add_argument(
        "--warp-dim",
        type=float,
        default=0.93,
        help="Per-frame brightness decay (toward BG_COLOR) applied to the warp "
        "echo. 1.0 = echoes never decay (trails fill the screen). "
        "0.93 = ~1s visible trail at 60fps. 0.85 = short, snappy trails.",
    )
    args = ap.parse_args()

    fade_table = _build_fade_table(ALIVE_COLOR, BG_COLOR, args.fade_ticks)
    bg_pixel = np.array(BG_COLOR, dtype=np.uint8)

    layout = LAYOUTS[args.layout]
    audio_h, audio_w = layout["audio_shape"]
    out_h, out_w = layout["output_shape"]
    audio_transform = layout["audio_transform"]

    print(f"[startup] opening audio device: {args.device!r}", flush=True)
    capture = AudioCapture(device=args.device, samplerate=args.samplerate)
    print("[startup] starting audio stream", flush=True)
    capture.start()
    print("[startup] audio stream started", flush=True)

    audio_render = BarMeter(samplerate=args.samplerate)
    ruleset = VARIANTS[args.ruleset]((out_h, out_w))
    print(f"[startup] ruleset {args.ruleset} initialized at {(out_h, out_w)}", flush=True)

    # Only init pygame.display — pygame.init() would also bring up
    # pygame.mixer, which races sounddevice/PortAudio for the audio
    # device on macOS and deadlocks. We don't use pygame audio at all.
    print("[startup] pygame.display.init()", flush=True)
    pygame.display.init()
    print("[startup] opening window", flush=True)
    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    print("[startup] window open, entering main loop", flush=True)
    pygame.display.set_caption(f"MagicalMusicMirror — {args.layout} / {args.ruleset}")
    clock = pygame.time.Clock()
    src_surface = pygame.Surface((out_w, out_h))

    scale = max(1, min(WINDOW_W // out_w, WINDOW_H // out_h))
    scaled_w, scaled_h = out_w * scale, out_h * scale
    x_off = (WINDOW_W - scaled_w) // 2
    y_off = (WINDOW_H - scaled_h) // 2

    # Per-pixel age counter for the fade table. Reset to 0 on death.
    age = np.zeros((out_h, out_w), dtype=np.int32)

    # Warp echo state. prev_display gets zoomed and dimmed each frame to
    # become the next frame's background-where-pixels-are-dead, producing
    # the warp-drive trails. Start at solid background.
    warp_ys, warp_xs = _build_warp_map(out_h, out_w, args.warp_zoom, out_h // 2, out_w // 2)
    bg_float = np.array(BG_COLOR, dtype=np.float32)
    prev_display = np.empty((out_h, out_w, 3), dtype=np.uint8)
    prev_display[:] = bg_pixel

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
            composed = compose(audio_layer, ruleset_out, mode=ruleset.compose_mode)

            # Warp echo: zoom the previous frame outward from the center,
            # then decay it toward the background. This is what fills the
            # "dead pixel" slots — the result reads as content receding
            # into the distance.
            warped = prev_display[warp_ys, warp_xs].astype(np.float32)
            warped = warped * args.warp_dim + bg_float * (1.0 - args.warp_dim)
            warped = warped.clip(0, 255).astype(np.uint8)

            # Age the alive pixels and look up their faded color. New births
            # pop bright; dead pixels show the warped echo of recent frames.
            alive = composed.any(axis=-1)
            age = np.where(alive, np.minimum(age + 1, args.fade_ticks), 0)
            display = fade_table[age]
            display = np.where(alive[..., None], display, warped)
            prev_display = display

            pygame.surfarray.blit_array(src_surface, np.transpose(display, (1, 0, 2)))
            scaled = pygame.transform.scale(src_surface, (scaled_w, scaled_h))
            screen.fill(BG_COLOR)
            screen.blit(scaled, (x_off, y_off))
            pygame.display.flip()
            clock.tick(TARGET_FPS)
    finally:
        capture.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
