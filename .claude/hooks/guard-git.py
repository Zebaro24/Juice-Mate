#!/usr/bin/env python3
# template-managed: core/.claude/hooks/guard-git.py — edit in _Claude-Template, not here
"""PreToolUse(Bash|PowerShell) guard on everything that leaves this machine or cannot be undone.

Always, in every profile:
  1) dangerous git is refused — force-push (any spelling), --no-verify, --no-gpg-sign,
     reset --hard <remote>, clean -f, discarding the whole working tree;
  2) the author is the human — a commit, tag, PR or issue text may not carry Co-Authored-By or
     mention the assistant (`.claude/project.json` → attribution);
  3) a push needs a fresh approval marker (`scripts/approve.py push`, minted by /push or /approve);
  4) pushing a release tag needs its own marker (`scripts/approve.py release`, minted by /release).

Team profile (`git.protected_branches` non-empty) adds:
  5) `gh pr merge` / `gh pr ready` are the owner's — refused outright;
  6) closing an issue by hand needs the approval;
  7) a shell write into a repo parked on a protected branch is the same edit guard-branch refuses.

Commits stay free: they are local savepoints. The approval gates the push, not the commit.

WHAT THIS IS AND ISN'T. It stops the command an agent reaches for on autopilot. It cannot stop a
deliberate evasion — `python -c "subprocess.run(['git','push','-f'])"` has nothing in its text to
match. The rules live in the docs; this is the tripwire. A passing command is not a permission.

Wired to BOTH shell tools: a guard on Bash alone is walked past by picking PowerShell.
Deny = JSON + exit 2, allow = exit 0. Stdlib only.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

# Paths and the harness's own variable names contain "claude" and are machinery, not attribution:
# `git add CLAUDE.md && git commit` and `$CLAUDE_PROJECT_DIR` must not block a commit.
PATHISH = re.compile(r"\S*[/\\]\S*|\bCLAUDE\.md\b|\.claude\b", re.I)
ENVISH = re.compile(r"\bCLAUDE_[A-Z0-9_]+\b")
HEREDOC = re.compile(r"""<<-?\s*['"]?(\w+)['"]?[^\n]*\n(.*?)\n\s*\1\b""", re.S)
MSG_FLAGS = {"-m", "--message", "-b", "--body", "-t", "--title"}
FILE_FLAGS = {"-F", "--file", "--body-file"}


def option_tokens(rest):
    """The flags of a subcommand — skipping the values of -m/-F/-C/... so a message is never a flag."""
    out, skip = [], False
    for a in rest:
        if skip:
            skip = False
            continue
        if a == "--":
            break
        if a in ("-m", "-F", "-C", "-c", "--message", "--file", "-t", "--template"):
            skip = True
            continue
        if a.startswith("-"):
            out.append(a)
    return out


def dangerous(cmd):
    for _seg, (sub, rest, opts) in _lib.git_calls(cmd):
        flags = option_tokens(rest)
        low = [a.lower() for a in flags]
        cfg_opts = [v.lower().replace(" ", "").partition("=") for v in opts.get("-c", [])]
        # Checked across all of `rest`, not only flags: a value the skipper thought it saw must not hide it.
        raw = [a.lower() for a in rest]
        if "--no-verify" in raw:
            return "--no-verify"
        # `-n` is --no-verify for these; for push it is --dry-run, which is harmless.
        if sub in ("commit", "merge", "revert", "cherry-pick") and any(re.match(r"^-[a-zA-Z]*n[a-zA-Z]*$", a) for a in flags):
            return "-n (= --no-verify)"
        if "--no-gpg-sign" in raw or any(k == "core.hookspath" or (k == "commit.gpgsign" and _lib.git_bool(v) is not True)
                                         for k, _eq, v in cfg_opts):
            return "skipping hooks or signing (--no-gpg-sign / -c core.hooksPath / -c commit.gpgsign=false)"
        if sub == "push":
            for a in rest:
                if a.startswith("--force") or re.match(r"^-[a-zA-Z]*f[a-zA-Z]*$", a):
                    return "force-push"
                if a.startswith("+") and len(a) > 1:
                    return "force-push (+refspec)"
                if a in ("--mirror", "--delete", "-d", "--prune") or (a.startswith(":") and len(a) > 1):
                    return f"destructive push ({a}: deletes remote refs)"
        if sub == "reset" and "--hard" in low:
            refs = [a for a in rest if not a.startswith("-")]
            if any("/" in r or r == "origin" or "@{" in r or r.upper() == "FETCH_HEAD" for r in refs):
                return "reset --hard <remote>"
        if sub == "clean" and any(a == "--force" or re.match(r"^-[a-zA-Z]*f", a) for a in rest):
            return "git clean -f (deletes untracked files)"
        if sub in ("checkout", "restore") and "--staged" not in low:
            paths = rest[rest.index("--") + 1:] if "--" in rest else [a for a in rest if not a.startswith("-")]
            if any(p in (".", "*", ":/") for p in paths):
                return f"git {sub} of the whole tree (discards every uncommitted change)"
    return None


