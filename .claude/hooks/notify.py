#!/usr/bin/env python3
# template-managed: core/.claude/hooks/notify.py — edit in _Claude-Template, not here
"""notify — tell the owner when Claude actually needs them. Windows toast and/or Telegram.

Deliberately quiet. It speaks only when the owner has something to do:

  Stop                                      -> the task is finished, your turn
  PreToolUse(AskUserQuestion|ExitPlanMode)  -> Claude is blocked on a question / a plan
  Notification                              -> Claude needs attention (Telegram only)

A notifier that fires on everything gets muted within a day, and then it is worse than none.

Channels: `.claude/project.json` → notify.windows / notify.telegram.
Telegram credentials: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment, else from
`_secrets/hooks.env` (KEY=value per line). Never in settings.local.json — that file is config, it is
loaded and quotable. A variable set-but-empty in the environment means "stay silent" (self-checks).
Telegram messages delete themselves after notify.telegram_delete_after seconds (0 keeps them).

The hook never waits: the toast and the Telegram call run in detached children, because a slow hook
stalls the whole turn. Always exits 0 — a notifier must never fail a turn. Stdlib only.

Manual test:  echo '{"hook_event_name":"Stop","cwd":"."}' | python .claude/hooks/notify.py
"""
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib  # noqa: E402

# Speech to the owner, so it is in the owner's language (see CLAUDE.md → language).
TEXT = {
    "done": ("готово", "Задача закончена, жду тебя."),
    "question": ("вопрос", "Нужен твой ответ."),
    "plan": ("план готов", "Нужно твоё «го»."),
    "attention": ("нужно внимание", "Claude ждёт тебя."),
}

# Built-in PowerShell AppId: always registered, so the toast always shows. A made-up one is dropped.
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
PS_SHOW = (
    "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
    "[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime]>$null;"
    "$x=New-Object Windows.Data.Xml.Dom.XmlDocument;$x.LoadXml($env:CT_TOAST_XML);"
    "$t=New-Object Windows.UI.Notifications.ToastNotification $x;"
    "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:CT_TOAST_APPID).Show($t)"
)
DETACHED = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED_PROCESS | NEW_PROCESS_GROUP | NO_WINDOW


def spawn(args, env=None):
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if os.name == "nt":
        kw["creationflags"] = DETACHED
    else:
        kw["start_new_session"] = True
    try:
        subprocess.Popen(args, env=env, **kw)  # type: ignore[arg-type]
    except Exception:
        pass


def toast(title, body):
    if os.name != "nt":
        return
    xml = ('<toast><visual><binding template="ToastGeneric"><text>%s</text><text>%s</text>'
           '</binding></visual><audio src="ms-winsoundevent:Notification.Default"/></toast>'
           % (escape(title), escape(body)))
    env = dict(os.environ, CT_TOAST_XML=xml, CT_TOAST_APPID=APP_ID)
    spawn(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
           "-WindowStyle", "Hidden", "-Command", PS_SHOW], env)


def secret(name, root):
    if name in os.environ:
        return os.environ[name]
    try:
        with open(os.path.join(root, "_secrets", "hooks.env"), encoding="utf-8") as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep and key.strip() == name and not key.startswith("#"):
                    return value.strip().strip("\"'")
    except OSError:
        pass
    return None


def telegram_api(token, method, params):
    data = urllib.parse.urlencode(params).encode()
    url = "https://api.telegram.org/bot%s/%s" % (token, method)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=8) as r:
            return json.load(r)
    except Exception:
        return None


def telegram_worker(text, delete_after):
    """Runs in the detached child: send, wait, delete."""
    import time
    root = _lib.project_root()
    token, chat = secret("TELEGRAM_BOT_TOKEN", root), secret("TELEGRAM_CHAT_ID", root)
    if not (token and chat):
        return
    resp = telegram_api(token, "sendMessage", {"chat_id": chat, "text": text, "disable_web_page_preview": "true"})
    if delete_after > 0 and resp and resp.get("ok"):
        time.sleep(delete_after)
        telegram_api(token, "deleteMessage", {"chat_id": chat, "message_id": resp["result"]["message_id"]})


def classify(data):
    event = data.get("hook_event_name") or ""
    if event == "Stop":
        return "done", None
    if event == "Notification":
        return "attention", data.get("message")
    if event == "PreToolUse":
        tool = data.get("tool_name") or ""
        ti = _lib.tool_input(data)
        if tool == "AskUserQuestion":
            qs = [q.get("question", "") for q in (ti.get("questions") or []) if isinstance(q, dict)]
            qs = [q for q in qs if q]
            body = (qs[0] + ("  (+%d)" % (len(qs) - 1) if len(qs) > 1 else "")) if qs else None
            return "question", body
        if tool == "ExitPlanMode":
            return "plan", None
    return None, None


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--telegram-worker":
        telegram_worker(sys.argv[2], int(sys.argv[3]))
        return 0
    data = _lib.read_event() or {}
    kind, detail = classify(data)
    if not kind:
        return 0
    cfg = _lib.load_config()
    name = cfg["project"]["name"] or os.path.basename((data.get("cwd") or "").rstrip("/\\")) or "Claude"
    title, body = TEXT[kind]
    body = detail or body
    if cfg["notify"]["windows"] and kind != "attention":
        toast("%s — %s" % (name, title), body)
    if cfg["notify"]["telegram"]:
        spawn([sys.executable, os.path.abspath(__file__), "--telegram-worker",
               "%s — %s\n%s" % (name, title, body), str(int(cfg["notify"]["telegram_delete_after"]))])
    return 0


try:
    sys.exit(main())
except SystemExit:
    raise
except Exception:
    sys.exit(0)
