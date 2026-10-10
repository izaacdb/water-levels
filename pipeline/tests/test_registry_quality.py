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
