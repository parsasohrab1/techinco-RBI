.PHONY: install seed run test clean

install:
	pip install -r requirements.txt

seed:
	python seed.py

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

clean:
	rm -f rbi.db && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
