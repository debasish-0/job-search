#!/usr/bin/env sh
set -eu

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[all,dev]"

if [ ! -f .env ]; then
  cp .env.example .env
fi

jobsearch init-db
printf '%s\n' "Setup complete."
printf '%s\n' "Run the offline demo: jobsearch run --no-llm"
printf '%s\n' "Run the dashboard: jobsearch dashboard"
