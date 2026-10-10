from pipeline.health import SourceHealth, alerts


def test_alerts_open_after_three_failures_and_close_on_recovery() -> None:
    health = {
        "pt-apa": SourceHealth(last_error="down", consecutive_failures=3),
        "bg-moew": SourceHealth(last_error="down", consecutive_failures=2),
        "es-miteco": SourceHealth(last_success="2026-10-10T06:00:00+00:00"),
    }
    failing, healthy = alerts(health, threshold=3)
    assert failing == {"pt-apa": "down"}
    assert healthy == ["es-miteco"]
