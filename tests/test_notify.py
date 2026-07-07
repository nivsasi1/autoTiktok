from types import SimpleNamespace

import config
import notify


def enable(monkeypatch):
    monkeypatch.setattr(config, "NOTIFY_EMAIL_TO", "me@example.com")
    monkeypatch.setattr(config, "NOTIFY_SMTP_USER", "bot@gmail.com")
    monkeypatch.setattr(config, "NOTIFY_SMTP_PASSWORD", "apppass")


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        self.creds = (user, password)

    def send_message(self, msg):
        FakeSMTP.sent.append((self.creds, msg))


def test_disabled_without_config(monkeypatch):
    monkeypatch.setattr(config, "NOTIFY_EMAIL_TO", "")
    monkeypatch.setattr(
        notify.smtplib, "SMTP",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("connected")))
    assert notify.send_failure("s", "b") is False


def test_sends_over_starttls_with_prefixed_subject(monkeypatch):
    enable(monkeypatch)
    FakeSMTP.sent = []
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    assert notify.send_failure("upload failed", "the reason") is True
    (creds, msg), = FakeSMTP.sent
    assert creds == ("bot@gmail.com", "apppass")
    assert msg["Subject"] == "[autoTiktok] upload failed"
    assert msg["To"] == "me@example.com"
    assert "the reason" in msg.get_content()


def test_smtp_errors_never_raise(monkeypatch, capsys):
    enable(monkeypatch)

    def boom(*a, **kw):
        raise OSError("smtp down")

    monkeypatch.setattr(notify.smtplib, "SMTP", boom)
    assert notify.send_failure("s", "b") is False
    assert "failure email not sent" in capsys.readouterr().out
