"""
Notifikační backend – Discord webhook, Email, ntfy.sh, Windows toast.
Konfigurace v notify_config.json (vytvoří se automaticky).
"""
import json
import os
import smtplib
import requests
from email.mime.text import MIMEText
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "notify_config.json"

DEFAULT_CONFIG = {
    "_comment": "Vyplň platformy které chceš používat, ostatní nech prázdné.",
    "discord": {
        "enabled": False,
        "webhook_url": ""
    },
    "email": {
        "enabled": False,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "",
        "password": "",
        "to": ""
    },
    "ntfy": {
        "enabled": False,
        "topic": "",
        "_help": "Nainstaluj ntfy app, vytvoř si libovolný topic (např. pavel-stocks) a zadej ho sem."
    },
    "windows_toast": {
        "enabled": True
    }
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"[notify] Vytvořen konfigurační soubor: {CONFIG_FILE}")
        print("[notify] Uprav notify_config.json pro zapnutí platforem.")
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_CONFIG


def _send_discord(cfg: dict, title: str, message: str, action: str):
    url = cfg.get("webhook_url", "")
    if not url:
        return
    color = 0x22C55E if action == "BUY" else 0xEF4444 if action == "SELL" else 0x888888
    payload = {
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
            "footer": {"text": "Stock Advisor"},
        }]
    }
    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as e:
        print(f"[notify] Discord chyba: {e}")


def _send_email(cfg: dict, title: str, message: str):
    try:
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = f"[Stock Advisor] {title}"
        msg["From"]    = cfg["username"]
        msg["To"]      = cfg["to"]
        with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as s:
            s.starttls()
            s.login(cfg["username"], cfg["password"])
            s.send_message(msg)
    except Exception as e:
        print(f"[notify] Email chyba: {e}")


def _send_ntfy(cfg: dict, title: str, message: str, action: str):
    topic = cfg.get("topic", "")
    if not topic:
        return
    priority = "high" if action in ("BUY", "SELL") else "default"
    tags = ["chart_with_upwards_trend"] if action == "BUY" else \
           ["chart_with_downwards_trend"] if action == "SELL" else ["bell"]
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode("utf-8"),
            headers={
                "Title":    title,
                "Priority": priority,
                "Tags":     ",".join(tags),
            },
            timeout=8,
        )
    except Exception as e:
        print(f"[notify] ntfy chyba: {e}")


def _send_windows_toast(title: str, message: str):
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Stock Advisor",
            timeout=10,
        )
        return
    except Exception:
        pass
    # Záloha přes PowerShell
    def esc(s):
        return s.replace("'", "`'").replace('"', '`"')
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.Visible = $true; "
        f"$n.ShowBalloonTip(9000, '{esc(title)}', '{esc(message)}', "
        "[System.Windows.Forms.ToolTipIcon]::Info); "
        "Start-Sleep -Seconds 9; $n.Dispose()"
    )
    os.system(f'powershell -WindowStyle Hidden -Command "{ps}"')


def send(title: str, message: str, action: str = "INFO"):
    """Odešle notifikaci na všechny povolené platformy."""
    cfg = load_config()

    if cfg.get("windows_toast", {}).get("enabled", True):
        _send_windows_toast(title, message)

    if cfg.get("discord", {}).get("enabled"):
        _send_discord(cfg["discord"], title, message, action)

    if cfg.get("email", {}).get("enabled"):
        _send_email(cfg["email"], title, message)

    if cfg.get("ntfy", {}).get("enabled"):
        _send_ntfy(cfg["ntfy"], title, message, action)
