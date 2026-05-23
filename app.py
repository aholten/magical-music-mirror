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

# Each palette is a list of RGB stops walked piecewise-linearly across the
# alive lifetime: stops[0] is the freshly-born "alive" color, stops[-1] is
# the background. Anything in between is a sweep through the palette.
#
# To add your own: pick 4–8 colors that read as a single mood and end on a
# dark "background" color. They get evenly distributed across --fade-ticks
# and the warp echo + screen fill both pick up the last stop automatically.
PALETTES = {
    "sunset": [
        (250, 240, 190),   # pale sun
        (255, 215, 130),   # warm gold
        (255, 155, 70),    # orange
        (235, 95, 70),     # coral
        (190, 55, 100),    # magenta
        (110, 45, 120),    # deep purple
        (40, 30, 80),      # twilight
        (10, 14, 36),      # night
    ],
    "ocean": [
        (220, 250, 255),   # foam
        (130, 220, 235),   # sea-green
        (60, 180, 220),    # bright blue
        (30, 110, 180),    # ocean blue
        (20, 60, 130),     # deep blue
        (10, 25, 60),      # abyss
        (5, 10, 25),       # black water
    ],
    "fire": [
        (255, 250, 210),   # white-hot
        (255, 220, 100),   # yellow flame
        (255, 140, 30),    # orange flame
        (220, 60, 30),     # red flame
        (140, 20, 20),     # ember
        (50, 10, 10),      # coal
        (10, 4, 4),        # ash
    ],
    "neon": [
        (255, 255, 255),   # white
        (255, 100, 220),   # hot pink
        (180, 60, 230),    # violet
        (90, 50, 220),     # electric blue
        (40, 100, 200),    # cobalt
        (20, 40, 100),     # deep
        (8, 10, 30),       # midnight
    ],
    "forest": [
        (240, 255, 220),   # mist
        (180, 230, 140),   # spring green
        (100, 180, 80),    # leaf
        (50, 130, 60),     # forest
        (30, 80, 50),      # moss
        (15, 40, 25),      # shadow
        (5, 15, 10),       # undergrowth
    ],
    "monochrome": [
        (255, 255, 255),   # white
        (190, 190, 195),   # light gray
        (130, 130, 140),   # gray
        (70, 70, 80),      # dark gray
        (25, 25, 35),      # near black
        (5, 5, 10),        # black
    ],
}


def _build_fade_table(stops: list, ticks: int, curve: float = 1.0) -> np.ndarray:
    """Piecewise-linear interpolation through `stops` over `ticks+1` entries.

    `curve` controls how stops are distributed across [0, ticks]:
      1.0   linear — every stop gets equal screen time.
      >1.0  exponential decay — early stops rush past, later stops linger.
            Sunset-like: yellow→orange blasts through quickly while the deep
            purples + twilight take most of the visible lifetime.
      <1.0  slow start, fast end — colors creep in gradually then collapse.

    The first stop is always at age 0 and the last stop at age `ticks`,
    regardless of curve.
    """
    ticks = max(1, ticks)
    stops_arr = np.asarray(stops, dtype=np.float32)
    curve = max(0.01, curve)
    # Stop positions along [0, ticks]. Linear linspace ** curve packs the
    # early stops near 0 (so age=0..small advances through many stops)
    # while pushing the last toward ticks. With curve=1 this reduces to
    # the original even distribution.
    positions = np.linspace(0, 1, len(stops)) ** curve
    stop_x = positions * ticks
    ages = np.arange(ticks + 1, dtype=np.float32)
    table = np.stack(
        [np.interp(ages, stop_x, stops_arr[:, c]) for c in range(3)],
        axis=1,
    )
    return table.clip(0, 255).astype(np.uint8)


