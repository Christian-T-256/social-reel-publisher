from reel_publisher.cli import main


def test_cli_dry_run_needs_no_config_or_credentials(capsys):
    assert main(["--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "DRY RUN: mocked happy path" in output
    assert "DRY RUN: mocked wrong-account refusal" in output
    assert "PASS no upload call was made" in output
