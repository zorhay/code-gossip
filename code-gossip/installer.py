#!/usr/bin/env python3
"""Shared install/uninstall flow for Code Gossip's local agent integrations."""

import argparse
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid

from hooks import codex, cursor
from updates.errors import UpdateError
from updates.process import lock
from updates.storage import record_installation, write_json, write_text, load_installation, installed_version, sync_tree, read_json
from updates.config import UpdatePaths
from updates import recovery


AGENTS = ("codex", "cursor", "claude")
USER_FILES = ("config.json", "phrases.json", "narrator_styles.json")
TAGS = {
    "codex": ("code-gossip/hooks/codex.py",),
    "cursor": ("code-gossip/hooks/cursor.py",),
    "claude": ("code-gossip/engine/play.sh",),
}


def targets(home):
    codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex").expanduser().absolute()
    return {"codex": codex_home / "hooks.json",
            "cursor": home / ".cursor/hooks.json",
            "claude": home / ".claude/settings.json"}


def detected_agents(home, paths):
    commands = {"codex": ("codex",), "cursor": ("cursor", "cursor-agent"), "claude": ("claude",)}
    apps = {"codex": "Codex.app", "cursor": "Cursor.app", "claude": "Claude.app"}
    return [agent for agent in AGENTS if paths[agent].parent.is_dir()
            or any(shutil.which(cmd) for cmd in commands[agent])
            or any((root / apps[agent]).is_dir()
                   for root in (Path("/Applications"), home / "Applications"))]


def read_document(path):
    document = json.loads(path.read_text()) if path.exists() else {}
    if not isinstance(document, dict) or not isinstance(document.get("hooks", {}), dict):
        raise ValueError(f"{path}: expected a JSON object with a hooks object")
    for groups in document.get("hooks", {}).values():
        if not isinstance(groups, list) or any(not isinstance(g, dict) for g in groups):
            raise ValueError(f"{path}: hook events must contain arrays of objects")
        for group in groups:
            if "hooks" in group and (not isinstance(group["hooks"], list)
                    or any(not isinstance(h, dict) for h in group["hooks"])):
                raise ValueError(f"{path}: invalid hook handlers")
    return document


def owned(handler, agent):
    command = handler.get("command", "")
    return isinstance(command, str) and any(tag in command for tag in TAGS[agent])


def merge_hooks(document, agent, new_hooks):
    """Remove only our commands, preserving unrelated handlers in shared groups."""
    updated = copy.deepcopy(document)
    merged = {}
    for event, groups in updated.get("hooks", {}).items():
        kept = []
        for group in groups:
            if agent == "cursor":
                if not owned(group, agent):
                    kept.append(group)
            else:
                handlers = group.get("hooks", [])
                remaining = [handler for handler in handlers if not owned(handler, agent)]
                if remaining or not handlers:
                    kept.append({**group, "hooks": remaining} if handlers else group)
        if kept:
            merged[event] = kept
    for event, groups in new_hooks.items():
        merged.setdefault(event, []).extend(groups)
    if merged:
        updated["hooks"] = merged
    else:
        updated.pop("hooks", None)
    if agent == "cursor" and new_hooks:
        updated.setdefault("version", 1)
    return updated


def is_connected(document, agent):
    return any(owned(handler, agent)
               for groups in document.get("hooks", {}).values()
               for group in groups
               for handler in ([group] if agent == "cursor" else group.get("hooks", [])))


def select_agents(selection, available):
    tokens = re.split(r"[\s,]+", selection.strip().lower())
    aliases = {"1": "all", "2": "codex", "3": "cursor", "4": "claude"}
    tokens = [aliases.get(token, token) for token in tokens]
    if not tokens or any(token not in (*AGENTS, "all") for token in tokens):
        raise ValueError("Select all, codex, cursor, or claude (names or numbers, separated by spaces or commas).")
    chosen = set(available if "all" in tokens else ()) | (set(tokens) - {"all"})
    return [agent for agent in AGENTS if agent in chosen]


def choose(args, available):
    if args.all:
        return list(AGENTS) if args.action == "uninstall" else list(available)
    if args.agents:
        return select_agents(" ".join(args.agents), AGENTS if args.action == "uninstall" else available)
    print(f"Detected {'integrations' if args.action == 'uninstall' else 'agents'}: {', '.join(available) or 'none'}")
    print("  1) all\n  2) codex\n  3) cursor\n  4) claude")
    print("Choose one or more (e.g. 2,4 or codex claude). Explicit names also work if detection missed an agent.")
    while True:
        try:
            selection = input(f"Agents to {args.action}: ")
        except EOFError:
            raise ValueError("No selection received. Use --agents codex,cursor,claude or --all for noninteractive use.") from None
        try:
            return select_agents(selection, AGENTS if args.action == "uninstall" else available)
        except ValueError as exc:
            print(exc)


