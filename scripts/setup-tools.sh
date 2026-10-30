#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tools_dir="$task_root/.tools"
mkdir -p "$tools_dir"
if [[ -x "$tools_dir/go/bin/go" ]]; then
  "$tools_dir/go/bin/go" version
else
# A local development toolchain, never part of the broker deployment image.
version=1.27.3
case "$(uname -sm)" in
  'Linux x86_64') arch=amd64; checksum=65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40 ;;
  'Linux aarch64') arch=arm64; checksum=a06e99309dbcbdca1a8ccd2282c3ee146e55930886e26b4f1193269587165f49 ;;
  *) printf 'Install Go %s for this platform manually.\n' "$version" >&2; exit 1 ;;
esac
archive="$tools_dir/go$version.linux-$arch.tar.gz"
curl --fail --silent --show-error --location --retry 3 \
  "https://go.dev/dl/go$version.linux-$arch.tar.gz" -o "$archive"
printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --status
tar -xzf "$archive" -C "$tools_dir"
"$tools_dir/go/bin/go" version
fi

# Debian/Ubuntu development hosts can unpack Make locally without root. APT
# verifies the package against the configured distribution's signed metadata.
if ! command -v make >/dev/null && [[ ! -x "$tools_dir/make/usr/bin/make" ]]; then
  if command -v apt-get >/dev/null && command -v dpkg-deb >/dev/null; then
    mkdir -p "$tools_dir/make-package" "$tools_dir/make"
    (
      cd "$tools_dir/make-package"
      apt-get download make
      packages=(make_*.deb)
      if [[ ${#packages[@]} != 1 || ! -f "${packages[0]}" ]]; then
        printf 'Expected one Make package; use scripts/project.sh directly.\n' >&2
        exit 1
      fi
      dpkg-deb --extract "${packages[0]}" "$tools_dir/make"
    )
  else
    printf 'Make unavailable; use bash scripts/project.sh <target>.\n'
  fi
fi
