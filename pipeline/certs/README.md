# Pinned intermediate certificates

Some official sources serve an incomplete TLS chain. Browsers repair this by fetching the missing intermediate (AIA); Python's `ssl` doesn't. The pipeline trusts certifi's roots plus the intermediates in this folder. Verification stays on: each intermediate must still chain to a certifi root.

| File | Why | Source | Valid until |
|---|---|---|---|
| `AlpiroRSADVSSLCA2.pem` | `www.pvl.cz` (Povodí Vltavy) sends the old "AlpiroSSL RSA DV CA" intermediate for a leaf issued by this one | http://crt.sectigo.com/AlpiroRSADVSSLCA2.crt (SHA-256 `CD:FB:B4:78:…:E4:A2:5D:F5`), issued by Sectigo Public Server Authentication Root R46 | 2035-03-26 |
