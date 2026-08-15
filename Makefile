.PHONY: install test unit regression lint format types check paper clean

install:
	pip install -e ".[dev,cv,viz]"

test:
	pytest -q

unit:
	pytest tests/unit -q

regression:          ## the ADR-backed lessons; run these before any refactor
	pytest tests/regression -v -m regression

lint:
	ruff check src tests experiments

format:
	ruff format src tests experiments

types:
	mypy src

check: lint types test   ## what CI runs

paper:
	latexmk -pdf -cd paper/main.tex

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