def message_texts(seg, cwd):
    """Every piece of text this segment would write into history or onto GitHub."""
    toks = [_lib.unquote(t) for t in _lib.TOKEN.findall(seg)]
    texts = []
    for i, t in enumerate(toks):
        flag, _, inline = t.partition("=")
        if flag in MSG_FLAGS or re.match(r"^-[a-z]*m$", t):
            val = inline if inline else (toks[i + 1] if i + 1 < len(toks) else "")
            texts.append(val)
        elif flag in FILE_FLAGS:
            path = inline if inline else (toks[i + 1] if i + 1 < len(toks) else "")
            if path and path != "-":
                try:
                    with open(os.path.join(cwd, path), encoding="utf-8", errors="replace") as f:
                        texts.append(f.read())
                except OSError:
                    pass
    return texts


def writes_text(seg):
    gc = _lib.git_call(seg)
    if gc and gc[0] in ("commit", "tag", "notes"):
        return True
    return bool(re.match(r"^\s*(?:\S*[/\\])?gh(?:\.exe)?\s+(?:pr|issue|release)\s+(?:create|edit|comment)\b", seg))


def attribution_hit(cmd, cwd, cfg):
    if not cfg["attribution"]["forbid"]:
        return False
    words = [r"co-authored-by", r"generated with", "\U0001F916", r"\bclaude\b", r"\banthropic\b"]
    words += [rf"\b{re.escape(w)}\b" for w in cfg["attribution"]["extra_words"]]
    pat = re.compile("|".join(words), re.I)
    heredocs = [m.group(2) for m in HEREDOC.finditer(cmd)]
    for seg in _lib.segments(cmd):
        if not writes_text(seg):
            continue
        for text in message_texts(seg, cwd) + heredocs:
            if pat.search(ENVISH.sub(" ", PATHISH.sub(" ", text))):
                return True
    return False


def pushes(cmd):
    """[(repo_dir_or_None, pushes_a_tag)] for every `git push` in the command."""
    out = []
    for _seg, (sub, rest, opts) in _lib.git_calls(cmd):
        if sub != "push":
            continue
        # A wildcard refspec (`refs/*:refs/*`) can carry tags too, so it counts as a release push.
        tag = any(a in ("--tags", "--follow-tags") or "refs/tags/" in a or "*" in a for a in rest) or any(
            k.strip().lower() == "push.followtags" and _lib.git_bool(v) is not False
            for k, _eq, v in (o.partition("=") for o in opts.get("-c", [])))
        out.append(((opts.get("-C") or [None])[-1], tag, rest))
    return out


