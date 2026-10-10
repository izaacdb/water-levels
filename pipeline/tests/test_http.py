import ssl

from pipeline.http import CERTS_DIR, ssl_context


def test_context_trusts_certifi_roots_plus_pinned_intermediates() -> None:
    ctx = ssl_context()
    subjects = {
        dict(field[0] for field in cert["subject"]).get("commonName") for cert in ctx.get_ca_certs()
    }
    assert "Alpiro RSA DV SSL CA 2" in subjects
    assert "Sectigo Public Server Authentication Root R46" in subjects
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname
    assert any(CERTS_DIR.glob("*.pem"))
