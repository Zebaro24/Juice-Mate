#!/usr/bin/env python3
# template-managed: core/.claude/hooks/guard-secrets.py — edit in _Claude-Template, not here
"""PreToolUse(Bash|PowerShell) guard — keep real secrets out of the transcript.

`settings.json` denies *reading* secret files with the Read tool. This closes the other doors: a
shell command that prints the same values. Dumping `.env` from a shell and reading it with Read have
identical consequences — the value lands in the transcript, quotable, logged, impossible to take back.

Refused: printing an env file, anything under `_secrets/`, a private key; a full dump of the process
environment; Docker commands that print a container's environment.
Allowed: `.env.example` (names, not values), `docker inspect --format` picking one field,
`docker compose config -q`, and anything that merely *names* a variable.

Every pattern is deliberately narrow: a guard that blocks ordinary work gets routed around, and then
it protects nothing at all. Extra project patterns: `.claude/project.json` → secrets.extra_path_patterns.

Deny = exit 2, allow = exit 0. Stdlib only.
"""
import fnmatch
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

# Commands that dump file contents, anchored to the command position of a simple command so that
# "concatenate" or "only" never read as `cat` / `nl`.
READERS = re.compile(
    r"(?:^|['\"`(]|\bsudo\s+|\bxargs\s+)\s*"
    r"(cat|tac|type|more|less|head|tail|bat|nl|strings|od|xxd|sed|awk|grep|rg|base64|"
    r"Get-Content|gc|Select-String|sls|cp|copy|Copy-Item)\b",
    re.I,
)
# The lookbehind keeps `self.env`, `os.environ`, `settings.environment` from tripping it.
SECRET_PATH = (
    r"(?<![\w.])\.env(?!\.example)(\.[\w-]+)?(?!\.example)(?![\w])"
    r"|_secrets[/\\]"
    r"|\.pem\b|\.p12\b|\.pfx\b"
    r"|id_ed25519(?!\.pub)|id_rsa(?!\.pub)"
    r"|settings\.local\.json"
)
# What a glob operand is matched against — a pattern that can expand to any of these is a secret read.
SECRET_NAMES = (".env", ".env.local", ".env.production", ".env.development", "_secrets", "id_rsa",
                "id_ed25519", "settings.local.json", "key.pem")
FULL_ENV_DUMP = re.compile(
    r"^(env|printenv|set|export\s+-p|Get-ChildItem\s+env:|gci\s+env:|ls\s+env:|dir\s+env:)\s*$", re.I)
DOCKER_INSPECT = re.compile(r"\bdocker\s+(?:container\s+)?inspect\b(?!.*(?:\s-f\b|--format))")
DOCKER_EXEC_ENV = re.compile(r"\bdocker\s+exec\b.*\b(env|printenv)\b|\bdocker\s+exec\b.*/proc/\d+/environ")
COMPOSE_CONFIG = re.compile(r"\bdocker[\s-]compose\b.*\bconfig\b(?!.*(?:\s-q\b|--quiet|--services))")


def main():
    data = _lib.read_event()
    cmd = _lib.command_of(data)
    if not cmd:
        return 0
    cfg = _lib.load_config()
    try:
        secret = re.compile("|".join([SECRET_PATH] + [str(p) for p in cfg["secrets"]["extra_path_patterns"]]), re.I)
    except re.error:
        secret = re.compile(SECRET_PATH, re.I)  # a broken project pattern must not switch the guard off

    # Reader and secret must sit in the SAME simple command: checked across the whole line,
    # `grep x .gitignore` next to a heredoc that merely mentions ".env" was refused.
    for seg in _lib.segments(cmd):
        # The heredoc operator is not a path; its body arrives as later segments (text being written).
        head = re.sub(r"<<-?\s*['\"]?\w+['\"]?", " ", seg)
        # Quotes and escapes do not change the path the shell opens: `cat ".e"nv`, `cat .e\nv`.
        plain = re.sub(r"[\"'`\\]", "", head)
        reads = READERS.search(head) or re.search(r"(?:^|\s)<\s*\S", plain)
        # A glob that can expand to a secret name: `cat .e*`, `cat ?env`, `type _sec*/k.txt`.
        globbed = any(fnmatch.fnmatch(name, part) for tok in plain.split() if re.search(r"[*?\[]", tok)
                      for part in re.split(r"[/\\]", tok) if part for name in SECRET_NAMES)
        if reads and (secret.search(head) or secret.search(plain) or globbed):
            _lib.deny("This command prints a secret file (.env, _secrets/, a private key or "
                      "settings.local.json) — its contents would land in the transcript. Look at "
                      "`.env.example` for the names; ask the owner for values.")
        if FULL_ENV_DUMP.search(seg):
            _lib.deny("A full environment dump prints every token. Ask for one variable by name.")
        if DOCKER_INSPECT.search(seg) or DOCKER_EXEC_ENV.search(seg) or COMPOSE_CONFIG.search(seg):
            _lib.deny("This prints a container's environment, tokens included. For inspect pick one "
                      "field with --format; for compose use `config -q` or `config --services`.")
    return 0


sys.exit(main())
