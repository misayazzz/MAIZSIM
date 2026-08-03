from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIP_SOURCE = REPO_ROOT / "Soil Source" / "Drip.FOR"
WATER_MOVER = REPO_ROOT / "Soil Source" / "Watmov.for"
SURFACE_STATE = REPO_ROOT / "Soil Source" / "PuSurface.ins"
OUTPUT_SOURCE = REPO_ROOT / "Soil Source" / "OUTPUT.FOR"
INPUT_WRITER = (
    REPO_ROOT
    / "示例输入"
    / "ExcelInterface-master"
    / "tools"
    / "maizsim_inputs"
    / "drip.py"
)


def _compact(path):
    return "".join(path.read_text(encoding="utf-8").lower().split())


def test_only_fixed_contact_mode6_drip_contract_remains():
    source = _compact(DRIP_SOURCE)
    mover = _compact(WATER_MOVER)
    writer = _compact(INPUT_WRITER)
    for removed in (
        "mode5",
        "wetradius",
        "currentradius",
        "maxradius",
    ):
        assert removed not in source + mover + writer
    for removed in ("dripspreadmode", "dripwetwidthmax", "dripsourcewidth"):
        assert removed not in source + mover
    assert "dripmode6active" in source
    assert "dripmode6contactmeasure" in source
    assert "dripmode6contactmeasure" in mover


def test_input_is_physical_flow_spacing_contact_and_x_zero():
    source = _compact(DRIP_SOURCE)
    writer = _compact(INPUT_WRITER)

    assert "emitterflowlph" in source
    assert "emitterspacingcm" in source
    assert "contactwidthcm" in source
    assert "fieldcount=dripfieldcount(eventline)" in source
    assert "if(fieldcount.ne.8)then" in source
    assert "half_line_factor=0.5d0*24.0d0*litre_to_cm3" in source
    assert "externalflux=dble(emitterflowlph(i))*half_line_factor/" in source
    assert "if(abs(x(nappl(i))).gt.driptol)" in source
    assert "equivalentdriplinemustbelocatedatx=0" in source
    assert "emitterflowlph" in writer
    assert "emitterspacingcm" in writer
    assert "contactwidthcm" in writer


def test_contact_interval_is_discretized_once_with_partial_edge_measure():
    source = _compact(DRIP_SOURCE)

    assert "coverright=amin1(segmentright,contactwidthcm(1))" in source
    assert "coverwidth=amax1(0.0,coverright-coverleft)" in source
    assert "localmeasure=width(dripsurfbnd(k))*coverwidth/segmentwidth" in source
    assert "dripmode6contacttotal=dripmode6contacttotal+" in source
    assert "dble(localmeasure)" in source
    assert "dripmode6assignedflux(k)=solversupply*" in source
    assert "dripmode6contactmeasure(k)/dripmode6contacttotal" in source


def test_mode6_newton_and_active_flux_head_switch_are_retained():
    mover = _compact(WATER_MOVER)

    assert "callsolvemode6fixedactivesetnewton" in mover
    assert "if(hnew(n).gt.mode6headtol)then" in mover
    assert "dripmode6fluxactive(k)=0" in mover
    assert "dripmode6headactive(k)=1" in mover
    assert "mode6term=mode6accepted(mode6source)+" in mover
    assert "mode6sourcebracketlow(mode6source)=" in mover
    assert "mode6sourcebrackethigh(mode6source)=" in mover
    assert "mode6actual=0.5d0*(" in mover


def test_no_fallback_skip_or_relaxed_closure_path_exists():
    mover = _compact(WATER_MOVER)
    source = _compact(DRIP_SOURCE)
    combined = mover + source

    assert "fallback" not in combined
    assert "goto1100" in mover
    assert "dt=dmax1(dt/3.0d0,dtmin)" in mover
    assert "stop'mode6failedtoconvergeatminimumwaterstep'" in mover
    assert "mode6massabsolutetolerance=1.0d-6" in mover
    assert "5.0d0*mode6massroundoff+1.0d-4*mode6massscale" in mover
    assert "dripmode6boundarylimit_sum" in mover


def test_local_ponding_and_overflow_close_the_physical_ledger():
    mover = _compact(WATER_MOVER)
    output = _compact(OUTPUT_SOURCE)

    assert "mode6availablevolume=mode6oldstorage+" in mover
    assert "dripmode6externalflux(mode6source)*dt" in mover
    assert "mode6newstorage=mode6availablevolume-mode6acceptedvolume" in mover
    assert "mode6storagecapacity=dripmode6contacttotal*" in mover
    assert "mode6overflowvolume=dmax1(" in mover
    assert "dripstoragechange_flux=dripstoragechange_flux+" in mover
    assert "dripoverflow_flux=dripoverflow_flux+mode6overflowvolume" in mover
    assert "dripledgerclosure=(dripinput_flux-" in output
    assert "dripactualinfil_flux-dripstoragechange_flux-" in output
    assert "dripoverflow_flux" in output


def test_output_exposes_contact_solver_and_physical_ledgers():
    output = OUTPUT_SOURCE.read_text(encoding="utf-8")
    for column in (
        "DripEmitterInput_mm",
        "DripActualInfil_mm",
        "DripPondingChange_mm",
        "DripOverflow_mm",
        "DripPonded_mm",
        "DripLedgerClosure_mm",
        "DripContactWidth_cm",
        "DripContactMeasure_cm",
        "DripMode6Available_mm",
        "DripMode6ClosureResidual",
        "DripMode6SolverLimit",
        "DripMode6BoundaryLimit",
    ):
        assert column in output
