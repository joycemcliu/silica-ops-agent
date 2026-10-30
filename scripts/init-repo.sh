#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$task_root"
if git rev-parse --show-toplevel >/dev/null 2>&1; then
  printf 'Git repository already initialized.\n'
else
  git init --initial-branch=main
fi
# Do not invent an author identity or commit anything automatically.
