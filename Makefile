.PHONY: setup install run test test-verbose build clean help

CAMERA  ?=0
VERBOSE ?=

RUN_ARGS := --camera $(CAMERA)
ifneq ($(VERBOSE),)
RUN_ARGS += --verbose
endif

setup:
	@echo "=== Установка Python 3.12 ==="
	@if [ "$$(uname)" = "Darwin" ]; then \
		if ! command -v brew >/dev/null 2>&1; then \
			echo "Homebrew не найден. Установите: https://brew.sh"; \
			exit 1; \
		fi; \
		if ! brew list python@3.12 >/dev/null 2>&1; then \
			brew install python@3.12; \
		else \
			echo "Python 3.12 уже установлен (Homebrew)"; \
		fi; \
		PYTHON_PATH=$$(brew --prefix python@3.12)/bin/python3.12; \
	else \
		if ! command -v winget >/dev/null 2>&1; then \
			echo "winget не найден. Установите Python 3.12 вручную: https://python.org"; \
			exit 1; \
		fi; \
		if ! python3.12 --version >/dev/null 2>&1 && ! py -3.12 --version >/dev/null 2>&1; then \
			winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements; \
		else \
			echo "Python 3.12 уже установлен"; \
		fi; \
		if py -3.12 --version >/dev/null 2>&1; then \
			PYTHON_PATH=$$(py -3.12 -c "import sys; print(sys.executable)"); \
		else \
			PYTHON_PATH=python3.12; \
		fi; \
	fi; \
	echo "=== Настройка Poetry окружения ===" ; \
	if ! command -v poetry >/dev/null 2>&1; then \
		echo "Poetry не найден. Установите: https://python-poetry.org/docs/#installation"; \
		exit 1; \
	fi; \
	poetry env use $$PYTHON_PATH; \
	echo "=== Установка зависимостей ==="; \
	poetry lock; \
	poetry install; \
	echo "=== Готово ==="

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
	@echo "  make setup          Install Python 3.12, configure Poetry env, install deps"
	@echo "  make install        Install dependencies via Poetry (Python already set up)"
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
