from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIP_SOURCE = REPO_ROOT / "Soil Source" / "Drip.FOR"
WATER_MOVER_SOURCE = REPO_ROOT / "Soil Source" / "Watmov.for"
OUTPUT_SOURCE = REPO_ROOT / "Soil Source" / "OUTPUT.FOR"
SURFACE_INCLUDE = REPO_ROOT / "Soil Source" / "PuSurface.ins"
MAIN_SOURCE = REPO_ROOT / "Soil Source" / "2DMAIZSIM.FOR"


def _source(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def _compact(text):
    return re.sub(r"\s+", "", text.lower())


def test_mode4_axis_branch_is_limited_to_kat1():
    source = _compact(_source(DRIP_SOURCE))

    assert "(dripspreadmode(jj).eq.4.or.!dripspreadmode(jj).eq.5).and.kat.eq.1.and." in source
    assert "if(abs(x(sourcenode)).le.driptol)" not in source


def test_mode4_demand_uses_covered_measure_contract():
    source = _compact(_source(DRIP_SOURCE))

    assert "if(dripspreadmode(jj).eq.4)thensourcedemandflux=sourcerate*totalmeasure" in source
    assert "elseif(dripsourcewidth(jj).gt.0.0)thensourcedemandflux=sourcerate*dripsourcewidth(jj)" in source


def test_mode4_surface_storage_uses_covered_measure():
    include = _compact(_source(SURFACE_INCLUDE))
    drip = _compact(_source(DRIP_SOURCE))
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "dripcoveredmeasure(numbpd)" in include
    assert "dripcoveredmeasure(dripsurfbnd(k))" in drip
    assert "dripstoragemeasure=dripcoveredmeasure(k)" in water_mover
    assert "dripstoragelimit=dripstoragemeasure*dble(criticalh)" in water_mover


def test_mode5_dynamic_surface_source_contract():
    source = _compact(_source(DRIP_SOURCE))

    assert "dripspreadmode(i).lt.0.or.dripspreadmode(i).gt.5" in source
    assert "elseif(dripspreadmode(jj).eq.5)then" in source
    assert "sourcedemandflux=sourcerate*dripsourcewidth(jj)" in source
    assert "dripspreadmode(jj).eq.5).and.step.gt.0.0d0" in source
    assert "if(dripspreadmode(jj).eq.5)maxradius=edgemaxradius" in source
    assert "dripwetwidthmaxlimits" in source


def test_g05_outputs_mode4_closure_residual_columns():
    output = _source(OUTPUT_SOURCE)

    assert "DripBoundaryInClosure," in output
    assert "DripBoundaryAccClosure," in output
    assert "DripDemand_Flux-" in output
    assert "DripInput_Flux-" in output


def test_main_loop_keeps_mode4_crop_coupling_explicit():
    source = _compact(_source(MAIN_SOURCE))

    drip_pos = source.index("calldrip()")
    crop_pos = source.index("callcrop(")
    uptake_pos = source.index("callwateruptake()")
    mover_pos = source.index("callwatermover()")
    assert drip_pos < crop_pos < uptake_pos < mover_pos
