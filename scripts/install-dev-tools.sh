#!/usr/bin/env bash
set -euo pipefail

repository_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
tools_directory="$repository_root/.tools"
mkdir -p "$tools_directory/bin"
temporary_directory=$(mktemp -d)
trap 'rm -rf -- "$temporary_directory"' EXIT

case "$(uname -s)/$(uname -m)" in
    Linux/x86_64) shellcheck_arch=x86_64; gitleaks_arch=x64 ;;
    Linux/aarch64) shellcheck_arch=aarch64; gitleaks_arch=arm64 ;;
    *) printf '%s\n' 'Install ShellCheck, Bats, and Gitleaks manually on this platform.' >&2; exit 1 ;;
esac

curl --fail --location --retry 3 \
    "https://github.com/koalaman/shellcheck/releases/download/v0.10.0/shellcheck-v0.10.0.linux.$shellcheck_arch.tar.xz" \
    --output "$temporary_directory/shellcheck.tar.xz"
tar -xJf "$temporary_directory/shellcheck.tar.xz" -C "$temporary_directory"
install -m 755 "$temporary_directory/shellcheck-v0.10.0/shellcheck" "$tools_directory/bin/shellcheck"

curl --fail --location --retry 3 \
    https://github.com/bats-core/bats-core/archive/refs/tags/v1.11.1.tar.gz \
    --output "$temporary_directory/bats.tar.gz"
tar -xzf "$temporary_directory/bats.tar.gz" -C "$temporary_directory"
bash "$temporary_directory/bats-core-1.11.1/install.sh" "$tools_directory"

gitleaks_archive="gitleaks_8.24.2_linux_$gitleaks_arch.tar.gz"
curl --fail --location --retry 3 \
    "https://github.com/gitleaks/gitleaks/releases/download/v8.24.2/$gitleaks_archive" \
    --output "$temporary_directory/$gitleaks_archive"
curl --fail --location --retry 3 \
    https://github.com/gitleaks/gitleaks/releases/download/v8.24.2/gitleaks_8.24.2_checksums.txt \
    --output "$temporary_directory/checksums.txt"
(
    cd -- "$temporary_directory"
    grep "  $gitleaks_archive$" checksums.txt | sha256sum --check --status
)
tar -xzf "$temporary_directory/$gitleaks_archive" -C "$temporary_directory" gitleaks
install -m 755 "$temporary_directory/gitleaks" "$tools_directory/bin/gitleaks"
printf '%s\n' 'Development tools installed in .tools/bin (already on the Makefile PATH).'