def definitions(agent, source, dest):
    if agent == "codex":
        return codex.hook_definitions(dest / "hooks/codex.py")
    if agent == "cursor":
        return cursor.hook_definitions(dest / "hooks/cursor.py")
    hooks = json.loads((source / "hooks/claude-hooks.json").read_text())
    for groups in hooks.values():
        for group in groups:
            for handler in group["hooks"]:
                event = handler["command"].rsplit(" ", 1)[1]
                path = shlex.quote(str(dest / "engine/play.sh"))
                handler["command"] = f"if [ -f {path} ]; then /bin/bash {path} {event} || true; fi"
    return hooks


def write_hooks(path, original, updated):
    if read_document(path) != original:
        raise ValueError(f"{path}: hooks changed during installation; retry.")
    if original != updated:
        if path.exists():
            write_text(path.with_name(path.name + ".code-gossip-backup"), path.read_text())
        write_json(path, updated)


PUBLIC_FILES = "VERSION paths.py installer.py update.py update.sh uninstall.sh switch.sh hooks engine soundbar data updates".split()


def validate_layout(source, dest, dev):
    if dev:
        if dest.exists() and (not dest.is_symlink() or dest.resolve() != source):
            raise ValueError("Uninstall the existing installation before changing development checkouts or modes.")
    elif dest.is_symlink():
        raise ValueError(f"{dest} is a dev symlink; use --dev or uninstall it first.")
    root = source if dev else dest
    for name in ("configs", "state", "version_state", "version_state/releases"):
        if (root / name).is_symlink():
            raise ValueError(f"{root / name}: installation directories must not be symlinks.")
    if not dev:
        current = root / "current"
        if current.is_symlink():
            recovery.validate_target(UpdatePaths(root), os.readlink(current))
        elif current.exists():
            raise ValueError("The current release pointer must be a symbolic link.")
        for name in PUBLIC_FILES:
            path = root / name
            if path.exists() and not path.is_symlink():
                raise ValueError("Flat installation layout: back up custom audio, uninstall all integrations without --purge, then reinstall. Settings are retained; audio and Kokoro setup are removed.")
            if path.is_symlink() and os.readlink(path) != "current/" + name:
                raise ValueError(f"Unexpected runtime link: {path}")
    config = root / "configs/config.json"
    if config.exists() and not isinstance(json.loads(config.read_text()), dict):
        raise ValueError(f"{config}: expected a JSON object")
    return root


def sound_files(manifest):
    for layer in ("effects", "voice"):
        for profile in manifest.get(layer, {}).values():
            for spec in profile.get("events", {}).values():
                names = ([spec["file"]] if "file" in spec else spec.get("files", []))
                names = names + [name for sequence in spec.get("sequence", []) for name in sequence]
                yield from (Path(profile.get("dir", "")) / name for name in names)


def preserve_audio(root, candidate):
    """Carry manifest-referenced audio forward without overriding shipped updates."""
    if not (root / "current").is_symlink():
        return
    data = (root / "current").resolve() / "data"
    shipped = set(sound_files(read_json(data / "sounds.json")))
    for name in sorted(set(sound_files(read_json(root / "configs/sounds.json")))):
        if name.is_absolute():
            if name.is_relative_to(root / "data"):
                name = name.relative_to(root / "data")
            elif name.resolve().is_relative_to((root / "version_state").resolve()):
                raise ValueError(f"Use the stable data path for custom audio: {name}")
            else:
                continue
        if name.parts[:1] != ("sounds",) or ".." in name.parts:
            raise ValueError(f"Custom audio must stay under data/sounds: {name}")
        original, target = data / name, candidate / "data" / name
        if not original.resolve().is_relative_to(data / "sounds"):
            raise ValueError(f"Custom audio link escapes data/sounds: {name}")
        if target.exists():
            if not target.is_file() or (name not in shipped and original.read_bytes() != target.read_bytes()):
                raise ValueError(f"Custom audio conflicts with the release package; rename it: {name}")
            continue
        if not original.exists() and name in shipped:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)


