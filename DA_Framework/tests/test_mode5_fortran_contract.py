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


def test_mode5_surface_storage_uses_covered_measure():
    include = _compact(_source(SURFACE_INCLUDE))
    drip = _compact(_source(DRIP_SOURCE))
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "dripcoveredmeasure(numbpd)" in include
    assert "dripcoveredmeasure(dripsurfbnd(k))" in drip
    assert "dripstoragemeasure=dripcoveredmeasure(k)" in water_mover
    assert "dripstoragelimit=dripstoragemeasure*dble(criticalh)" in water_mover


def test_mode5_dynamic_surface_source_contract():
    source = _compact(_source(DRIP_SOURCE))

    assert "dripspreadmode(i).ne.0.and." in source
    assert "dripspreadmode(jj).eq.4" not in source
    assert "dripspreadmode(i).ne.5.and." in source
    assert "dripspreadmode(i).ne.6)then" in source
    assert "driptargetwidth" not in source
    assert "dripcurvehour" not in source
    assert "sourcedemandflux=sourcerate*dripsourcewidth(jj)" in source
    assert "if(dripspreadmode(jj).eq.5.and.step.gt.0.0d0)then" in source
    assert "if(dripspreadmode(jj).eq.5)maxradius=edgemaxradius" in source
    assert "dripwetwidthmaxlimits" in source


def test_g05_outputs_drip_closure_residual_columns():
    output = _source(OUTPUT_SOURCE)

    assert "DripBoundaryInClosure," in output
    assert "DripBoundaryAccClosure," in output
    assert "DripDemand_Flux-" in output
    assert "DripInput_Flux-" in output


def test_main_loop_keeps_drip_crop_coupling_explicit():
    source = _compact(_source(MAIN_SOURCE))

    drip_pos = source.index("calldrip()")
    crop_pos = source.index("callcrop(")
    uptake_pos = source.index("callwateruptake()")
    mover_pos = source.index("callwatermover()")
    assert drip_pos < crop_pos < uptake_pos < mover_pos
