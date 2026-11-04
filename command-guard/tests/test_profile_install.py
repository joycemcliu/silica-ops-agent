import importlib.util
from pathlib import Path

import yaml


def test_profile_apply_preserves_model_and_other_profile_and_backs_up(tmp_path):
    path = Path(__file__).parents[1] / "deploy" / "linux" / "apply_hermes.py"
    spec = importlib.util.spec_from_file_location("apply_guard_profile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = tmp_path / "diagnose"
    home.mkdir()
    original = "model:\n  default: existing-model\n"
    (home / "config.yaml").write_text(original)
    (home / "SOUL.md").write_text("Existing instructions")
    other = tmp_path / "default.yaml"
    other.write_text("terminal:\n  backend: local\n")
    backup = module.apply(home, "/host/srv/operations")
    config = yaml.safe_load((home / "config.yaml").read_text())
    assert config["model"]["default"] == "existing-model"
    assert config["terminal"]["backend"] == "command_guard"
    assert config["plugins"]["entries"]["command-guard"]["allow_tool_override"] is True
    assert "file" not in config["toolsets"] and "code_execution" not in config["toolsets"]
    assert (backup / "config.yaml").read_text() == original
    assert other.read_text() == "terminal:\n  backend: local\n"
    assert (home / "SOUL.md").read_text().startswith("Existing instructions")
    module.apply(home, "/host/srv/operations")
    assert (home / "SOUL.md").read_text().count("<!-- command-guard -->") == 1


def test_relocation_only_changes_socket_and_plugin_link(tmp_path):
    path = Path(__file__).parents[1] / "deploy/linux/apply_hermes.py"
    spec = importlib.util.spec_from_file_location("relocate_guard_profile", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = tmp_path / "diagnose"
    home.mkdir()
    config = {
        "terminal": {"backend": "command_guard", "cwd": "/host/work"},
        "toolsets": ["terminal", "mcp-custom"],
        "model": {"default": "existing-model"},
        "plugins": {
            "entries": {
                "command-guard": {
                    "settings": {"socket": "/old/socket", "allowed_mcp_servers": ["custom"]}
                }
            }
        },
    }
    (home / "config.yaml").write_text(yaml.safe_dump(config))
    (home / "SOUL.md").write_text("User instructions")
    backup = module.relocate(home, "/new/socket")
    after = yaml.safe_load((home / "config.yaml").read_text())
    config["plugins"]["entries"]["command-guard"]["settings"]["socket"] = "/new/socket"
    assert after == config
    assert (home / "SOUL.md").read_text() == "User instructions"
    assert (backup / "config.yaml").exists()
    assert (home / "plugins/command-guard").resolve() == module.PLUGIN_ROOT