def install_files(source, dest, dev):
    """Prepare a complete generation; never copy over executable runtime files."""
    if any(not (source / name).exists() for name in PUBLIC_FILES if name != "VERSION"):
        raise ValueError("Installation source is missing required runtime files.")
    candidate = source if dev else UpdatePaths(dest).releases / uuid.uuid4().hex
    try:
        if not dev:
            candidate.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            ignored = shutil.ignore_patterns(*USER_FILES, "__pycache__",
                ".venv", ".pytest_cache", ".DS_Store", "*.log", "*.sock", "*.code-gossip-backup", "state", "version_state")
            def ignore_local(directory, names):
                return ignored(directory, names) | ({"sounds.json"} if Path(directory) == source / "configs" else set())
            shutil.copytree(source, candidate, ignore=ignore_local)
        if shutil.which("say"):
            subprocess.run(["/bin/bash", str(candidate / "data/sounds/generals/generate.sh")], check=True, timeout=120)
        if not dev:
            preserve_audio(dest, candidate)
            sync_tree(candidate)
    except BaseException:
        if not dev:
            recovery.remove_path(candidate)
        raise
    return candidate


def initialize_files(source, root, dev):
    configs = root / "configs"
    configs.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in USER_FILES:
        target = configs / name
        if not target.exists():
            write_json(target, json.loads((source / "configs" / name.replace(".json", ".defaults.json")).read_text()))
    config = json.loads((configs / "config.json").read_text())
    if config.get("python3_path") != sys.executable:
        write_json(configs / "config.json", {**config, "python3_path": sys.executable})
    if not dev:
        links = {root / name: "current/" + name for name in PUBLIC_FILES}
        links.update({configs / name.replace(".json", ".defaults.json"): "../current/configs/" + name.replace(".json", ".defaults.json") for name in USER_FILES})
        for path, target in links.items():
            if not path.is_symlink():
                path.symlink_to(target)


def owned_process(pid, script):
    if pid <= 1:
        return False
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    generations = script.parents[1] / "version_state/releases"
    scripts = (script, script.resolve(), *generations.glob("*/" + script.parent.name + "/" + script.name))
    return any(result.stdout.strip().endswith(" " + str(path)) for path in scripts)


def stop_process(pid, script):
    """Only terminate an identity-checked process, including a retained generation."""
    if owned_process(pid, script):
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except ProcessLookupError:
            pass


def stop_processes(dest):
    state = dest / "state"
    if state.is_symlink():
        return
    server_script = dest / "soundbar/server.py"
    daemon_script = dest / "engine/kokoro_server.py"
    pid_file = state / ".server.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except ValueError:
            pid = 0
        stop_process(pid, server_script)
        pid_file.unlink()
    sock = state / "kokoro.sock"
    lsof = shutil.which("lsof") or "/usr/sbin/lsof"
    if sock.exists() and Path(lsof).is_file():
        result = subprocess.run([lsof, "-t", str(sock)], capture_output=True, text=True)
        for value in result.stdout.split():
            stop_process(int(value), daemon_script)
        sock.unlink(missing_ok=True)


def remove_files(dest, purge):
    stop_processes(dest)
    if dest.is_symlink():
        dest.unlink()  # Never remove a development checkout.
    elif dest.exists():
        for child in dest.iterdir():
            if not purge and child.name == "configs" and not child.is_symlink():
                for config in child.iterdir():
                    if config.name not in (*USER_FILES, "sounds.json"):
                        recovery.remove_path(config)
            else:
                recovery.remove_path(child)
        if not any(dest.iterdir()):
            dest.rmdir()


def open_panel(dest):
    try:
        subprocess.run([sys.executable, str(dest / "soundbar/launcher.py"), "--background"], check=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"Installation succeeded; open Soundbar later: {dest / 'soundbar/panel.sh'} ({exc})", file=sys.stderr)


