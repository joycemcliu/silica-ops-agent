#!/usr/bin/env bash
set -euo pipefail

repository_root=$(git rev-parse --show-toplevel)
cd -- "$repository_root"
temporary_directory=$(mktemp -d)
trap 'rm -rf -- "$temporary_directory"' EXIT
mkdir "$temporary_directory/tree"
git ls-files --cached --others --exclude-standard -z > "$temporary_directory/paths"
while IFS= read -r -d '' repository_path; do
    if [[ -f "$repository_path" && ! -L "$repository_path" ]]; then
        cp --parents -- "$repository_path" "$temporary_directory/tree/"
    fi
done < "$temporary_directory/paths"
gitleaks dir --redact --no-banner "$temporary_directory/tree"
