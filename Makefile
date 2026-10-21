# ==============================================================================
# Jetson Stereo AI Camera Carrier Board - Root Build & Verification Makefile
# ==============================================================================

PROJECT_NAME := Jetson-AI-Cam-CopperPilot
PCB_FILE     := $(PROJECT_NAME).kicad_pcb
SCH_FILE     := $(PROJECT_NAME).kicad_sch
PRO_FILE     := $(PROJECT_NAME).kicad_pro
MANUFACTURING_DIR := manufacturing
RELEASE_ZIP  := $(MANUFACTURING_DIR)/gerbers.zip

PYTHON       ?= python3
KICAD_CLI    ?= $(shell which kicad-cli 2>/dev/null || echo /usr/bin/kicad-cli)
UV           := $(shell which uv 2>/dev/null || echo ~/.local/bin/uv)

# Pytest runner resolution (system pytest, python -m pytest, uv pytest, or standalone)
PYTEST       := $(shell \
	if command -v pytest >/dev/null 2>&1; then \
		echo "pytest"; \
	elif $(PYTHON) -m pytest --version >/dev/null 2>&1; then \
		echo "$(PYTHON) -m pytest"; \
	elif [ -x "$(UV)" ]; then \
		echo "$(UV) run --with pytest pytest"; \
	else \
		echo "$(PYTHON) tests/run_tests.py"; \
	fi)

.PHONY: all help lint test test-pcb verify drc erc fab clean distclean

# Default target executes complete hardware verification and static analysis
all: test lint

help:
	@echo "======================================================================"
	@echo " Jetson Stereo AI Camera: Build, Test & Verification System"
	@echo "======================================================================"
	@echo "Primary Targets:"
	@echo "  make test      - Run full verification (21-point PyTest + review/verify.sh)"
	@echo "  make test-pcb  - Run automated 21-point PyTest hardware verification suite"
	@echo "  make verify    - Run 11-point acceptance test suite (review/verify.sh)"
	@echo "  make lint      - Static analysis and Electrical Rule Check (ERC)"
	@echo "  make drc       - Run KiCad CLI Design Rule Check on PCB layout"
	@echo "  make erc       - Run KiCad CLI Electrical Rule Check on schematic"
	@echo "  make fab       - Verify and package manufacturing deliverables (Gerbers, BOM, CPL)"
	@echo "  make clean     - Clean intermediate caches and temporary test reports"
	@echo "  make distclean - Deep clean removing all caches, backups, and virtual environments"

# ------------------------------------------------------------------------------
# Automated Hardware Testing
# ------------------------------------------------------------------------------
test: test-pcb verify
	@echo "======================================================================"
	@echo "SUCCESS: All automated hardware and acceptance tests passed cleanly!"
	@echo "======================================================================"

test-pcb:
	@echo ">>> Running Automated 21-Point Hardware Verification Suite..."
	@$(PYTEST) tests/test_pcb.py -v

verify:
	@echo ">>> Running Official 11-Point Acceptance Verification Suite (review/verify.sh)..."
	@bash review/verify.sh

# ------------------------------------------------------------------------------
# Linting & Static Analysis
# ------------------------------------------------------------------------------
lint: erc
	@echo ">>> Running repository hygiene and path check..."
	@$(PYTHON) -c "import glob, sys; bad = [p for p in glob.glob('**/*.kicad_*', recursive=True) if '/Users/' in open(p, errors='ignore').read() or '/home/' in open(p, errors='ignore').read()]; sys.exit(1) if bad else print('Repository hygiene: Clean project-local paths verified.')"
	@echo "All linting and rule checks passed."

# ------------------------------------------------------------------------------
# Hardware DRC / ERC
# ------------------------------------------------------------------------------
drc:
	@echo ">>> Running KiCad CLI Design Rule Check (DRC) with zone refilling..."
	@$(KICAD_CLI) pcb drc --refill-zones --format json -o review/tmp_drc.json $(PCB_FILE) > /dev/null
	@$(PYTHON) -c "import json, sys; \
		data = json.load(open('review/tmp_drc.json')); \
		errs = [v for v in data.get('violations', []) if v.get('severity') == 'error']; \
		unconn = data.get('unconnected_items', []); \
		print(f'DRC Results: {len(errs)} errors, {len(unconn)} unconnected items'); \
		sys.exit(1 if errs or unconn else 0)"
	@echo "DRC Clean: 0 errors, 100% routed."

erc:
	@echo ">>> Running KiCad CLI Electrical Rule Check (ERC)..."
	@$(KICAD_CLI) sch erc --format json -o review/tmp_erc.json $(SCH_FILE) > /dev/null
	@$(PYTHON) -c "import json, sys; \
		data = json.load(open('review/tmp_erc.json')); \
		errs = [v for s in data.get('sheets', []) for v in s.get('violations', []) if v.get('severity') == 'error']; \
		print(f'ERC Results: {len(errs)} errors'); \
		sys.exit(1 if errs else 0)"
	@echo "ERC Clean: 0 errors."

# ------------------------------------------------------------------------------
# Manufacturing Release Packaging
# ------------------------------------------------------------------------------
fab:
	@echo ">>> Verifying manufacturing outputs in $(MANUFACTURING_DIR)/..."
	@test -f $(MANUFACTURING_DIR)/BOM.csv || (echo "Error: BOM.csv missing"; exit 1)
	@test -f $(MANUFACTURING_DIR)/CPL.csv || (echo "Error: CPL.csv missing"; exit 1)
	@test -f $(RELEASE_ZIP) || (echo "Error: gerbers.zip missing"; exit 1)
	@test -f $(MANUFACTURING_DIR)/ORDER_SPEC.md || (echo "Error: ORDER_SPEC.md missing"; exit 1)
	@echo "Manufacturing bundle verified: Gerbers, BOM, CPL, and ORDER_SPEC are complete."

# ------------------------------------------------------------------------------
# Clean
# ------------------------------------------------------------------------------
clean:
	@rm -rf .pytest_cache tests/__pycache__ __pycache__ review/tools/__pycache__
	@find . -type f -name "*.py[cod]" -delete 2>/dev/null || true
	@find . -type f -name "*~" -delete 2>/dev/null || true
	@find . -type f -name "~*.lck" -delete 2>/dev/null || true
	@echo "Intermediate build and test caches cleaned."

distclean: clean
	@rm -rf review/tmp_drc.json review/tmp_erc.json .drc_test_tmp.json .erc_test_tmp.json
	@echo "Distclean complete: all caches, temporary reports, and lock files removed."
