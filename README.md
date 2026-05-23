# MagicalMusicMirror

A local music visualizer that runs on macOS and visualizes whatever is playing through system audio (Spotify, Apple Music, browser, anything). Pure local — no networking, no streaming.

Architecturally, a visualizer scene is composed of two pluggable theme components:

- **AudioRender** — pure function of the current audio frame → a layer of pixels.
- **RenderRuleset** — pure function of the previous frame → a per-pixel survival mask or evolved buffer.

The MVP ships one of each: a `BarMeter` AudioRender (FFT, low→high left→right) and a Conway's Game of Life RenderRuleset with four gene-parameterized variants.

## Quickstart (macOS)

1. **Install [BlackHole 2ch](https://existential.audio/blackhole/)** — virtual audio loopback driver. Free, brew: `brew install --cask blackhole-2ch`.
2. **Create a Multi-Output Device** in Audio MIDI Setup that includes both your speakers/headphones *and* BlackHole. Set system output to the Multi-Output Device. (You'll hear audio normally, and BlackHole gets a copy.)
3. **Clone and run:**
   ```bash
   git clone https://github.com/aholten/magical-music-mirror.git
   cd magical-music-mirror
   make run                       # creates .venv, installs deps, runs with defaults
   ```
   Other targets:
   ```bash
   make devices                   # list audio devices (find BlackHole's exact name)
   make run RULESET=conway10      # try a different Conway gene variant
   make run DEVICE="Built-in Input"
   make clean                     # nuke .venv
   ```

## Theme concepts

### Genes

A RenderRuleset species is parameterized by an ordered tuple of small-arity decisions called **genes**. Naming convention: `<Species>RenderRuleset<g₀g₁…gₙ₋₁>` where each digit is the chosen option for that gene's position (left = gene 0). A species with `n` genes has `n` digits.

### Conway's genes (n=2)

- **Gene 0 — composition rule**
  - `0` = **Gated**: survival mask stencils the audio layer; non-survivors go dark.
  - `1` = **Underlay**: ruleset evolves its own buffer; audio paints over survivors, Life keeps running underneath.
- **Gene 1 — state boundary**
  - `0` = **Audio-seeded**: previous composed frame (incl. audio pixels) feeds the next generation. Loud bands birth cells.
  - `1` = **Isolated**: Conway evolves only its own buffer; audio never feeds in.

Four shipping variants: `ConwayRenderRuleset00`, `ConwayRenderRuleset01`, `ConwayRenderRuleset10`, `ConwayRenderRuleset11`.

## MVP architecture

**Stack:** Python 3 + `sounddevice` (PortAudio) + `numpy` + `pygame`.

**Render loop:**
1. Pull latest audio chunk (1024 samples @ 44.1 kHz) from the input device.
2. AudioRender → fresh pixel buffer.
3. RenderRuleset → advance using `prev_frame` or its own buffer (per gene 1), produce survival mask / evolved buffer.
4. Compositor combines per gene 0 → final frame.
5. Blit to pygame surface, present, store as `prev_frame`.

**Target:** 60 fps. Grid resolution intentionally chunky (160×90 → upscaled), since Conway looks better with visible cells.

**Theme interface:**

```python
class AudioRender:
    def render(self, audio_frame: np.ndarray, shape: tuple[int, int]) -> np.ndarray: ...

class RenderRuleset:
    genes: list[Gene]
    def step(self, prev_frame: np.ndarray, audio_layer: np.ndarray) -> np.ndarray: ...
```

## Repo layout

```
.
├── app.py
├── engine/
│   ├── compositor.py
│   ├── genes.py
│   └── audio_capture.py
├── themes/
│   ├── audio/
│   │   └── bar_meter.py
│   └── ruleset/
│       └── conway.py        # all 4 gene variants
└── requirements.txt
```

## Roadmap

MVP scope:
- [x] Repo skeleton + README
- [ ] Engine: theme interfaces, `Gene` declaration, compositor, audio capture loop, pygame frontend
- [ ] AudioRender: `BarMeter` (FFT, low→high left→right)
- [ ] RenderRuleset: Conway with all 4 gene variants
- [ ] Runtime theme/variant switching via keyboard hotkeys
- [ ] 60 fps at chosen resolution

Out of scope (MVP):
- Networked viewing / streaming
- Packaging as `.app`
- GPU shaders / WebGL
- Additional Render species

## Origin

Started life as [aholten/selfhost#198](https://github.com/aholten/selfhost/issues/198), then moved to its own repo since it's a native macOS desktop app and doesn't fit selfhost's GitOps infrastructure model.
