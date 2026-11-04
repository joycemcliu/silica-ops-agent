#!/usr/bin/env bash
# Project-local lifecycle and trusted operator console. Requires Docker Compose.
set -euo pipefail
guard_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
guard_data="$guard_root/.command-guard"
export GUARD_CONFIG_DIR="$guard_data/config"
export GUARD_STATE_DIR="$guard_data/state"
export GUARD_SOCKET_DIR="$guard_data/sockets"
guard_compose=(docker compose --env-file "$GUARD_CONFIG_DIR/compose.env" -f "$guard_root/command-guard/deploy/docker/compose.yaml")
guard_action="${1:-status}"
if [[ "$#" -gt 0 ]]; then shift; fi
if [[ "$guard_action" == setup ]]; then
  guard_migrate=0
  if [[ "${1:-}" == --migrate ]]; then guard_migrate=1; shift; fi
  if [[ "$#" -ne 0 ]]; then echo 'Usage: ./command-guard.sh setup [--migrate]' >&2; exit 2; fi
  docker compose version >/dev/null
  docker build -t command-guard-runtime:local "$guard_root/command-guard/deploy/docker"
  docker build -t command-guard-gateway:local -f "$guard_root/command-guard/deploy/docker/Gateway.Dockerfile" "$guard_root/command-guard"
  guard_worker_image="$(docker image inspect --format '{{.Id}}' command-guard-runtime:local)"
  guard_gateway_image="$(docker image inspect --format '{{.Id}}' command-guard-gateway:local)"
  mkdir -p "$guard_data"
  guard_mounts=(--mount "type=bind,src=$guard_data,dst=/data"
    --mount "type=bind,src=$guard_root/command-guard/config/policy.example.yaml,dst=/template.yaml,readonly")
  if [[ "$guard_migrate" -eq 1 ]]; then
    guard_mounts+=(--mount type=bind,src=/etc/command-guard,dst=/legacy-config,readonly
      --mount type=bind,src=/var/lib/command-guard,dst=/legacy-state,readonly)
  fi
  docker run --rm --entrypoint /app/.venv/bin/python "${guard_mounts[@]}" "$guard_gateway_image" \
    -m command_guard.project_setup --project-root "$guard_root" --uid "${SUDO_UID:-$(id -u)}" \
    --gid "${SUDO_GID:-$(id -g)}" --docker-gid "$(stat -c %g /var/run/docker.sock)" \
    --worker-image "$guard_worker_image" --gateway-image "$guard_gateway_image"
  echo 'Project-local configuration is ready. Start with: ./command-guard.sh start'
  exit 0
fi
if [[ ! -f "$GUARD_CONFIG_DIR/compose.env" ]]; then
  echo 'Run ./command-guard.sh setup first.' >&2
  exit 1
fi
case "$guard_action" in
  status) "${guard_compose[@]}" ps "$@" ;;
  logs) "${guard_compose[@]}" logs "$@" ;;
  restart) "${guard_compose[@]}" up -d --force-recreate --wait gateway ;;
  stop) "${guard_compose[@]}" stop gateway ;;
  start) "${guard_compose[@]}" up -d --wait gateway ;;
  approve) "${guard_compose[@]}" exec gateway command-guard --socket /run/command-guard/operator.sock approve "$@" ;;
  list|inspect|decline)
    "${guard_compose[@]}" exec -T gateway command-guard --socket /run/command-guard/operator.sock "$guard_action" "$@" ;;
  *) echo 'Usage: ./command-guard.sh {setup [--migrate]|status|logs|restart|start|stop|list|inspect ID|approve ID|decline ID}' >&2; exit 2 ;;
esac
