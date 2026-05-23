VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip

DEVICE     ?= BlackHole 2ch
RULESET    ?= conway11
LAYOUT     ?= dual-mirror
FADE_TICKS ?= 120
WARP_ZOOM  ?= 1.04
WARP_DIM   ?= 0.93

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
	@echo "  make run FADE_TICKS=60   # quick fade — 1s at 60fps"
	@echo "  make run FADE_TICKS=600  # slow trails — 10s at 60fps"
	@echo "  make run WARP_ZOOM=1.02  # subtle warp drift"
	@echo "  make run WARP_ZOOM=1.08  # aggressive hyperspace"
	@echo "  make run WARP_ZOOM=1.0 WARP_DIM=0.0   # disable warp entirely"
	@echo "  make run DEVICE='Built-in Input'"

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $(VENV)/bin/activate

install: $(VENV)/bin/activate

run: install
	$(PY) app.py --device "$(DEVICE)" --ruleset $(RULESET) --layout $(LAYOUT) \
		--fade-ticks $(FADE_TICKS) --warp-zoom $(WARP_ZOOM) --warp-dim $(WARP_DIM)

devices: install
	$(PY) -c "import sounddevice as sd; print(sd.query_devices())"

clean:
	rm -rf $(VENV)
