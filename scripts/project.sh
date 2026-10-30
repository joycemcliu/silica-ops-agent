#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$task_root/.tools/go/bin:$PATH"
export GOCACHE="$task_root/.tools/cache/go-build"
export GOMODCACHE="$task_root/.tools/cache/go-mod"
cd "$task_root/broker"
case "${1:-}" in
  build)
    mkdir -p "$task_root/bin"
    go build -trimpath ./...
    go build -trimpath -o "$task_root/bin/broker" ./cmd/broker
    ;;
  test) go test -count=1 -timeout=90s ./... ;;
  coverage) go test -count=1 -timeout=90s -coverprofile="$task_root/coverage.out" ./... ;;
  lint)
    go vet ./...
    unformatted="$(gofmt -l .)"
    if [[ -n "$unformatted" ]]; then
      printf 'Run make fmt to format:\n%s\n' "$unformatted" >&2
      exit 1
    fi
    ;;
  fmt) gofmt -w . ;;
  deps) go mod tidy ;;
  check-config)
    go run ./cmd/broker check-config \
      --environments "$task_root/environments/envs.yaml" \
      --access "$task_root/environments/access.yaml" \
      --redaction "$task_root/environments/redaction.yaml"
    ;;
  *) printf 'Usage: %s {build|test|coverage|lint|fmt|deps|check-config}\n' "$0" >&2; exit 2 ;;
esac
