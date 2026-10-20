#!/usr/bin/env python3
# template-managed: core/.claude/hooks/_lib.py — edit in _Claude-Template, not here
"""Shared machinery for every guard: the project config, the shell parser, approvals, deny.

Every hook in `.claude/hooks/` is the same file in every project. What differs between projects
lives in `.claude/project.json`, and this module is the only place that reads it. That is the whole
point: a fix to a guard is made once, in the template, and copied over unchanged — instead of being
re-applied by hand to seven diverged copies.

Stdlib only. Nothing here may raise into a hook: a crashing guard is a guard that guards nothing.
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# <root>/.claude/hooks/_lib.py -> <root>. Derived from this file, never from the shell's cwd: the
# Bash tool's cwd persists between calls, so a stray earlier `cd sub` would move every lookup.
ROOT = os.path.dirname(os.path.dirname(HERE))

DEFAULTS = {
    "template": {"version": "0.0.0", "profile": "solo", "addons": [], "overrides": []},
    "project": {"name": "", "owner_language": "Russian", "ui_language": None},
    "git": {
        "main_branch": "main",
        # Non-empty turns on the team rules: no edits (tool or shell) on these branches.
        "protected_branches": [],
        "release_tag_pattern": r"^v\d+\.\d+\.\d+",
    },
    "approval": {
        "ttl_minutes": 15,
        # solo: one approval = one push. team: one approval covers every repo of a feature.
        "consume": True,
        # The marker records HEAD; a commit made after approving makes it stale.
        "bind_head": True,
    },
    "attribution": {"forbid": True, "extra_words": []},
    "secrets": {"extra_path_patterns": []},
    "notify": {"windows": True, "telegram": False, "telegram_delete_after": 15},
    "team": {"forbid_merge": True, "forbid_ready": True, "issue_close_needs_approval": True},
}


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def load_config(root=None):
    """project.json merged over DEFAULTS. A missing or broken file means defaults (solo)."""
    path = os.path.join(root or project_root(), ".claude", "project.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return _merge(DEFAULTS, data)
    except (OSError, ValueError):
        pass
    return _merge(DEFAULTS, {})


def project_root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or ROOT


def read_event():
    """The hook payload as a dict, or None for anything malformed (the caller then allows)."""
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.buffer.read().decode("utf-8", "replace")
        data = json.loads(raw) if raw.strip() else None
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def tool_input(data):
    ti = (data or {}).get("tool_input")
    return ti if isinstance(ti, dict) else {}


def command_of(data):
    cmd = tool_input(data).get("command")
    return cmd if isinstance(cmd, str) else ""


# --- deny -----------------------------------------------------------------------------------------

CHAINED = re.compile(r"&&|\|\||;")
# A deny kills the WHOLE tool call before execution, but the reason names only the offending part —
# so a denied push at the end of `git commit … && git push` reads as "the commit went through". It did
# not, and an `--amend` afterwards rewrites an older commit. Learned the hard way in Director-Mode-AI.
CHAIN_NOTE = ("\nNOTHING in this command ran: a refusal cancels the whole call, including every part "
              "chained with && / || / ;. A `git commit` in front of a blocked push was NOT created — do "
              "not `--amend` afterwards. Re-run the parts you still need as separate calls.")


def deny(reason, cmd=""):
    if cmd and CHAINED.search(cmd):
        reason += CHAIN_NOTE
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))
    sys.exit(2)


# --- shell parsing --------------------------------------------------------------------------------

TOKEN = re.compile(r'''"(?:[^"\\]|\\.)*"|'[^']*'|\S+''')


def unquote(tok):
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
        return tok[1:-1]
    return tok


def segments(cmd):
    """Split a command line into simple commands at && || ; | & and newlines — outside quotes.

    Quote-aware on purpose: `git commit -m "a; b"` is one segment, and a split inside the quotes
    used to turn the second half of a message into a "command".
    """
    out, buf, quote, i = [], [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "\\" and i + 1 < len(cmd) and cmd[i + 1] in "\"'":
            # `\"` does not open a quote in bash. A backslash before a separator is NOT honoured:
            # PowerShell treats `\` as a literal, so splitting there anyway errs toward checking more.
            buf.append(cmd[i:i + 2])
            i += 2
            continue
        if ch in "\"'":
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch in ";|&\n":
            out.append("".join(buf))
            buf = []
            while i + 1 < len(cmd) and cmd[i + 1] in "|&":
                i += 1
            i += 1
            continue
        buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


def git_call(seg):
    """For a `git ...` segment: (subcommand, args_after_it, global_opts dict); else None.

    Walks past global options (`-C dir`, `-c k=v`, `--no-pager`, ...) so `git -C sub -c x=y push`
    is still a push — a regex expecting `git\\s+push` let exactly that through.
    """
    # Grouping and substitution openers are not the command: `(git push)`, `{ git push; }`, `$(git push)`.
    seg = re.sub(r"^[\s({`$]+", "", seg)
    toks = [unquote(t) for t in TOKEN.findall(seg)]
    # Leading env assignments and wrappers: `GIT_X=1 git push`, `sudo git push`, `& git push`.
    # A wrapper's own flags and numbers go too: `timeout 30 git push`, `nice -n 5 git push`.
    after_wrapper, env = False, []
    while toks and (re.match(r"^\w+=", toks[0]) or toks[0] in WRAPPERS
                    or after_wrapper and re.match(r"^(-\S*|\d+[smhd]?)$", toks[0])):
        after_wrapper = after_wrapper or toks[0] in WRAPPERS
        if re.match(r"^\w+=", toks[0]):
            env.append(toks[0])
        toks = toks[1:]
    if not toks:
        return None
    name = os.path.basename(toks[0].replace("\\", "/").strip("\"'")).lower()
    if name not in ("git", "git.exe"):
        return None
    # `GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=x git commit` is `-c core.hooksPath=x`.
    keys = {m.group(1): v for e in env for m in [re.match(r"^GIT_CONFIG_KEY_(\d+)=(.*)$", e)] if m for v in [m.group(2)]}
    vals = {m.group(1): m.group(2) for e in env for m in [re.match(r"^GIT_CONFIG_VALUE_(\d+)=(.*)$", e)] if m}
    opts, i = {"-c": [f"{k}={vals.get(n, '')}" for n, k in keys.items()]} if keys else {}, 1
    while i < len(toks):
        t = toks[i]
        if t in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env") and i + 1 < len(toks):
            opts.setdefault("-c" if t == "--config-env" else t, []).append(toks[i + 1])
            i += 2
            continue
        if t.startswith("--config-env="):
            opts.setdefault("-c", []).append(t.split("=", 1)[1])
            i += 1
            continue
        if t.startswith("-"):
            i += 1
            continue
        return t, toks[i + 1:], opts
    return None, [], opts


WRAPPERS = {"sudo", "&", "command", "env", "exec", "nohup", "nice", "time", "timeout", "stdbuf", "xargs", "ionice"}
# `bash -c "git push"`, `pwsh -Command "git push"`: the payload is a command line of its own.
NESTED = re.compile(r"^\s*(?:\S*[/\\])?(?:bash|sh|zsh|dash|pwsh|powershell)(?:\.exe)?\b.*?\s-(?:[a-z]*c|Command)\s+(.+)$",
                    re.I | re.S)
ENCODED = re.compile(r"^\s*(?:\S*[/\\])?(?:pwsh|powershell)(?:\.exe)?\b.*?\s-(?:e|ec|enc|encodedcommand)\s+(\S+)", re.I)


def decode_ps(b64):
    """`powershell -EncodedCommand` takes base64 of UTF-16LE."""
    import base64
    try:
        return base64.b64decode(b64 + "=" * (-len(b64) % 4)).decode("utf-16-le", "replace")
    except Exception:
        return ""


def git_calls(cmd, _depth=0):
    for seg in segments(cmd):
        enc = ENCODED.match(seg) if _depth < 3 else None
        if enc:
            yield from git_calls(decode_ps(unquote(enc.group(1))), _depth + 1)
            continue
        m = NESTED.match(seg) if _depth < 3 else None
        if m:
            yield from git_calls(unquote(m.group(1).strip()), _depth + 1)
            continue
        gc = git_call(seg)
        if gc is not None:
            yield seg, gc


def gh_verb(cmd, noun, verb):
    """True when some segment runs `gh <noun> ... <verb>` with only flags in between.

    `gh pr --repo o/n merge 12` is a working invocation, so adjacency is not required. Only flags may
    sit between, which keeps `gh pr comment 1 --body "ready to merge"` from matching.
    """
    flags = r"(?:\s+(?:--[\w-]+(?:=\S+)?|-\w)(?:\s+[^-\s]\S*)?)*"
    pat = re.compile(rf"^\s*(?:\S*[/\\])?gh(?:\.exe)?\s+{noun}{flags}\s+{verb}\b")
    return any(pat.search(s) for s in segments(blank_quotes(cmd)))


QUOTED = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'[^']*'")


def blank_quotes(cmd):
    """Quoted runs are data, not syntax — `grep "gh pr merge"` must not read as a merge."""
    return QUOTED.sub('""', cmd)


# --- git state ------------------------------------------------------------------------------------

_branch_cache = {}


def git_out(repo, *args):
    try:
        r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=8)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def repo_root(path):
    """The git repo enclosing `path`, walking up. Works for files that do not exist yet."""
    d = os.path.abspath(path)
    if not os.path.isdir(d):
        d = os.path.dirname(d)
    while d:
        if os.path.exists(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return None


def branch_of(repo):
    if repo not in _branch_cache:
        _branch_cache[repo] = git_out(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return _branch_cache[repo]


def protected_branch_for(path, cfg):
    """(repo, branch) when `path` sits in a repo parked on a protected branch, else None."""
    protected = cfg["git"]["protected_branches"]
    if not protected:
        return None
    repo = repo_root(path)
    if not repo:
        return None
    branch = branch_of(repo)
    return (repo, branch) if branch in protected else None


def repos_under(root):
    """The root itself if it is a repo, plus every repo one level below (multi-repo workspaces)."""
    found = []
    if os.path.exists(os.path.join(root, ".git")):
        found.append(root)
    try:
        for name in sorted(os.listdir(root)):
            sub = os.path.join(root, name)
            if os.path.isdir(sub) and os.path.exists(os.path.join(sub, ".git")):
                found.append(sub)
    except OSError:
        pass
    return found


def repo_key(root, repo):
    rel = os.path.relpath(repo, root).replace("\\", "/")
    return "." if rel == "." else rel


# --- approvals ------------------------------------------------------------------------------------
# A marker is `.claude/.approve-<action>`, JSON: {"created": <unix>, "heads": {"<repo>": "<sha>"}}.
# Minted only by `scripts/approve.py`, which a skill runs after a green gate. Its age is the TTL, its
# heads bind it to the exact commits that were checked — a commit after approving makes it stale.

def marker_path(root, action):
    return os.path.join(root, ".claude", f".approve-{action}")


def check_approval(root, action, cfg, target_repo=None):
    """'fresh' | 'expired' | 'stale' | 'absent'. Expired and stale markers are removed."""
    path = marker_path(root, action)
    if not os.path.exists(path):
        return "absent"
    ttl = float(cfg["approval"]["ttl_minutes"]) * 60
    try:
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return "absent"
    if age > ttl:
        _remove(path)
        return "expired"
    if cfg["approval"]["bind_head"] and target_repo:
        try:
            with open(path, encoding="utf-8") as f:
                heads = (json.load(f) or {}).get("heads") or {}
        except (OSError, ValueError, AttributeError):
            heads = {}
        expected = heads.get(repo_key(root, target_repo))
        actual = git_out(target_repo, "rev-parse", "HEAD")
        # approve.py records every repo it can see, so a marker that does not know this repo was not
        # minted for it. Only an unreadable HEAD fails open.
        if actual and (not expected or actual != expected):
            _remove(path)
            return "stale"
    return "fresh"


def git_bool(value):
    """git's own boolean spellings: true/yes/on/1 and false/no/off/0/empty."""
    v = (value or "").strip().lower()
    return True if v in ("true", "yes", "on", "1") else False if v in ("false", "no", "off", "0", "") else None


def consume_approval(root, action, cfg):
    if cfg["approval"]["consume"]:
        _remove(marker_path(root, action))


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
