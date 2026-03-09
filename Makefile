.PHONY: install run test test-verbose build clean help

CAMERA  ?=0
VERBOSE ?=

RUN_ARGS := --camera $(CAMERA)
ifneq ($(VERBOSE),)
RUN_ARGS += --verbose
endif

install:
	poetry lock
	poetry install

run:
	poetry run eyetracker $(RUN_ARGS)

test:
	poetry run pytest

test-verbose:
	poetry run pytest -v

build:
	poetry run pyinstaller eyetracker.spec --distpath dist --workpath build --noconfirm
	@if [ "$$(uname)" = "Darwin" ]; then \
		codesign --deep --force --sign - --entitlements entitlements.plist dist/EyeTracker.app; \
		echo "Built and signed: dist/EyeTracker.app"; \
	else \
		echo "Built: dist/EyeTracker.exe"; \
	fi

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	rm -rf .pytest_cache build dist

help:
	@echo "EyeTracker Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make install        Install dependencies via Poetry"
	@echo "  make run            Run the eye tracker (see args below)"
	@echo "  make test           Run tests"
	@echo "  make test-verbose   Run tests with verbose output"
	@echo "  make build          Build standalone app (.exe on Windows, .app on macOS)"
	@echo "  make clean          Remove __pycache__, .pytest_cache, build, dist"
	@echo "  make help           Show this help"
	@echo ""
	@echo "Run arguments (pass via make run KEY=VALUE):"
	@echo "  CAMERA=N            Camera device index (default: 0)"
	@echo "  VERBOSE=1           Enable verbose logging"
	@echo ""
	@echo "Examples:"
	@echo "  make run"
	@echo "  make run CAMERA=1"
	@echo "  make run VERBOSE=1"
