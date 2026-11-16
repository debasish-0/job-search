.PHONY: install test run dashboard api scheduler clean

install:
	python -m pip install -e ".[all,dev]"

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

run:
	jobsearch run

dashboard:
	jobsearch dashboard

api:
	jobsearch serve

scheduler:
	jobsearch scheduler

clean:
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
