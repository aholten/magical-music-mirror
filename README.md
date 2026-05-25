# MagicalMusicMirror

A local music visualizer that runs on macOS and visualizes whatever is playing through system audio (Spotify, Apple Music, browser, anything). Pure local — no networking, no streaming. Frequency-driven audio bars, Conway's Game of Life cellular automaton underlay, audio-reactive warp-drive motion, sunset-style color aging, and Balatro-style CRT post-processing.

## Quickstart (macOS)

1. **Install [BlackHole 2ch](https://existential.audio/blackhole/)** — virtual audio loopback driver:
   ```bash
   brew install --cask blackhole-2ch
   ```
2. **Create a Multi-Output Device** in *Audio MIDI Setup*:
   - Click the `+` in the bottom-left → *Create Multi-Output Device*.
   - Check both your real speakers/headphones **and** `BlackHole 2ch`.
   - Set "Master Device" to your real speakers and enable "Drift Correction" on the BlackHole row.
   - In *System Settings → Sound → Output*, pick the Multi-Output Device.
   (You'll hear audio normally; BlackHole gets a copy that the visualizer reads.)
3. **Clone and run:**
   ```bash
   git clone https://github.com/aholten/magical-music-mirror.git
   cd magical-music-mirror
   make run         # creates .venv, installs deps, launches with defaults
   ```
4. Other useful targets:
   ```bash
   make devices    # list audio input devices (confirm BlackHole's exact name)
   make help       # see common one-line tuning recipes
   make clean      # delete .venv
   ```

Press `ESC` or close the window to exit.

---

## Configuration knobs

Every knob is a Makefile variable, a CLI flag, or both. Override at runtime:

```bash
make run PALETTE=ocean RESOLUTION=2 WARP_FADE_VOCAL=1.0 HUD=1
```

### 1. Layout — how the visualizer is arranged on screen

| Knob | Default | Values | What it does |
|---|---|---|---|
| `LAYOUT` | `dual-mirror` | `dual-mirror`, `butterfly` | Picks the geometric arrangement of bars + Conway field. |

- **`dual-mirror`** — two stacked visualizers reaching toward the horizontal midline. Bottom half: bass-left → treble-right, bars grow up. Top half: bars grow down (treble-left/bass-right per a 180° rotation), pixel-identical to bottom mirror except for the translation. Fills a 16:9 window cleanly at integer scale.
- **`butterfly`** — visualizer rotated 90° CCW + horizontally mirrored. Bass at bottom, treble at top, bars extend outward from a central vertical axis. Letterboxed left/right at integer scale (9:8-ish aspect).

In both layouts, Conway evolves on **one continuous field across the whole output**, so the underlay pattern is continuous (not flipped at the seam).

### 2. Resolution — how chunky vs smooth the pixels are

| Knob | Default | Values | Effect |
|---|---|---|---|
| `RESOLUTION` | `1` | integer ≥1 | Multiplier on the layout's base grid size. |

`1` = chunky retro look (90×160 grid for dual-mirror, 8× pygame scale). `2` doubles everything (180×320, 4× scale). `4` is smooth (360×640, 2× scale). `8` is per-window-pixel (basically no scaling). CRT scanlines get finer as `RESOLUTION` rises — chunky 8-pixel scanlines at `1`, fine 1–2-pixel scanlines at `4`. Per-frame work scales with grid area, so `8` is the practical performance cliff.

### 3. Conway variants (RenderRuleset genes)

| Knob | Default | Values | Genes |
|---|---|---|---|
| `RULESET` | `conway11` | `conway00`, `conway01`, `conway10`, `conway11` | See below |

Conway is parameterized by two genes. Naming: `conway<g0><g1>`.

- **Gene 0 — composition rule**
  - `0` = **Gated**: survival mask stencils the audio layer; non-surviving cells go dark.
  - `1` = **Underlay**: ruleset evolves its own buffer; audio paints over survivors and Life keeps running underneath.
- **Gene 1 — state boundary**
  - `0` = **Audio-seeded**: loud audio bands birth Conway cells.
  - `1` = **Isolated**: Conway evolves on its own, no audio input.

| Variant | Composition | Audio → Conway? | Visual character |
|---|---|---|---|
| `conway00` | Gated | Yes | Audio births cells, mask gates the audio output |
| `conway01` | Gated | No | Conway field stencils the audio (drum-machine pattern feel) |
| `conway10` | Underlay | Yes | Audio births cells, Conway runs as underlay — most "reactive" |
| `conway11` (default) | Underlay | No | Conway evolves independently underneath audio bars (most cinematic) |

Conway uses **horizontal wrap** but **hard top/bottom walls** — patterns drift across the left/right seam but don't loop vertically.

### 4. Palette — the color sweep aged pixels walk through

| Knob | Default | Values |
|---|---|---|
| `PALETTE` | `sunset` | `sunset`, `ocean`, `fire`, `neon`, `forest`, `monochrome` |
| `PALETTE_CURVE` | `2.0` | float ≥0 |
| `FADE_TICKS` | `120` | frame count |

Every alive pixel walks from a "fresh" color (palette stop 0) through the palette to a "dead" background color (palette's last stop), then disappears. The background of the whole screen (letterbox bars, dead pixels, warp-decay target) is automatically derived from the palette's final stop.

| Palette | Sweep |
|---|---|
| `sunset` | pale yellow → gold → orange → coral → magenta → deep purple → twilight → night |
| `ocean` | foam → sea-green → blue → deep blue → abyss → black water |
| `fire` | white-hot → yellow → orange → red → ember → coal → ash |
| `neon` | white → hot pink → violet → electric blue → cobalt → midnight |
| `forest` | mist → spring green → leaf → forest → moss → undergrowth |
| `monochrome` | white → light gray → gray → dark gray → black |

**`PALETTE_CURVE`**: how non-linearly the palette is walked.
- `1.0` = linear (every color equal time).
- `2.0` (default) = exponential decay (bright early colors rush past, dark tones linger). Sunset-feel.
- `3.0+` = aggressive front-load.
- `0.5` = opposite (slow start, sudden collapse to background).

**`FADE_TICKS`**: how many frames a pixel takes to fully fade from birth color to background. `60 ≈ 1s`, `300 ≈ 5s` at 60 fps.

**Special bar-tip behavior**: the leading edge (top row) of each audio bar is force-reset to age 0 every frame, so the tip always shows the freshly-born palette color while the body of the bar ages normally. The bright tip with colorful trail effect.

### 5. Warp drive — frame-feedback motion overlay

Each frame, the previous output is sampled with a zoom-outward warp + dim toward background, then composed under the new frame. The result reads as content receding outward.

#### Static motion knobs

| Knob | Default | Effect |
|---|---|---|
| `WARP_ZOOM` | `1.04` | Per-frame zoom factor. `1.0` = no motion. `1.02` = subtle drift. `1.04` = noticeable hyperspace. `1.08+` = aggressive. |
| `WARP_FADE_TICKS` | `63` | How many frames until the echo decays to ~1% intensity. Matches `FADE_TICKS` semantics (higher = longer trail). `30 ≈ 0.5s`, `300 ≈ 5s`. |
| `WARP_DITHER` | `1.0` | Sub-pixel jitter on the warp source coords each frame. `0.0` = hard stair-step bands. `1.0` = smooth motion + film grain. `2.0+` = pronounced grain texture. |

#### Audio-reactive warp focal (vertical drift)

The "vanishing point" of the warp drifts vertically based on the spectral centroid of the audio.

| Knob | Default | Effect |
|---|---|---|
| `WARP_FOCUS_RANGE` | `0.6` | How far the focal can travel from center as a fraction of grid height. `0.0` = locked at center. `0.6` = ±30%. `1.0` = focal can reach the edges. Negative = flip direction. |
| `WARP_FOCUS_SMOOTHING` | `0.30` | Temporal smoothing on the centroid. `0.0` = raw, instant response (twitchy). `0.30` = snappy. `0.70` = leisurely drift. |
| `WARP_FOCUS_TREBLE_BIAS` | `3.0` | Linear ramp weighting on high-frequency bars when computing centroid. `0.0` = raw (focal mostly hugs the bass end). `3.0` = treble bins count 4× bass (balanced). `5.0+` = treble-led motion. |

**Direction convention**: bass → focal down, treble → focal up.

#### Audio-reactive warp fade (vocal-driven trail length)

The length of the warp trail is modulated by the energy in a vocal-frequency band.

| Knob | Default | Effect |
|---|---|---|
| `WARP_FADE_VOCAL` | `0.75` | Magnitude and direction of vocal modulation. See sign table below. |
| `VOCAL_BAND_LO` | `200` | Low edge of the vocal-energy band (Hz). |
| `VOCAL_BAND_HI` | `4000` | High edge of the vocal-energy band (Hz). |

**`WARP_FADE_VOCAL` sign convention** (positive = vocals *cause* warp):

| Value | Silence | Sustained vocals |
|---|---|---|
| `+1.0` | **no trails** | full base trails |
| `+0.75` (default) | short trails (~25% length) | full base trails |
| `0.0` | full base trails (no modulation) | full base trails |
| `-0.75` | full base trails | short trails (~25%) |
| `-1.0` | full base trails | **no trails** |

Either extreme drives the trail multiplier to zero on the appropriate end.

**Vocal band tuning** — the default `200–4000 Hz` is wide and catches percussion/cymbals too. Tighten for vocal-only response:

```bash
make run VOCAL_BAND_LO=250 VOCAL_BAND_HI=1500   # vocal fundamentals + first formant
make run VOCAL_BAND_LO=300 VOCAL_BAND_HI=1200   # exclude cymbals/hats entirely
make run VOCAL_BAND_LO=80  VOCAL_BAND_HI=200    # bass-only (use as an inverse trigger)
```

### 6. CRT post-processing — Balatro-style screen effects

All applied at grid resolution after compositing (so they scale with `RESOLUTION`). The CRT pass operates only on the rendered frame — it does *not* feed back into the warp, so scanlines don't compound through the feedback loop.

| Knob | Default | Effect |
|---|---|---|
| `CRT_SCANLINES` | `0.15` | Brightness reduction on alternate grid rows. `0` = off, `0.4` = pronounced, `0.8` = aggressive. |
| `CRT_ROLLING` | `0.10` | Brightness boost of a smooth gaussian band that scrolls vertically at a fixed ~3-second period (CRT vertical-sync drift). `0` = off, `0.3` = obvious. |
| `CRT_CHROMATIC` | `1` | Horizontal shift of R/B channels in grid pixels (CRT shadow-mask misalignment). `0` = off, `2-3` = heavy fringing. |
| `CRT_BLOOM` | `0.25` | Bright regions glow into neighbors via 5-point cross blur. `0` = off, `0.6` = strong, `1.0` = saturated. |

To kill all CRT effects:
```bash
make run CRT_SCANLINES=0 CRT_ROLLING=0 CRT_CHROMATIC=0 CRT_BLOOM=0
```

### 7. Debugging & live tuning

| Knob | Default | Effect |
|---|---|---|
| `DEBUG` | (off) | Set to `1` to print live audio-feature values to stderr ~3× per second: `centroid`, `vocal_energy`, `stretched_vocal`, `mult`, `fade_ticks_dyn`. |
| `HUD` | (off) | Set to `1` to overlay an on-screen tuning HUD: numeric readouts, colored bars, focal_y marker line, and a translucent bracket on the actual visualizer marking the vocal-sensitivity range. |

```bash
make run HUD=1 DEBUG=1    # both — visual + terminal printouts
```

### 8. Audio device

| Knob | Default | Effect |
|---|---|---|
| `DEVICE` | `BlackHole 2ch` | sounddevice input name or index. |

Find your device name:
```bash
make devices
```

---

## Architecture

**Stack**: Python 3 + `sounddevice` (PortAudio) + `numpy` + `pygame`.

**Render loop** (per frame, 60 fps target):

```
audio_capture.latest()                     ── 8192-sample rolling buffer
        │
        ▼
BarMeter.render(audio_h, audio_w)          ── FFT → log-spaced bars + sentinels
        │
        ▼
audio_transform(audio)                     ── layout-specific reshape
        │
        ▼
Conway.step(prev, audio)                   ── one generation @ output shape
        │
        ▼
compose(audio, conway, mode)               ── per gene-0
        │
        ▼
age + fade_table[age] + warped echo        ── color, motion, decay
        │
        ▼
prev_display = display (un-CRT'd)          ── captured here for next-frame warp
        │
        ▼
apply_crt(display, frame_count)            ── CA, bloom, scanlines, rolling bar
        │
        ▼
pygame.surfarray.blit_array → scale → blit
        │
        ▼
HUD overlay (if enabled)                   ── tuning panel + focal_y marker + vocal bracket
```

**Key signals**:

- `audio_render.centroid` — treble-biased smoothed spectral centroid `[0,1]`, drives warp `focal_y`.
- `audio_render.vocal_energy` — smoothed mean of bars in `[VOCAL_BAND_LO, VOCAL_BAND_HI]`, drives warp fade modulation.
- `audio_render._vocal_lo / _vocal_hi` — bar indices spanning the configured vocal band (exposed for the HUD bracket).

**Theme interface**:

```python
class AudioRender:
    def render(self, audio_frame: np.ndarray, shape: tuple[int, int]) -> np.ndarray: ...

class RenderRuleset:
    genes: list[Gene]
    compose_mode: str  # "gated" or "underlay"
    def step(self, prev_frame: np.ndarray, audio_layer: np.ndarray) -> np.ndarray: ...
```

---

## Tuning the warp-fade-vocal effect

This is the trickiest knob set. Workflow:

1. Run with the HUD on:
   ```bash
   make run HUD=1
   ```
2. Watch the **V** (vocal_energy), **S** (stretched_vocal), and **M** (mult) values during instrumental vs vocal sections.
3. Watch the **orange bracket** on the visualizer — it's drawn over the column range that contributes to V, and its brightness pulses with S.
4. Diagnose:
   - **V flat across vocal/instrumental** → band too wide. Narrow with `VOCAL_BAND_LO/HI`.
   - **V moves but S stays near 0** → vocal_energy isn't reaching the stretch threshold. Either bump magnitude with louder music, or narrow the band to concentrate energy.
   - **S moves but M stays flat** → `WARP_FADE_VOCAL` magnitude too low. Try `±1.0`.
   - **M swings but trails look the same** → `WARP_FADE_TICKS` base is too short for the % change to be visible. Try `200`.

Recommended starting point for vocal-driven warp:

```bash
make run HUD=1 \
  WARP_FADE_TICKS=200 \
  WARP_FADE_VOCAL=1.0 \
  VOCAL_BAND_LO=250 VOCAL_BAND_HI=1500 \
  WARP_ZOOM=1.05
```

---

## Repo layout

```
.
├── app.py                       # main entry: arg parsing, render loop, HUD, CRT
├── engine/
│   ├── audio_capture.py         # sounddevice ring buffer
│   ├── compositor.py            # audio + ruleset → final frame (per gene-0)
│   └── genes.py                 # Gene dataclass for ruleset declarations
├── themes/
│   ├── audio/
│   │   └── bar_meter.py         # BarMeter AudioRender (FFT + centroid + vocal_energy)
│   └── ruleset/
│       └── conway.py            # ConwayRenderRuleset00/01/10/11
├── Makefile                     # one-line install + run with every knob exposed
└── requirements.txt
```

---

## Origin

Started as [aholten/selfhost#198](https://github.com/aholten/selfhost/issues/198), moved to its own repo because it's a native macOS desktop app and doesn't fit the GitOps-for-homelab-infrastructure model of that project.
