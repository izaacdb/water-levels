# Registry build scripts

One-off scripts that build the curated registries from official sources. Re-run them when a source publishes a new inventory.

| Script | Inputs | Writes |
|---|---|---|
| `build_rbd_geo.py` | `registry/rbd-source.geojson`: the EEA WISE WFD 2022 river basin districts (CC BY 4.0), queried from `water.discomap.eea.europa.eu/.../WFD2022_RiverBasinDistrict_WM/MapServer/0` for our countries with `outSR=4326&maxAllowableOffset=0.01&f=geojson` | `registry/rbd.csv`, `web/public/geo/rbd.geojson` |
| `enrich_es_registry.py` | The MITECO *Inventario de Embalses* shapefile (`egis_embalse_geoetrs89.zip` from miteco.gob.es "Acceso rápido a los datos"), plus the bulletin CSV exported with `mdb-export -T '%Y-%m-%d'` | `rbd_code`, `lat` and `lon` in `registry/es.csv`. Hand fixes live in `registry/es_overrides.csv` |
| `fetch_rbd_source.py` | EEA WISE river basin districts for given codes and layer (`WFD2016` for the UK, which isn't in the 2022 cycle; `WFD2022` otherwise). Geometries are repaired and simplified locally | adds them to `registry/rbd-source.geojson`; then run `build_rbd_geo.py` |
| `build_uk_registry.py` | Each Stream company's own datasets (names, latest coordinates), plus `web/public/geo/rbd.geojson` for point-in-polygon districts. Hand fixes in `registry/uk_overrides.csv` | that company's rows in `registry/uk.csv` |
