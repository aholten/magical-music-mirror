VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip

DEVICE        ?= BlackHole 2ch
RULESET       ?= conway11
LAYOUT        ?= dual-mirror
RESOLUTION    ?= 1
PALETTE       ?= sunset
PALETTE_CURVE ?= 2.0
FADE_TICKS    ?= 120
WARP_ZOOM            ?= 1.04
WARP_FADE_TICKS      ?= 63
WARP_DITHER          ?= 1.0
WARP_FOCUS_RANGE       ?= 0.6
WARP_FOCUS_SMOOTHING   ?= 0.30
WARP_FOCUS_TREBLE_BIAS ?= 3.0
WARP_FADE_VOCAL        ?= 0.75
DEBUG                  ?=

.PHONY: help run devices install clean

help:
	@echo "Targets:"
	@echo "  make install     create .venv and install deps"
	@echo "  make run         run the visualizer (DEVICE='$(DEVICE)' RULESET=$(RULESET) LAYOUT=$(LAYOUT) FADE_TICKS=$(FADE_TICKS))"
	@echo "  make devices     list audio input devices"
	@echo "  make clean       remove .venv"
	@echo ""
	@echo "Examples:"
	@echo "  make run RULESET=conway10"
	@echo "  make run LAYOUT=butterfly"
	@echo "  make run RESOLUTION=2          # double grid detail"
	@echo "  make run RESOLUTION=4          # smooth (CPU heavier)"
	@echo "  make run PALETTE=ocean         # also: fire, neon, forest, monochrome"
	@echo "  make run PALETTE_CURVE=1.0     # linear palette walk (even color time)"
	@echo "  make run PALETTE_CURVE=3.0     # aggressive front-load (dark tones dominate)"
	@echo "  make run FADE_TICKS=60   # quick fade — 1s at 60fps"
	@echo "  make run FADE_TICKS=600  # slow trails — 10s at 60fps"
	@echo "  make run WARP_ZOOM=1.02         # subtle warp drift"
	@echo "  make run WARP_ZOOM=1.08         # aggressive hyperspace"
	@echo "  make run WARP_FADE_TICKS=30     # short snappy warp trails (0.5s)"
	@echo "  make run WARP_FADE_TICKS=300    # long lingering warp streams (5s)"
	@echo "  make run WARP_DITHER=0.0        # disable warp dithering"
	@echo "  make run WARP_DITHER=2.0        # heavier film-grain texture"
	@echo "  make run WARP_FOCUS_RANGE=0.0       # static warp focal (no audio reactivity)"
	@echo "  make run WARP_FOCUS_RANGE=0.5       # focal can reach the top/bottom edges"
	@echo "  make run WARP_FOCUS_SMOOTHING=0.0   # raw, instant (very twitchy)"
	@echo "  make run WARP_FOCUS_SMOOTHING=0.7   # slow leisurely drift"
	@echo "  make run WARP_FOCUS_TREBLE_BIAS=0.0 # raw centroid (heavily bass-skewed)"
	@echo "  make run WARP_FOCUS_TREBLE_BIAS=6.0 # heavy treble emphasis"
	@echo "  make run WARP_FADE_VOCAL=0.0       # off — constant base trails"
	@echo "  make run WARP_FADE_VOCAL=0.75      # default — vocals shorten trails"
	@echo "  make run WARP_FADE_VOCAL=1.0       # vocals fully kill trails (silence = base)"
	@echo "  make run WARP_FADE_VOCAL=-0.5      # silence partially shortens trails"
	@echo "  make run WARP_FADE_VOCAL=-1.0      # silence fully kills trails (vocals = base)"
	@echo "  make run DEBUG=1                   # print live audio-feature values to stderr"
	@echo "  make run WARP_ZOOM=1.0          # disable warp motion (no trails)"
	@echo "  make run DEVICE='Built-in Input'"

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $(VENV)/bin/activate

install: $(VENV)/bin/activate

run: install
	$(PY) app.py --device "$(DEVICE)" --ruleset $(RULESET) --layout $(LAYOUT) \
		--resolution $(RESOLUTION) --palette $(PALETTE) \
		--palette-curve $(PALETTE_CURVE) --fade-ticks $(FADE_TICKS) \
		--warp-zoom $(WARP_ZOOM) --warp-fade-ticks $(WARP_FADE_TICKS) \
		--warp-dither $(WARP_DITHER) --warp-focus-range $(WARP_FOCUS_RANGE) \
		--warp-focus-smoothing $(WARP_FOCUS_SMOOTHING) \
		--warp-focus-treble-bias $(WARP_FOCUS_TREBLE_BIAS) \
		--warp-fade-vocal $(WARP_FADE_VOCAL) \
		$(if $(DEBUG),--debug)

devices: install
	$(PY) -c "import sounddevice as sd; print(sd.query_devices())"

clean:
	rm -rf $(VENV)
