VENV    := .venv
PY      := $(VENV)/bin/python
PIP     := $(VENV)/bin/pip

DEVICE  ?= BlackHole 2ch
RULESET ?= conway11

.PHONY: help run devices install clean

help:
	@echo "Targets:"
	@echo "  make install     create .venv and install deps"
	@echo "  make run         run the visualizer (DEVICE='$(DEVICE)' RULESET=$(RULESET))"
	@echo "  make devices     list audio input devices"
	@echo "  make clean       remove .venv"
	@echo ""
	@echo "Examples:"
	@echo "  make run RULESET=conway10"
	@echo "  make run DEVICE='Built-in Input'"

$(VENV)/bin/activate: requirements.txt
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $(VENV)/bin/activate

install: $(VENV)/bin/activate

run: install
	$(PY) app.py --device "$(DEVICE)" --ruleset $(RULESET)

devices: install
	$(PY) -c "import sounddevice as sd; print(sd.query_devices())"

clean:
	rm -rf $(VENV)
