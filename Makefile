.PHONY: install run test test-verbose clean help

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

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	rm -rf .pytest_cache

help:
	@echo "EyeTracker Makefile"
	@echo ""
	@echo "Usage:"
	@echo "  make install        Install dependencies via Poetry"
	@echo "  make run            Run the eye tracker (see args below)"
	@echo "  make test           Run tests"
	@echo "  make test-verbose   Run tests with verbose output"
	@echo "  make clean          Remove __pycache__ and .pytest_cache"
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
