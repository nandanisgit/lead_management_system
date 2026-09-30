from typer.testing import CliRunner

from lead_capture.cli import app

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
