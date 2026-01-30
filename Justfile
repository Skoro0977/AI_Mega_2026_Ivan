#!/usr/bin/env just --justfile
export PATH := join(justfile_directory(), ".env", "bin") + ":" + env_var('PATH')

run-cli:
  export $(grep -v '^#' .env | xargs) && \
  uv run python -m src.interview_coach.cli

sync:
  uv sync

upgrade:
  uv lock --upgrade
