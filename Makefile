# Ever Recover Build System

PYTHON = python3
PIP = python3 -m pip
VENV = .venv

.PHONY: all install dev test clean run-demo run-gui

all: install

install:
	@echo "Creating virtual environment..."
	$(PYTHON) -m venv $(VENV)
	@echo "Installing dependencies..."
	$(PIP) install -r requirements.txt
	@echo "✅ Installation complete!"

dev: install
	@echo "Installing development tools..."
	$(PIP) install black flake8 mypy pytest
	@echo "✅ Development setup complete!"

test:
	@echo "Running tests..."
	$(VENV)/bin/pytest tests/ -v --tb=short

clean:
	@echo "Cleaning up..."
	rm -rf $(VENV)
	rm -rf __pycache__
	rm -rf *.pyc
	rm -rf .pytest_cache
	rm -rf *.egg-info
	rm -rf dist build
	rm -rf recovered output reports
	@echo "✅ Clean complete!"

run-demo:
	@echo "Running demo..."
	$(VENV)/bin/python ever_recover.py --demo

run-gui:
	@echo "Running GUI..."
	$(VENV)/bin/python ever_recover.py

lint:
	@echo "Running linters..."
	$(VENV)/bin/black --check ever_recover/
	$(VENV)/bin/flake8 ever_recover/
	@echo "✅ Linting complete!"

format:
	@echo "Formatting code..."
	$(VENV)/bin/black ever_recover/
	@echo "✅ Formatting complete!"

help:
	@echo "Ever Recover Build System"
	@echo ""
	@echo "Targets:"
	@echo "  make install   - Install dependencies"
	@echo "  make dev       - Development setup"
	@echo "  make test      - Run tests"
	@echo "  make clean     - Clean up"
	@echo "  make run-demo  - Run demo"
	@echo "  make run-gui   - Run GUI"
	@echo "  make lint      - Run linters"
	@echo "  make format    - Format code"
	@echo "  make help      - Show this help"