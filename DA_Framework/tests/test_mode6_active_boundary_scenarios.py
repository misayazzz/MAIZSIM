from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIP_SOURCE = REPO_ROOT / "Soil Source" / "Drip.FOR"
WATER_MOVER_SOURCE = REPO_ROOT / "Soil Source" / "Watmov.for"


def _source(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def _compact(text):
    return re.sub(r"[\s!&]+", "", text.lower())


def test_mode6_uses_center_active_boundary_or_local_high_flow_fallback():
    drip = _compact(_source(DRIP_SOURCE))

    assert "sourcedemandflux=sourcerate*dripsourcewidth(jj)" in drip
    assert "sourceflux=sourcedemandflux*pressurefactor" in drip
    assert "dripmode6centerbnd(mode6source)=centerbnd" in drip
    assert "desiredradius=0" in drip
    assert "mode6left=centerpos" in drip
    assert "mode6right=centerpos" in drip
    assert "if(sourceflux.gt.releasecap)then" in drip
    assert "dripmode6rateactive(dripsurfbnd(k))=1" in drip
    assert "dripmode6fluxactive(dripsurfbnd(k))=1" in drip
    assert "dripmode6assignedflux(dripsurfbnd(k))" in drip


def test_mode6_positive_head_flux_nodes_switch_to_zero_head():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "hnew(n).gt.sngl(mode6tol)" in water_mover
    assert "mode6assigned-dmax1(dble(qact(n)),0.0d0).gt." not in water_mover
    assert "dripmode6fluxactive(k)=0" in water_mover
    assert "dripmode6headactive(k)=1" in water_mover
    assert "hnew(n)=0.0" in water_mover


def test_mode6_uses_hydrus_positive_head_trigger_without_flux_cap():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "dripmode6boundedflux(i).ne.1" in water_mover
    assert "hnew(n).gt.sngl(mode6tol)" in water_mover
    assert "mode6actual.gt.mode6assigned+mode6tol" in water_mover
    assert "dripmode6boundedflux(k)=1" in water_mover
    assert "mode6fluxlimit" not in water_mover
    assert "mode6headpresent" not in water_mover
    assert "dripmode6fluxactive(i).ne.1" in water_mover
    assert "mode6needresolve=1" in water_mover


def test_mode6_remaining_flux_expands_to_neighboring_surface_ring():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "mode6newleft=dripmode6centerpos(mode6source)-" in water_mover
    assert "mode6newright=dripmode6centerpos(mode6source)+" in water_mover
    assert "dripmode6currentradius(mode6source)=mode6radius" in water_mover
    assert "dripmode6assignedflux(mode6bnd)=" in water_mover
    assert "dble(width(mode6bnd))/mode6newmeasure" in water_mover
    assert "dripmode6assignedflux(mode6bnd)=mode6store" in water_mover
    assert "dripmode6boundedflux(mode6bnd)=1" in water_mover


def test_mode6_wet_width_limit_routes_unaccepted_water_to_storage_or_runoff():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "mode6radius.lt.dripmode6maxradius(mode6source)" in water_mover
    assert "dripmode6remainingflux(mode6source).gt.mode6tol" in water_mover
    assert "dripsurfacestorage(k)=dripsurfacestorage(k)+" in water_mover
    assert "dripsurfacerunoff_flux=dripsurfacerunoff_flux+" in water_mover


def test_mode6_pressure_correction_feeds_active_boundary_supply():
    drip = _compact(_source(DRIP_SOURCE))

    pressure_pos = drip.index("pressurefactor=amax1(0.0,amin1(1.0,pressurefactor))")
    mode6_pos = drip.index("if(dripspreadmode(jj).eq.6)then")
    assert pressure_pos < mode6_pos
    assert "dripmode6inputflux(mode6source)=dble(sourceflux)" in drip
    assert "dripmode6pressurelossflux(mode6source)" in drip


def test_mode6_axisymmetric_candidates_use_surface_boundary_measure():
    drip = _compact(_source(DRIP_SOURCE))
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "if(kat.eq.1)then" in drip
    assert "segmentleft=0.0" in drip
    assert "dripmode6candidateowner(dripsurfbnd(k))=mode6source" in drip
    assert "dble(width(mode6bnd))" in water_mover
