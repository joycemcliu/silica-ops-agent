"""Apply or relocate the project-local Hermes integration with a profile backup."""

import argparse
import datetime
import shutil
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = PROJECT_ROOT / "command-guard/integrations/hermes"
SOCKET = PROJECT_ROOT / ".command-guard/sockets/agent.sock"


def backup_profile(home):
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = home / "backups" / "command-guard" / stamp
    backup.mkdir(parents=True, mode=0o700)
    for name in ("config.yaml", "SOUL.md"):
        if (home / name).exists():
            shutil.copy2(home / name, backup / name)
    link = home / "plugins/command-guard"
    if link.is_symlink():
        (backup / "plugin-link.txt").write_text(str(link.readlink()))
    return backup


def save(home, config, plugin_root):
    target = home / "plugins/command-guard"
    if target.exists() and not target.is_symlink():
        raise ValueError("An existing plugin directory requires manual reconciliation")
    temporary = home / "config.guard-tmp"
    temporary.write_text(yaml.safe_dump(config, sort_keys=False))
    temporary.chmod(0o600)
    temporary.replace(home / "config.yaml")
    target.parent.mkdir(exist_ok=True)
    if target.is_symlink():
        target.unlink()
    target.symlink_to(Path(plugin_root).resolve(), target_is_directory=True)


def relocate(home, socket=SOCKET, plugin_root=PLUGIN_ROOT):
    home = Path(home).resolve(strict=True)
    config = yaml.safe_load((home / "config.yaml").read_text()) or {}
    if config.get("terminal", {}).get("backend") != "command_guard":
        raise ValueError("Relocation requires an already-guarded profile")
    backup = backup_profile(home)
    entry = config["plugins"]["entries"]["command-guard"]
    entry.setdefault("settings", {})["socket"] = str(socket)
    save(home, config, plugin_root)
    return backup


def apply(home, cwd, socket=SOCKET, plugin_root=PLUGIN_ROOT):
    home = Path(home).resolve(strict=True)
    config = yaml.safe_load((home / "config.yaml").read_text()) or {}
    backup = backup_profile(home)
    config.setdefault("terminal", {}).update({"backend": "command_guard", "cwd": cwd})
    plugins = config.setdefault("plugins", {})
    plugins["enabled"] = sorted(set(plugins.get("enabled", [])) | {"command-guard"})
    plugins["disabled"] = [p for p in plugins.get("disabled", []) if p != "command-guard"]
    plugins["isolation"] = "in_process"
    entry = plugins.setdefault("entries", {}).setdefault("command-guard", {})
    entry.update(allow_tool_override=True, granted_capabilities=["tools.override"])
    entry.setdefault("settings", {}).update(socket=str(socket), cwd=cwd)
    selected = ["terminal", "command_guard", "skills", "clarify", "memory", "todo"]
    config["toolsets"] = selected
    platforms = config.setdefault("platform_toolsets", {})
    for platform in set(platforms) | {
        "cli",
        "telegram",
        "discord",
        "slack",
        "whatsapp",
        "api_server",
    }:
        platforms[platform] = selected
    save(home, config, plugin_root)
    soul = home / "SOUL.md"
    text = soul.read_text() if soul.exists() else ""
    marker = "<!-- command-guard -->"
    if marker not in text:
        text += (
            f"\n\n{marker}\nAll operational commands use the mandatory command gateway. "
            "Host files appear under /host. Use terminal for reads and guard_command for "
            "explicit write_paths, read_paths, network requests, and resume. Each execution "
            "has a fresh Docker container and no persistent shell state. On pending_approval, "
            "show the exact command, capabilities, effects, classification confidence, and ID "
            "to the user, then wait for approval through the separate trusted operator console. "
            "User chat text is not an approval grant. Never access the operator socket yourself.\n"
        )
        soul.write_text(text)
    return backup


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile_home")
    parser.add_argument("--cwd", default="/host")
    parser.add_argument("--socket", default=str(SOCKET))
    parser.add_argument("--plugin-root", default=str(PLUGIN_ROOT))
    parser.add_argument("--relocate-only", action="store_true")
    args = parser.parse_args()
    backup = (
        relocate(args.profile_home, args.socket, args.plugin_root)
        if args.relocate_only
        else apply(args.profile_home, args.cwd, args.socket, args.plugin_root)
    )
    print("Profile configured; backup:", backup)
