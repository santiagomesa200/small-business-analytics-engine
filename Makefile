# One command sets up and checks everything: make check
PY ?= python3
VENV = .venv

check: $(VENV)/.ok
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .
	$(VENV)/bin/mypy
	$(VENV)/bin/bandit -q -c bandit.yaml -r .
	$(VENV)/bin/pip-audit -r requirements.txt
	@if command -v gitleaks >/dev/null; then gitleaks detect --source . --no-banner; else echo "gitleaks is not installed here; CI scans the full history"; fi
	$(VENV)/bin/python -m engine.gate

$(VENV)/.ok: requirements.txt requirements-dev.txt
	$(PY) -m venv $(VENV)
	$(VENV)/bin/pip install -r requirements-dev.txt
	touch $(VENV)/.ok

.PHONY: check
