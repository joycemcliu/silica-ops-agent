"""Operator-facing verification through the actual Hermes plugin/registry runtime."""

import json


def setup(parser):
    parser.add_argument("--probe", action="store_true", help="Submit a harmless gateway command")
    parser.add_argument(
        "--reload", action="store_true", help="Hot-load this profile in its gateway"
    )
    parser.add_argument(
        "--resume", help="Resume an already-approved request as this profile's user"
    )


def run(args):
    from hermes_constants import get_default_hermes_root, get_hermes_home

    if args.reload:
        from gateway.control_socket import reload_gateway_plugins

        result = reload_gateway_plugins(get_default_hermes_root(), profile_home=get_hermes_home())
        print(
            json.dumps(
                {
                    "reloaded": bool(result and result.get("reloaded")),
                    "profile": str(get_hermes_home()),
                    "error": (result or {}).get("error"),
                },
                indent=2,
            )
        )
        raise SystemExit(0 if result and result.get("reloaded") else 1)

    import model_tools  # noqa: F401 -- initialize real builtin/plugin registries
    from agent.terminal_env_registry import get_provider
    from hermes_cli.plugins import get_pre_tool_call_directive
    from tools.registry import registry

    entry = registry.get_entry("terminal")
    provider = get_provider("command_guard")
    guarded = provider is not None and getattr(entry.handler, "__self__", None) is not None
    result = {
        "profile": str(get_hermes_home()),
        "backend_registered": provider is not None,
        "terminal_handler": entry.handler.__module__,
        "guarded": guarded,
    }
    if guarded:
        for tool in ("execute_code", "write_file", "delegate_task"):
            result[tool + "_gate"] = get_pre_tool_call_directive(tool, {})[0]
        result["default_cwd"] = provider.default_cwd
        if args.probe:
            result["probe"] = json.loads(
                entry.handler(
                    {"command": "printf hermes-gateway-check", "workdir": provider.default_cwd}
                )
            )
        if args.resume:
            handler = registry.get_entry("guard_command").handler
            result["resume"] = json.loads(handler({"action": "resume", "id": args.resume}))
    print(json.dumps(result, indent=2))
    if not guarded:
        raise SystemExit(1)