def run(args):
    from updates.soundbar import ensure_panel_idle, panel_port, restart_and_verify, stop_panel

    home = Path.home()
    source = Path(__file__).resolve().parent
    dest = home / ".code-gossip"
    targets_by_agent = targets(home)
    uninstall = args.action == "uninstall"
    documents = {agent: read_document(path) for agent, path in targets_by_agent.items()} if uninstall else {}
    available = [agent for agent in documents if is_connected(documents[agent], agent)] if uninstall else detected_agents(home, targets_by_agent)
    selected = choose(args, available)
    if not selected:
        raise ValueError("No agents detected or selected. Specify --agents codex, cursor, or claude.")
    root = dest.resolve() if uninstall else validate_layout(source, dest, args.dev)
    paths = UpdatePaths(root)
    if paths.version_state.is_symlink():
        raise ValueError("Installation metadata must not be a symbolic link.")
    if not uninstall and not shutil.which("jq"):
        raise ValueError("jq is required for sound playback. Install jq and try again.")
    # Validate every selected document even for a dry run.
    for agent in selected:
        read_document(targets_by_agent[agent])
    print(f"{'Preview: would ' if args.dry_run else ''}{args.action.capitalize()} for {', '.join(selected)}")
    for agent in selected:
        print(f"  {'Remove' if uninstall else 'Merge'} Code Gossip hooks: {targets_by_agent[agent]}")
    if args.dry_run:
        print("No changes made.")
        return
    with lock(root, inherited=getattr(args, "update_lock_fd", None)):
        recovery.recover(paths)
        if not uninstall:
            validate_layout(source, dest, args.dev)
        documents = {agent: read_document(path) for agent, path in targets_by_agent.items() if uninstall or agent in selected}
        remaining = [agent for agent in documents if agent not in selected and is_connected(documents[agent], agent)]
        port = panel_port(paths)
        verify = not uninstall and (not args.no_panel or getattr(args, "update_lock_fd", None) is not None or paths.panel_pid.exists())
        running = ensure_panel_idle(paths, port) if verify else False
        if uninstall and not remaining and paths.panel_pid.exists():
            pid = paths.panel_pid.read_text().strip()
            if pid.isdigit() and owned_process(int(pid), root / "soundbar/server.py"):
                ensure_panel_idle(paths, port)
        candidate = install_files(source, root, args.dev) if not uninstall else None
        documents = {agent: read_document(targets_by_agent[agent]) for agent in selected}
        updated = {agent: merge_hooks(documents[agent], agent, {} if uninstall else definitions(agent, source, dest)) for agent in selected}
        new_target = str(candidate.relative_to(root)) if candidate and not args.dev else None
        dev_link = dest if not uninstall and args.dev and not dest.is_symlink() else None
        files = [paths.installation] + ([] if uninstall else [root / "configs" / name for name in USER_FILES])
        journal = recovery.begin(paths, {agent: targets_by_agent[agent] for agent in selected}, files,
                                 new_target, dev_link, port if running else None, runtime=not uninstall)
        try:
            if not uninstall:
                stop_panel(paths)
                stop_processes(dest)
                if dev_link:
                    dev_link.symlink_to(root, target_is_directory=True)
                initialize_files(candidate, root, args.dev)
                if new_target:
                    recovery.activate(paths, new_target)
            for agent in selected:
                write_hooks(targets_by_agent[agent], documents[agent], updated[agent])
            record_installation(root, targets_by_agent, selected, dev=dest.is_symlink(), uninstall=uninstall)
            if verify:
                restart_and_verify(paths, load_installation(paths), port, installed_version(root))
            recovery.commit(paths)
        except BaseException:
            recovery.recover(paths)
            raise
        if uninstall and not remaining:
            remove_files(dest, args.purge)
        elif not uninstall and not args.dev:
            try:
                recovery.collect_releases(paths, journal["previous"])
            except OSError as error:
                print(f"Installed; old release cleanup can be retried: {error}", file=sys.stderr)
        elif uninstall:
            print("Keep shared Code Gossip files and processes for: " + ", ".join(remaining))
    print(f"Code Gossip {'uninstalled' if uninstall else 'installed'} for {', '.join(selected)}.")
    if not uninstall:
        if "codex" in selected:
            print("Open /hooks in Codex CLI to review and trust the commands, then start a new chat.")
        if not args.no_panel:
            open_panel(dest)


def install_latest(arguments):
    """A source checkout installs the same published package as the updater."""
    from updates.github import latest_release
    from updates.source import fetch_source

    release = latest_release()
    print(f"Installing Code Gossip {release.version} from its release package…", flush=True)
    with tempfile.TemporaryDirectory(prefix="code-gossip-install-") as temporary:
        source = fetch_source(release, Path(temporary))
        subprocess.run([sys.executable, "-B", str(source / "code-gossip/installer.py"),
                        "install", *arguments], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("action", choices=("install", "uninstall"))
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--agents", nargs="+", metavar="AGENT", help="agent names separated by spaces or commas; skips the prompt")
    selection.add_argument("--all", action="store_true", help="skip questions; install detected agents or uninstall every integration")
    parser.add_argument("--dry-run", action="store_true", help="preview without changing files or processes")
    parser.add_argument("--dev", action="store_true", help="install using a symlink to this checkout")
    parser.add_argument("--no-panel", action="store_true", help="install without starting Soundbar or opening a browser")
    parser.add_argument("--purge", action="store_true", help="delete user settings when the last integration is uninstalled")
    parser.add_argument("--update-lock-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.no_panel and args.action != "install":
        parser.error("--no-panel applies only to install")
    if args.dev and args.action != "install" or args.purge and args.action != "uninstall":
        parser.error("--dev applies only to install; --purge applies only to uninstall")
    try:
        if args.action == "install" and not args.dev and not Path(__file__).with_name("VERSION").is_file():
            install_latest(sys.argv[2:])
        else:
            run(args)
    except (OSError, ValueError, UpdateError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"Code Gossip: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "\nCancelled.\n")


if __name__ == "__main__":
    main()
