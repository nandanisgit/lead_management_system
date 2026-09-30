import httpx
import respx
from typer.testing import CliRunner

from lead_capture.cli import app
from lead_capture.settings import get_settings

runner = CliRunner()


def test_sync_lists_dry_run_prints_lists():
    result = runner.invoke(app, ["sync-lists", "--dry-run"])
    assert result.exit_code == 0 and "Board: CBSE" in result.output


def test_check_sheet_reports_missing_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", str(tmp_path / "missing.json"))
    result = runner.invoke(app, ["check-sheet"])
    assert result.exit_code == 1 and "sheet check failed" in result.output

    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    result = runner.invoke(app, ["check-sheet"])
    assert result.exit_code == 1 and "not configured" in result.output


def test_replay_requires_app_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("WA_APP_SECRET", "")
    f = tmp_path / "p.json"
    f.write_text("{}")
    result = runner.invoke(app, ["replay", str(f)])
    assert result.exit_code == 1


def _telegram_env(monkeypatch):
    monkeypatch.setenv("LC__CHANNEL__PROVIDER", "telegram")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:T")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cret")
    get_settings.cache_clear()


@respx.mock
def test_set_webhook_registers_telegram(monkeypatch):
    _telegram_env(monkeypatch)
    route = respx.post("https://api.telegram.org/bot123:T/setWebhook").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": True})
    )
    result = runner.invoke(app, ["set-webhook", "https://abc.trycloudflare.com"])
    get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert "https://abc.trycloudflare.com/webhooks/telegram" in result.output
    assert route.called


def test_set_webhook_needs_https(monkeypatch):
    _telegram_env(monkeypatch)
    result = runner.invoke(app, ["set-webhook", "http://localhost:8000"])
    get_settings.cache_clear()
    assert result.exit_code == 1 and "https" in result.output


def test_set_webhook_for_whatsapp_points_to_dashboard(monkeypatch):
    monkeypatch.setenv("LC__CHANNEL__PROVIDER", "whatsapp_cloud")
    get_settings.cache_clear()
    result = runner.invoke(app, ["set-webhook", "https://abc.trycloudflare.com"])
    get_settings.cache_clear()
    assert result.exit_code == 1 and "/webhooks/whatsapp" in result.output
