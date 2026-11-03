import posixpath
import re
import shlex

from access_common import AccessError


def readable_path(path):
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", path) or posixpath.normpath(path) != path:
        return False
    return path in {
        "/etc/os-release", "/proc/meminfo", "/proc/loadavg", "/proc/uptime",
        "/proc/version", "/proc/stat", "/proc/cpuinfo", "/proc/diskstats",
    } or path == "/var/log" or path.startswith("/var/log/")


def command_arguments(command):
    if not command or len(command) > 4096 or re.search(r"[;|&><$`()\n\r\x00-\x1f\x7f]", command):
        raise AccessError("Command rejected by read-only policy.")
    try:
        arguments = shlex.split(command)
    except ValueError:
        raise AccessError("Command rejected by read-only policy.") from None
    if not arguments:
        raise AccessError("Command rejected by read-only policy.")
    binary, *options = arguments
    valid = False
    if binary == "journalctl":
        valid = journal_options(options)
        arguments.insert(1, "--no-pager")
    elif binary == "systemctl":
        valid = bool(options) and options[0] == "status" and all(
            re.fullmatch(r"[A-Za-z0-9_@.:-]+", unit) and not unit.startswith("-")
            for unit in options[1:]
        )
        arguments[1:1] = ["--no-pager", "--plain"]
    elif binary == "ps":
        valid = all(option in {"aux", "-ef", "-e", "-f", "--no-headers"} for option in options)
    elif binary == "df":
        valid = all(option in {"-h", "-i", "-T", "--total"} for option in options)
    elif binary == "free":
        valid = all(option in {"-h", "-m", "-g", "--wide", "--total"} for option in options)
    elif binary == "ss":
        valid = all(re.fullmatch(r"-[tulnpsa46H]+", option) for option in options)
    elif binary == "uptime":
        valid = all(option in {"-p", "-s"} for option in options)
    elif binary == "dmesg":
        valid = all(option in {"--ctime", "--human", "--decode", "--kernel", "--userspace", "--color=never"} for option in options)
    elif binary in {"ls", "cat"}:
        paths = [option for option in options if not option.startswith("-")]
        flags = [option for option in options if option.startswith("-")]
        valid = bool(paths) and all(readable_path(path) for path in paths)
        if binary == "ls":
            valid = valid and all(re.fullmatch(r"-[lha]+", flag) for flag in flags)
        else:
            valid = valid and all(flag in {"-n", "-b"} for flag in flags)
    if not valid:
        raise AccessError("Command rejected by read-only policy.")
    return arguments


def journal_options(options):
    standalone = {"--no-pager", "--utc", "--reverse", "--kernel"}
    values = {
        "-n": r"[0-9]{1,5}", "--lines": r"[0-9]{1,5}",
        "-u": r"[A-Za-z0-9_@.:-]+", "--unit": r"[A-Za-z0-9_@.:-]+",
        "--since": r"[A-Za-z0-9 :+.-]{1,80}", "--until": r"[A-Za-z0-9 :+.-]{1,80}",
        "-p": r"[0-7]", "--priority": r"[0-7]",
        "-b": r"-?[0-9]{1,4}", "--boot": r"-?[0-9]{1,4}",
        "-o": r"(?:short|short-iso|json|cat)", "--output": r"(?:short|short-iso|json|cat)",
    }
    position = 0
    while position < len(options):
        option = options[position]
        if option in standalone:
            position += 1
            continue
        name, separator, value = option.partition("=")
        if name not in values:
            return False
        if not separator:
            position += 1
            if position >= len(options):
                return False
            value = options[position]
        if not re.fullmatch(values[name], value):
            return False
        position += 1
    return True
