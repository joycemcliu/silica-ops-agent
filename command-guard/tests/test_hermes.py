import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def plugin(monkeypatch, tmp_path):
    module = types.ModuleType("agent.terminal_env_provider")
    module.TerminalEnvironmentProvider = type("TerminalEnvironmentProvider", (), {})
    constants = types.ModuleType("hermes_constants")
    constants.get_hermes_home = lambda: tmp_path / "diagnose"
    monkeypatch.setitem(sys.modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.terminal_env_provider", module)
    monkeypatch.setitem(sys.modules, "hermes_constants", constants)
    path = Path(__file__).parents[1] / "integrations" / "hermes" / "__init__.py"
    spec = importlib.util.spec_from_file_location("guard_plugin", path)
    loaded = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "guard_plugin", loaded)
    spec.loader.exec_module(loaded)
    return loaded


def test_terminal_override_and_profile_owned_hooks(plugin):
    ctx = Mock()
    plugin.register(ctx)
    registrations = ctx.register_tool.call_args_list
    assert registrations[0].kwargs["name"] == "terminal"
    assert registrations[0].kwargs["override"] is True
    assert registrations[1].kwargs["name"] == "guard_command"
    service = plugin.Service(ctx)
    for tool in (
        "execute_code",
        "write_file",
        "patch",
        "delegate_task",
        "process",
        "plugins.manage",
    ):
        assert service.before_tool(tool, {})["action"] == "block"
    assert service.before_tool("terminal", {}) is None
    plugin.get_hermes_home = lambda: Path("/another-profile")
    with pytest.raises(ValueError, match="another profile"):
        service.require_scope()


def test_profile_cwd_and_capability_mapping(plugin, monkeypatch):
    ctx = Mock()
    ctx.get_config.side_effect = lambda key, default=None: default
    service = plugin.Service(ctx)
    call = Mock(return_value={"status": "pending_approval", "id": "test"})
    monkeypatch.setattr(plugin, "exchange", call)
    service.submit(
        {
            "command": "echo test",
            "cwd": "/host/home/project",
            "write_paths": ["/host/home/project"],
            "network": True,
        }
    )
    request = call.call_args.args[1]["request"]
    assert request["cwd"] == "/home/project"
    assert request["write_paths"] == ["/home/project"]
    assert request["network"] is True
    with pytest.raises(ValueError):
        service.submit({"command": "true", "approved": True})


def test_mcp_exceptions_are_explicit_and_server_scoped(plugin):
    ctx = Mock()
    settings = {}
    ctx.get_config.side_effect = lambda key, default=None: settings.get(key, default)
    service = plugin.Service(ctx)
    dev = "mcp__sandbox_dev_grafana__list_datasources"
    assert service.before_tool(dev, {})["action"] == "block"
    settings["allowed_mcp_servers"] = ["sandbox_dev_grafana", "sandbox_prod_grafana"]
    assert service.before_tool(dev, {}) is None
    assert service.before_tool("mcp__sandbox_prod_grafana__list_datasources", {}) is None
    for name in (
        "mcp__sandbox_dev_grafana_other__list_datasources",
        "mcp__untrusted__list_datasources",
        "mcp__sandbox_dev_grafana__",
        "tool_search",
        "tool_describe",
        "tool_call",
        "execute_code",
    ):
        assert service.before_tool(name, {})["action"] == "block"
    for invalid in (None, "sandbox_dev_grafana", [""], ["*"], ["sandbox-dev-grafana"]):
        settings["allowed_mcp_servers"] = invalid
        assert service.before_tool(dev, {})["action"] == "block"


def test_resume_has_no_replacement_command(plugin, monkeypatch):
    ctx = Mock()
    ctx.get_config.side_effect = lambda key, default=None: default
    service = plugin.Service(ctx)
    call = Mock(return_value={"status": "finished", "exit_code": 0})
    monkeypatch.setattr(plugin, "exchange", call)
    assert json.loads(service.command({"action": "resume", "id": "abc"}))["status"] == "finished"
    assert call.call_args.args[1] == {"action": "resume", "id": "abc"}
    assert (
        json.loads(service.command({"action": "resume", "id": "abc", "command": "evil"}))["status"]
        == "error"
    )


def test_unavailable_service_never_runs_local_command(plugin, tmp_path):
    result = plugin.exchange(str(tmp_path / "absent.sock"), {"action": "submit"})
    assert result["status"] == "error"
