import polars as pl

from pipeline.registry import load_rbds, load_registry

# Reservoirs we could not place from official inventories; they still count in
# aggregates but have no map point.
KNOWN_UNLOCATED = {"ES-la-cabezuela"}


def test_every_spanish_reservoir_has_a_known_river_basin_district() -> None:
    reg = load_registry("ES")
    rbds = set(load_rbds()["code"].to_list())
    assert reg["rbd_code"].is_in(rbds).all()


def test_spanish_reservoirs_have_coordinates_inside_spain() -> None:
    reg = load_registry("ES").filter(~pl.col("id").is_in(KNOWN_UNLOCATED))
    lat = reg["lat"].cast(pl.Float64)
    lon = reg["lon"].cast(pl.Float64)
    assert lat.is_not_null().all() and lon.is_not_null().all()
    assert lat.is_between(35.8, 43.9).all()
    assert lon.is_between(-9.4, 3.4).all()


PT_UNLOCATED = {"PT-monte-gato", "PT-monte-migueis", "PT-santa-agueda"}


def test_portuguese_reservoirs_have_a_district_and_coordinates_inside_portugal() -> None:
    reg = load_registry("PT")
    rbds = set(load_rbds()["code"].to_list())
    assert reg["rbd_code"].is_in(rbds).all()
    located = reg.filter(~pl.col("id").is_in(PT_UNLOCATED))
    lat = located["lat"].cast(pl.Float64)
    lon = located["lon"].cast(pl.Float64)
    assert lat.is_between(36.9, 42.2).all()
    assert lon.is_between(-9.6, -6.1).all()


def test_czech_reservoirs_have_districts_and_located_ones_are_in_czechia() -> None:
    reg = load_registry("CZ")
    rbds = set(load_rbds()["code"].to_list())
    assert reg["rbd_code"].is_in(rbds).all()
    located = reg.filter(pl.col("lat") != "")
    assert located.height >= 90
    assert located["lat"].cast(pl.Float64).is_between(48.5, 51.1).all()
    assert located["lon"].cast(pl.Float64).is_between(12.0, 18.9).all()
    # Assigned by geography, not by enterprise: Bedřichov (Povodí Labe) drains to the Oder.
    assert reg.filter(pl.col("source_key") == "bedrichov")["rbd_code"].item() == "CZ6000"


def test_cypriot_dams_are_located_in_cyprus() -> None:
    reg = load_registry("CY")
    assert reg.height == 21
    assert (reg["rbd_code"] == "CY001").all()
    assert reg["lat"].cast(pl.Float64).is_between(34.5, 35.7).all()
    assert reg["lon"].cast(pl.Float64).is_between(32.2, 34.6).all()


def test_bulgarian_reservoirs_are_located_in_bulgaria() -> None:
    reg = load_registry("BG")
    rbds = set(load_rbds()["code"].to_list())
    assert reg["rbd_code"].is_in(rbds).all()
    assert reg["lat"].cast(pl.Float64).is_between(41.2, 44.3).all()
    assert reg["lon"].cast(pl.Float64).is_between(22.3, 28.7).all()


def test_uk_reservoirs_belong_to_a_known_source_and_lie_in_great_britain() -> None:
    from pipeline.cli import ADAPTERS

    reg = load_registry("UK")
    sources = {a.meta.id for a in ADAPTERS if a.meta.country == "UK"}
    assert set(reg["source_id"].unique()) <= sources
    assert reg["id"].is_unique().all()
    assert reg.select("source_id", "source_key").is_unique().all()
    assert reg["rbd_code"].is_in(set(load_rbds()["code"].to_list())).all()
    assert reg["lat"].cast(pl.Float64).is_between(49.8, 60.9).all()
    assert reg["lon"].cast(pl.Float64).is_between(-8.2, 1.8).all()