def _build_warp_map_float(h: int, w: int, zoom: float, focal_y: float, focal_x: float):
    """Precompute the FLOAT source coordinates for the warp.

    Sampling at integer source coords is the standard nearest-neighbor warp,
    which produces hard "stair-step" bands when the per-pixel displacement
    is sub-pixel (everything within ~1/(zoom-1) of focal can't move at all).
    We keep the unrounded coords so the main loop can add temporal dither
    each frame and average to the true sub-pixel motion.

    focal_{y,x} are floats so the focal can sit between pixels — passing
    the true geometric center ((h-1)/2, (w-1)/2) on an even-sized grid
    produces a 2×2 stationary block at the center, symmetric across both
    axes.
    """
    ys, xs = np.indices((h, w)).astype(np.float32)
    src_y = focal_y + (ys - focal_y) / zoom
    src_x = focal_x + (xs - focal_x) / zoom
    return src_y, src_x


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
    ap.add_argument(
        "--resolution",
        type=int,
        default=1,
        help="Integer multiplier on the layout's grid size. 1 = chunky (90×160 "
        "for dual-mirror), 2 = double res, 4 = smooth, 8 = nearly per-window-"
        "pixel. Higher costs more CPU per frame (Conway step + warp sample + "
        "audio render all scale roughly with grid area).",
    )
    ap.add_argument("--palette", default="sunset", choices=PALETTES.keys())
    ap.add_argument(
        "--palette-curve",
        type=float,
        default=2.0,
        help="How non-linearly the palette is walked across an alive pixel's "
        "lifetime. 1.0 = linear (every color gets equal time). "
        "2.0 = exponential-decay feel (bright early colors rush past, dark "
        "tones linger — sunset-like). 3.0+ = aggressive front-load. "
        "0.5 = the opposite (slow start, sudden collapse to background).",
    )
    ap.add_argument("--samplerate", type=int, default=44100)
    ap.add_argument(
        "--debug",
        action="store_true",
        help="Print live audio-feature values (centroid, vocal_energy, "
        "stretched_vocal, fade_ticks_dyn) to stderr ~3× per second so "
        "you can verify what the modulators are actually reading.",
    )
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
        "--warp-fade-ticks",
        type=int,
        default=63,
        help="Frames for the warp echo to decay to ~1%% intensity (visually "
        "gone). Smaller = snappy short trails. Larger = lingering streams. "
        "At 60fps: 30=0.5s, 63=1s, 120=2s, 300=5s.",
    )
    ap.add_argument(
        "--warp-dither",
        type=float,
        default=1.0,
        help="Half-pixel jitter applied to warp source coords each frame. "
        "0.0 = fixed nearest-neighbor sampling (hard stair-step bands). "
        "1.0 = full ±0.5px stochastic rounding (smooth motion + film grain). "
        "2.0+ = pronounced grain texture.",
    )
    ap.add_argument(
        "--warp-focus-range",
        type=float,
        default=0.6,
        help="How far the warp focal point drifts vertically from the grid "
        "center, as a fraction of grid height, driven by the spectral "
        "centroid (bass = down, treble = up). 0.0 = static center, "
        "0.6 = up to ±30%%, 1.0 = focal can reach the edges. Negative "
        "values flip the direction.",
    )
    ap.add_argument(
        "--warp-focus-smoothing",
        type=float,
        default=0.30,
        help="Temporal smoothing applied to the centroid that drives the warp "
        "focal. 0.0 = raw, instant response (snappy/twitchy). 0.30 = brief "
        "smoothing (snappy default). 0.70 = leisurely drift. 0.90 = lazy.",
    )
    ap.add_argument(
        "--warp-focus-treble-bias",
        type=float,
        default=3.0,
        help="Counteracts the bass-dominated FFT magnitudes that pull the "
        "centroid (and thus the warp focal) toward the low end. 0.0 = raw "
        "centroid (heavily bass-skewed). 3.0 = treble bins count 4× bass "
        "(balanced default). 5.0+ = treble-led motion. Higher = hats and "
        "cymbals yank the focal up more aggressively.",
    )
    ap.add_argument(
        "--warp-fade-vocal",
        type=float,
        default=0.75,
        help="How sustained vocal-range content (200–4000 Hz) modulates "
        "warp trail length. The sign picks which end of the vocal axis "
        "carries the warp: "
        "+1.0 = vocals CAUSE warp (silence = no trails, vocals = full), "
        " 0.0 = no modulation (constant base trails), "
        "-1.0 = vocals KILL warp (silence = full trails, vocals = none). "
        "Values between scale the effect. Either extreme can fully zero "
        "the trails at the appropriate end.",
    )
    args = ap.parse_args()

    palette = PALETTES[args.palette]
    bg_color = palette[-1]  # last stop = background
    fade_table = _build_fade_table(palette, args.fade_ticks, curve=args.palette_curve)
    bg_pixel = np.array(bg_color, dtype=np.uint8)

    # warp_dim is recomputed each frame from a vocal-modulated fade_ticks
    # value (see main loop). The base/static value below is just an initial
    # placeholder before the loop runs.
    warp_dim = 0.01 ** (1.0 / max(1, args.warp_fade_ticks))

    layout = LAYOUTS[args.layout]
    res = max(1, args.resolution)
    audio_h, audio_w = (d * res for d in layout["audio_shape"])
    out_h, out_w = (d * res for d in layout["output_shape"])
    audio_transform = layout["audio_transform"]

    print(f"[startup] opening audio device: {args.device!r}", flush=True)
    capture = AudioCapture(device=args.device, samplerate=args.samplerate)
    print("[startup] starting audio stream", flush=True)
    capture.start()
    print("[startup] audio stream started", flush=True)

    audio_render = BarMeter(
        samplerate=args.samplerate,
        centroid_smoothing=args.warp_focus_smoothing,
        centroid_treble_bias=args.warp_focus_treble_bias,
    )
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
    pygame.display.set_caption(
        f"MagicalMusicMirror — {args.layout} / {args.ruleset} / {args.palette}"
    )
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
    # Warp focal: x stays fixed at the geometric center; y drifts vertically
    # each frame based on the spectral centroid (bass→down, treble→up).
    # Decompose `src_y = focal_y + (ys - focal_y) / zoom` into a precomputable
    # index part `ys/zoom` plus a per-frame scalar `focal_y * (1 - 1/zoom)`,
    # so the loop just does a scalar-add — no array re-creation per frame.
    ys_arr, xs_arr = np.indices((out_h, out_w)).astype(np.float32)
    focal_x_static = (out_w - 1) / 2.0
    center_y = (out_h - 1) / 2.0
    warp_x_float = focal_x_static + (xs_arr - focal_x_static) / args.warp_zoom
    warp_y_index_part = ys_arr / args.warp_zoom
    warp_y_focal_factor = 1.0 - 1.0 / args.warp_zoom
    warp_rng = np.random.default_rng()
    bg_float = np.array(bg_color, dtype=np.float32)
    prev_display = np.empty((out_h, out_w, 3), dtype=np.uint8)
    prev_display[:] = bg_pixel

    frame_count = 0
    try:
        running = True
        while running:
            frame_count += 1
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False

            audio_frame = capture.latest()
            audio_small = audio_render.render(audio_frame, (audio_h, audio_w))
            audio_layer = audio_transform(audio_small)
            ruleset_out = ruleset.step(prev_frame=None, audio_layer=audio_layer)
            composed = compose(audio_layer, ruleset_out, mode=ruleset.compose_mode)

            # Dynamic warp focal: shift y based on the centroid (already
            # treble-biased + smoothed inside BarMeter) so bass-heavy
            # content emanates from below center and treble from above.
            focal_y = center_y + (0.5 - audio_render.centroid) * out_h * args.warp_focus_range
            warp_y_float = focal_y * warp_y_focal_factor + warp_y_index_part

            # Dynamic warp fade: vocal-range level modulates trail length.
            # vocal_energy is the smoothed absolute mid-band level (0..~0.7);
            # stretch around 0.20 by 3× to map instrumental (~0.30) toward
            # stretched≈0.30 and loud vocals (~0.55+) to a saturated 1.0.
            #
            # Sign of WARP_FADE_VOCAL picks WHICH end of the vocal axis
            # carries the warp trails:
            #   +1.0  vocals CAUSE warp  (silence = no trails, vocals = full)
            #    0.0  no modulation      (constant base trails)
            #   -1.0  vocals KILL warp   (silence = full trails, vocals = none)
            # Either extreme drives the multiplier to ≈0 at the "off" end;
            # below 0.01 we bypass the warp blend entirely so trails are
            # genuinely off, not just very faint.
            stretched_vocal = max(0.0, min(1.0, (audio_render.vocal_energy - 0.20) * 3.0))
            v = args.warp_fade_vocal
            if v >= 0:
                # Positive: vocals turn the warp ON. Silence sits at (1-v),
                # peak vocals sit at 1.0 (base trails).
                mult = (1.0 - v) + v * stretched_vocal
            else:
                # Negative: vocals turn the warp OFF. Silence sits at 1.0,
                # peak vocals sit at (1+v).
                mult = 1.0 + v * stretched_vocal
            mult = max(0.0, min(4.0, mult))
            if mult < 0.01:
                warp_dim = 0.0  # trails off — warped will collapse to bg
                fade_ticks_dyn = 0
            else:
                fade_ticks_dyn = max(1, int(args.warp_fade_ticks * mult))
                warp_dim = 0.01 ** (1.0 / fade_ticks_dyn)

            if args.debug and frame_count % 20 == 0:
                print(
                    f"[audio] centroid={audio_render.centroid:.3f} "
                    f"vocal_energy={audio_render.vocal_energy:.3f} "
                    f"stretched_vocal={stretched_vocal:.3f} "
                    f"mult={mult:.3f} fade_ticks_dyn={fade_ticks_dyn}",
                    flush=True,
                )

            # Warp echo: zoom the previous frame outward from the (dynamic)
            # focal with per-frame stochastic rounding (sub-pixel dither),
            # then decay toward the background. Result fills dead-pixel
            # slots and reads as content receding outward.
            j = args.warp_dither * 0.5
            sy = np.round(warp_y_float + warp_rng.uniform(-j, j, warp_y_float.shape)).astype(np.int32)
            sx = np.round(warp_x_float + warp_rng.uniform(-j, j, warp_x_float.shape)).astype(np.int32)
            np.clip(sy, 0, out_h - 1, out=sy)
            np.clip(sx, 0, out_w - 1, out=sx)
            warped = prev_display[sy, sx].astype(np.float32)
            warped = warped * warp_dim + bg_float * (1.0 - warp_dim)
            warped = warped.clip(0, 255).astype(np.uint8)

            # Age the alive pixels and look up their faded color. New births
            # pop bright; dead pixels show the warped echo of recent frames.
            # The leading edge of each audio bar (R==1 sentinel from BarMeter)
            # is force-reset to age 0 every frame so the tip always reads as
            # the initial palette color, while the body ages normally.
            alive = composed.any(axis=-1)
            age = np.where(alive, np.minimum(age + 1, args.fade_ticks), 0)
            bar_edge = composed[..., 0] == 1
            age = np.where(bar_edge, 0, age)
            display = fade_table[age]
            display = np.where(alive[..., None], display, warped)
            prev_display = display

            pygame.surfarray.blit_array(src_surface, np.transpose(display, (1, 0, 2)))
            scaled = pygame.transform.scale(src_surface, (scaled_w, scaled_h))
            screen.fill(bg_color)
            screen.blit(scaled, (x_off, y_off))
            pygame.display.flip()
            clock.tick(TARGET_FPS)
    finally:
        capture.stop()
        pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