def main():
    data = _lib.read_event()
    cmd = _lib.command_of(data)
    if not cmd:
        return 0
    root = _lib.project_root()
    cwd = data.get("cwd") or root
    cfg = _lib.load_config(root)
    team = bool(cfg["git"]["protected_branches"])
    try:
        tag_re = re.compile(str(cfg["git"]["release_tag_pattern"]))
    except re.error:
        tag_re = re.compile(_lib.DEFAULTS["git"]["release_tag_pattern"])

    reason = dangerous(cmd)
    if reason:
        _lib.deny(f"Dangerous git blocked ({reason}). If it is truly needed, the owner types it by hand.", cmd)

    # The marker is evidence that a gate ran; only scripts/approve.py writes it. A shell write would
    # be a forgery (the Edit/Write tools are denied in settings.json).
    # Matched on the raw text, quotes and escapes removed: any command that names a marker, except the
    # one script that mints it. Reading a marker is never needed, so no read is lost.
    if ".approve-" in re.sub(r"[\"'`\\]", "", cmd) and not re.match(
            r"^\s*(?:python3?|py)(?:\.exe)?\s+(?:\S*[/\\])?scripts[/\\](?:approve|release)\.py(?:\s+[\w-]+)*\s*$", cmd):
        _lib.deny("Approval markers are written only by `scripts/approve.py`, through /push or the owner's "
                  "/approve — never by hand.", cmd)

    if attribution_hit(cmd, cwd, cfg):
        _lib.deny("The text of a commit, tag, PR or issue must not carry Co-Authored-By or mention the "
                  "assistant or its vendor — the author is the human. Commit format: one line, "
                  "`type(scope): summary`.", cmd)

    for repo_dir, tag_flag, rest in pushes(cmd):
        target = _lib.repo_root(os.path.join(cwd, repo_dir) if repo_dir else cwd) or root
        # push.followTags set in the repo's own config sends tags with a plain push.
        follow = _lib.git_out(target, "config", "--type=bool", "--get", "push.followTags") == "true"
        is_release = tag_flag or follow or any(tag_re.search(a.split(":")[-1]) for a in rest if not a.startswith("-"))
        if is_release:
            state = _lib.check_approval(root, "release", cfg, target)
            if state != "fresh":
                _lib.deny(f"Pushing a release tag deploys. It goes only through /release (strict gate → "
                          f"version → CHANGELOG → the owner's go). Release approval: {state}.", cmd)
            continue
        state = _lib.check_approval(root, "push", cfg, target)
        if state != "fresh":
            how = "/approve (the owner runs it)" if team else "/push (gate → approval → push)"
            hint = {"stale": " A commit was made after approving — re-run the gate and approve again.",
                    "expired": " The approval lapsed."}.get(state, "")
            _lib.deny(f"git push leaves this machine and needs a fresh approval: {how}.{hint}", cmd)

    if team:
        tc = cfg["team"]
        if tc["forbid_merge"] and (_lib.gh_verb(cmd, "pr", "merge") or re.search(
                r"\bgh\s+api\b[^|&;\n]*(?:pulls/\d+/merge|mergePullRequest)", cmd)):
            _lib.deny("Merging is the owner's step (/merge-task). A raw merge skips every check it makes.", cmd)
        if tc["forbid_ready"] and (_lib.gh_verb(cmd, "pr", "ready") or "markPullRequestReadyForReview" in cmd):
            _lib.deny("Taking a PR out of draft is the owner's step — leave it a draft and say so.", cmd)
        if tc["issue_close_needs_approval"] and _lib.gh_verb(cmd, "issue", "close"):
            if _lib.check_approval(root, "push", cfg) != "fresh":
                _lib.deny("Closing an issue by hand needs the owner's /approve — normally a merged PR "
                          "closes it via `Closes #n`.", cmd)
        for target in shell_write_targets(cmd):
            path = target if os.path.isabs(target) else os.path.join(cwd, target)
            hit = _lib.protected_branch_for(path, cfg)
            if hit:
                _lib.deny(f"Writing to '{target}' is blocked: its repo ({hit[0]}) is on '{hit[1]}'. Switch "
                          f"to a task branch first — the same rule guard-branch applies to Edit/Write.", cmd)

    # Consume only once nothing in the command was refused.
    if pushes(cmd):
        _lib.consume_approval(root, "push", cfg)
        if any(t or any(tag_re.search(a.split(":")[-1]) for a in r if not a.startswith("-"))
               for _d, t, r in pushes(cmd)):
            _lib.consume_approval(root, "release", cfg)
    return 0


# --- shell writes (team) --------------------------------------------------------------------------

INPLACE = re.compile(r"(?:^|\s)(?:sed\s[^|&;\n]*?-\w*i\w*|tee|Set-Content|Add-Content|Out-File)\b(?P<rest>[^|&;\n]*)")
SED_EXPR = re.compile(r"^[a-z]\W.*\W$", re.I)


def redirect_targets(cmd):
    """Targets of `>` / `>>` outside quotes. `$VAR` targets are skipped: their value is unknowable here
    and guessing in the blocking direction is the worse failure."""
    targets, quote, i = [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if quote:
            quote = None if ch == quote else quote
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            continue
        if ch == ">":
            i += 1
            if i < len(cmd) and cmd[i] == ">":
                i += 1
            while i < len(cmd) and cmd[i] in " \t":
                i += 1
            start = i
            while i < len(cmd) and cmd[i] not in " \t|&;<>\n":
                i += 1
            tok = cmd[start:i].strip("\"'")
            if tok and tok not in ("&1", "&2") and "$" not in tok and "`" not in tok and tok != "/dev/null":
                targets.append(tok)
            continue
        i += 1
    return targets


def shell_write_targets(cmd):
    targets = redirect_targets(cmd)
    for seg in _lib.segments(cmd):
        for m in INPLACE.finditer(_lib.blank_quotes(seg)):
            targets += [t for t in m.group("rest").split() if not t.startswith("-") and not SED_EXPR.match(t)
                        and t != '""']
        toks = [_lib.unquote(t) for t in _lib.TOKEN.findall(seg)]
        operands = [t for t in toks[1:] if not t.startswith("-")]
        name = os.path.basename(toks[0]).lower() if toks else ""
        if name in ("cp", "mv", "copy", "move", "copy-item", "move-item") and operands:
            targets.append(operands[-1])                      # the destination
        elif name in ("rm", "del", "remove-item", "ri", "perl", "truncate") and operands:
            targets += [t for t in operands if not SED_EXPR.match(t)]
    for _seg, (sub, rest, opts) in _lib.git_calls(cmd):
        if sub in ("checkout", "restore") and "--" in rest:
            base = (opts.get("-C") or [""])[-1]
            targets += [os.path.join(base, p) if base else p for p in rest[rest.index("--") + 1:]]
    return targets


sys.exit(main())
