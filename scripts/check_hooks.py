#!/usr/bin/env python3
# template-managed: core/scripts/check_hooks.py — edit in _Claude-Template, not here
"""Behaviour check for .claude/hooks — the gate's `hooks` target. No CI ever sees the guards.

Each case is a command string and whether the guard must refuse it. The strings only go to the
hook's stdin; nothing here is executed. Runs every case in a throwaway project for both profiles
(solo and team), with and without an approval marker, and against a real git repo for the
HEAD-binding and protected-branch rules.

Found a hole or a false alarm? Add the case here first, watch it fail, then fix the guard.

Usage:  python scripts/check_hooks.py [-v]
Stdlib only.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(ROOT, ".claude", "hooks")

SECRETS = [
    ("cat .env", True),
    ("type .env.local", True),
    ("Get-Content _secrets/key.txt", True),
    ("ls && cat ~/.ssh/id_ed25519", True),
    ("tail -n 5 apps/api/.env", True),
    ("grep TOKEN .env", True),
    ("cat .claude/settings.local.json", True),
    ("printenv", True),
    ("Get-ChildItem env:", True),
    ("docker exec api env", True),
    ("docker inspect api", True),
    ("docker compose config", True),
    ("ssh host 'cat /srv/app/.env'", True),
    ("cat .e*", True),
    ("cat ?env", True),
    ("type _sec*/key.txt", True),
    ("cat .en\\v", True),
    ("ls *.md", False),
    ('cat ".e"nv', True),
    ("python - < .env", True),
    ("cat .env.example", False),
    ("cat ~/.ssh/id_ed25519.pub", False),
    ("grep -n environment src/settings.py", False),
    ("docker inspect api --format '{{.State.Status}}'", False),
    ("docker compose config -q", False),
    ("cat > _temp/x.py <<'EOF'\nprint('.env')\nEOF", False),
    ("env | grep TOKEN", True),
    ("echo $HOME", False),
    ("python -c \"import os; print(os.environ.get('X'))\"", False),
]

# (command, deny without approval, deny with a fresh push+release approval)
GIT_ALWAYS = [
    ("git status", False, False),
    ("git log --oneline -5", False, False),
    ('git commit -m "feat(api): add AI scoring"', False, False),
    ('git add CLAUDE.md .claude/hooks && git commit -m "docs: thin rules"', False, False),
    ('git commit -m "chore: x" -m "Co-Authored-By: someone <a@b>"', True, True),
    ('git commit -m "chore(tooling): tune claude hooks"', True, True),
    ("git commit -m \"$(cat <<'EOF'\nfix: x\n\nGenerated with a tool\nEOF\n)\"", True, True),
    ('gh pr create --title "feat: x" --body "Generated with Claude Code"', True, True),
    ('echo "$CLAUDE_PROJECT_DIR" && git commit -m "fix: path"', False, False),
    ("git push --force origin main", True, True),
    ("git push -uf origin main", True, True),
    ("git push origin +main:main", True, True),
    ("git push --force-with-lease", True, True),
    ("git commit --no-verify -m 'fix: x'", True, True),
    ("git reset --hard origin/main", True, True),
    ("git reset --hard upstream/dev", True, True),
    ("git reset --hard HEAD~1", False, False),
    ("git clean -fd", True, True),
    ("git checkout -- .", True, True),
    ("git restore .", True, True),
    ("git restore --staged .", False, False),
    ("git restore src/a.py", False, False),
    ("rm -f x && git push origin main", True, False),
    ("git push origin main", True, False),
    ("git -C sub -c core.x=y push", True, False),
    ("cd sub; git push", True, False),
    ("git push origin v1.2.3", True, False),
    ("git push --tags", True, False),
    ("git push origin refs/tags/v1.0.0", True, False),
    ("git commit -nm 'fix: x'", True, True),
    ("git -c core.hooksPath=/dev/null commit -m 'fix: x'", True, True),
    ("git push --mirror", True, True),
    ("git push origin --delete main", True, True),
    ("git push origin :main", True, True),
    ("git reset --hard FETCH_HEAD", True, True),
    ("git push -n origin main", True, False),
    ('bash -c "git push --force origin main"', True, True),
    ("pwsh -Command 'git push origin main'", True, False),
    ("(git push origin main)", True, False),
    ("timeout 30 git push origin main", True, False),
    ("nice -n 5 git push origin main", True, False),
    ("git push origin 'refs/*:refs/*'", True, False),
    ("echo ok > .claude/.approve-push", True, True),
    ("touch .claude/.approve-release", True, True),
    ("python -c \"open('.claude/.approve-push','w')\"", True, True),
    ("echo x > \".claude/.app\"\"rove-push\"", True, True),
    ("python scripts/approve.py push", False, False),
    ("bash -lc 'git push origin main'", True, False),
    ("powershell -enc ZwBpAHQAIABwAHUAcwBoACAALQBmAA==", True, True),
    ("git push origin main \\; echo", True, False),
    ("git -c commit.gpgsign=no commit -m 'fix: x'", True, True),
    ("git --config-env=core.hooksPath=X commit -m 'fix: x'", True, True),
    ("GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x git commit -m 'f: x'", True, True),
    ("git -c push.followTags=yes push origin main", True, False),
    ("git commit -m x --no-verify", True, True),
    ('git commit -m "fix: -n flag parsing"', False, False),
    ('grep -rn "git push --force" docs/', False, False),
    ('git commit -m "docs: never git push --force"', False, False),
]

TEAM_ONLY = [
    ("gh pr merge 12 --squash", True, True),
    ("gh pr --repo o/n merge 12", True, True),
    ("gh pr ready 12", True, True),
    ('gh pr comment 12 --body "ready to merge"', False, False),
    ("gh issue close 5", True, False),
]


def write_config(project, profile):
    cfg = {"template": {"profile": profile}}
    if profile == "team":
        cfg["git"] = {"protected_branches": ["main", "develop"]}
        cfg["approval"] = {"consume": False}
    os.makedirs(os.path.join(project, ".claude"), exist_ok=True)
    with open(os.path.join(project, ".claude", "project.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def approve(project, heads=None):
    for action in ("push", "release"):
        with open(os.path.join(project, ".claude", f".approve-{action}"), "w", encoding="utf-8") as f:
            json.dump({"created": int(time.time()), "heads": heads or {}}, f)


def clear(project):
    for action in ("push", "release"):
        try:
            os.remove(os.path.join(project, ".claude", f".approve-{action}"))
        except OSError:
            pass


def run(hook, payload, project):
    proc = subprocess.run(
        [sys.executable, os.path.join(HOOKS, hook)],
        input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "CLAUDE_PROJECT_DIR": project},
    )
    return proc.returncode == 2, proc.stdout


def git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def main():
    verbose = "-v" in sys.argv
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    bad, total = [], 0

    def expect(label, hook, cmd, project, must_deny, cwd=None):
        nonlocal total
        if not os.path.exists(os.path.join(HOOKS, hook)):
            return  # not part of this project's profile (guard-branch is team-only)
        total += 1
        denied, _out = run(hook, {"tool_input": {"command": cmd} if hook != "guard-branch.py"
                                 else {"file_path": cmd}, "cwd": cwd or project}, project)
        if denied != must_deny:
            bad.append(f"  FAIL [{label}] {hook}: expected {'deny' if must_deny else 'allow'}: {cmd!r}")
        elif verbose:
            print(f"  ok   [{label}] {cmd!r}")

    for profile in ("solo", "team"):
        with tempfile.TemporaryDirectory() as project:
            write_config(project, profile)
            for cmd, must in SECRETS:
                expect(profile, "guard-secrets.py", cmd, project, must)
            cases = GIT_ALWAYS + (TEAM_ONLY if profile == "team" else [])
            for cmd, plain, approved in cases:
                clear(project)
                expect(f"{profile}", "guard-git.py", cmd, project, plain)
                approve(project)
                expect(f"{profile}+approved", "guard-git.py", cmd, project, approved)
            clear(project)
            if profile == "solo":
                # Bare "AI" is an opt-in extra word, not a default: AI can be a project's subject.
                with open(os.path.join(project, ".claude", "project.json"), "w", encoding="utf-8") as f:
                    json.dump({"attribution": {"extra_words": ["AI"]}}, f)
                expect("solo+AI", "guard-git.py", 'git commit -m "feat: add AI scoring"', project, True)

    # A real repo: approvals bound to HEAD, one-shot consumption, protected branches.
    with tempfile.TemporaryDirectory() as project:
        write_config(project, "solo")
        git(project, "init", "-q", "-b", "main")
        git(project, "commit", "-q", "--allow-empty", "-m", "init")
        head = subprocess.run(["git", "-C", project, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        approve(project, {".": head})
        expect("solo+bound", "guard-git.py", "git push origin main", project, False)
        expect("solo+consumed", "guard-git.py", "git push origin main", project, True)
        approve(project, {".": head})
        git(project, "commit", "-q", "--allow-empty", "-m", "after approval")
        expect("solo+stale", "guard-git.py", "git push origin main", project, True)

        write_config(project, "team")
        target = os.path.join(project, "src", "a.py")
        expect("team+main", "guard-branch.py", target, project, True)
        expect("team+main", "guard-git.py", "echo x > src/a.py", project, True)
        expect("team+main", "guard-git.py", "sed -i 's/a/b/' src/a.py", project, True)
        expect("team+main", "guard-git.py", "git checkout develop -- src/a.py", project, True)
        expect("team+main", "guard-git.py", 'git commit -m "use > instead"', project, False)
        expect("team+main", "guard-git.py", "echo x > $TMP/a.md", project, False)
        expect("team+main", "guard-git.py", "cp _temp/a.py src/a.py", project, True)
        expect("team+main", "guard-git.py", "rm src/a.py", project, True)
        expect("team+main", "guard-git.py", "cat src/a.py", project, False)
        git(project, "switch", "-q", "-c", "feature/1-x")
        expect("team+branch", "guard-branch.py", target, project, False)
        expect("team+branch", "guard-git.py", "echo x > src/a.py", project, False)

    print("\n".join(bad))
    print(f"  {total - len(bad)}/{total} hook cases ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
