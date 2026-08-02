from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIP_SOURCE = REPO_ROOT / "Soil Source" / "Drip.FOR"
WATER_MOVER_SOURCE = REPO_ROOT / "Soil Source" / "Watmov.for"


def _source(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def _compact(text):
    return re.sub(r"[\s!&]+", "", text.lower())


def test_mode6_uses_center_active_boundary_without_local_fallback():
    drip = _compact(_source(DRIP_SOURCE))

    assert "sourcedemandflux=sourcerate*dripsourcewidth(jj)" in drip
    assert "sourceflux=sourcedemandflux*pressurefactor" in drip
    assert "dripmode6centerbnd(mode6source)=centerbnd" in drip
    assert "desiredradius=min(wetradius(jj,in),maxradius)" in drip
    assert "dripmode6headactive(dripsurfbnd(k))=1" in drip
    assert "dripmode6fluxactive(dripsurfbnd(k))=1" in drip
    assert "dripmode6assignedflux(dripsurfbnd(k))=" in drip
    assert "dripmode6boundaryowner(dripsurfbnd(k))=mode6source" in drip
    assert "if(sourceflux.gt.releasecap)then" not in drip
    assert "dripmode6rateactive" not in drip


def test_mode6_positive_head_flux_nodes_switch_to_zero_head():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "hnew(n).gt.mode6headtol" in water_mover
    assert "mode6assigned-dmax1(dble(qact(n)),0.0d0).gt." not in water_mover
    assert "dripmode6fluxactive(k)=0" in water_mover
    assert "dripmode6headactive(k)=1" in water_mover
    assert "hnew(n)=0.0" in water_mover


def test_mode6_uses_hydrus_positive_head_trigger_without_flux_cap():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "hnew(n).gt.mode6headtol" in water_mover
    assert "dripmode6acceptedflux(mode6source).gt." in water_mover
    assert "dripmode6inputflux(mode6source)+mode6fluxtol" in water_mover
    assert "dripmode6boundedflux" not in water_mover
    assert "mode6fluxlimit" not in water_mover
    assert "mode6headpresent" not in water_mover
    assert (
        "mode6boundaryactual(k)=dble(qact(n)-baseq(n)-qautoirrig(n))"
        in water_mover
    )
    assert "mode6needresolve=1" in water_mover


def test_mode6_solves_signed_source_closure_with_a_safeguarded_bracket():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert (
        "mode6term=mode6accepted(mode6source)+"
        "mode6fluxcurrent(mode6source)-"
        "dripmode6inputflux(mode6source)"
    ) in water_mover
    assert "if(mode6term.lt.0.0d0)then" in water_mover
    assert "mode6sourcebracketlow(mode6source)=" in water_mover
    assert "mode6sourcebrackethigh(mode6source)=" in water_mover
    assert (
        "mode6actual=0.5d0*(mode6sourcebracketlow(mode6source)+"
        "mode6sourcebrackethigh(mode6source))"
    ) in water_mover
    assert (
        "mode6actual=dmax1(dripmode6inputflux(mode6source)-"
        "mode6accepted(mode6source),0.0d0)"
    ) in water_mover
    assert "dripshare=mode6actual*dble(width(k))/" in water_mover


def test_mode6_nonconvergence_restarts_mode6_on_a_smaller_time_step():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "mode6solvermaxit=max(maxit,200)" in water_mover
    assert "mode6retrycount=mode6retrycount+1" in water_mover
    assert "hnew(i)=basehold(i)" in water_mover
    assert "dripmode6fluxactive(mode6bnd)=1" in water_mover
    assert "dt=dmax1(dt/3.0d0,dtmin)" in water_mover
    assert "mode6failedtoconvergeatminimumwaterstep" in water_mover
    nonconvergence = water_mover[
        water_mover.index("if(.not.itcrit)then"):
        water_mover.index("cendofiterationloops")
    ]
    assert "goto619" not in nonconvergence


def test_mode6_boundary_exhaustion_is_reported_without_iteration_masking():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "mode6limitedclosure=1" in water_mover
    assert "dripmode6boundarylimit_sum=dripmode6boundarylimit_sum+dt" in water_mover
    assert "iter=min(iter,3)" not in water_mover
    assert "dripmode6remaining_flux=dripmode6remaining_flux+" in water_mover


def test_mode6_remaining_flux_expands_to_neighboring_surface_ring():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "mode6newleft=dripmode6centerpos(mode6source)-" in water_mover
    assert "mode6newright=dripmode6centerpos(mode6source)+" in water_mover
    assert "dripmode6currentradius(mode6source)=mode6radius" in water_mover
    assert "dripmode6assignedflux(mode6bnd)=" in water_mover
    assert "dble(width(mode6bnd))/mode6newmeasure" in water_mover
    assert "dripmode6assignedflux(mode6bnd)=mode6store" not in water_mover
    assert "dripmode6boundedflux" not in water_mover


def test_mode6_uses_full_surface_and_routes_only_domain_residual_to_runoff():
    drip = _compact(_source(DRIP_SOURCE))
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    full_surface_pos = drip.index(
        "if(dripspreadmode(jj).eq.6)then",
        drip.index("edgemaxradius=max("),
    )
    assert drip.index("maxradius=edgemaxradius", full_surface_pos) > full_surface_pos
    assert "mode6radius.lt.dripmode6maxradius(mode6source)" in water_mover
    assert "dripmode6remainingflux(mode6source).gt.mode6fluxtol" in water_mover
    assert "dripsurfacerunoff_flux=dripsurfacerunoff_flux+" in water_mover
    mode6_closure = water_mover[
        water_mover.index("dripmode6remaining_flux=dripmode6remaining_flux+"):
        water_mover.index("domode6source=1,dripmode6count", water_mover.index("dripmode6remaining_flux=dripmode6remaining_flux+") + 1)
    ]
    assert "dripsurfacestorage" not in mode6_closure


def test_mode6_pressure_correction_feeds_active_boundary_supply():
    drip = _compact(_source(DRIP_SOURCE))

    pressure_pos = drip.index("pressurefactor=amax1(0.0,amin1(1.0,pressurefactor))")
    mode6_pos = drip.index("dripmode6inputflux(mode6source)=dble(sourceflux)")
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


def test_mode6_overaccept_handling_matches_exact_neumann_frontier():
    water_mover_source = _source(WATER_MOVER_SOURCE)
    water_mover = _compact(water_mover_source)

    assert "elseif(dripmode6fluxactive(k).eq.1)then" in water_mover
    assert "codew(i)=-4" in water_mover
    assert (
        "q(i)=q(i)+sngl(mode6continuation*"
        "dripmode6assignedflux(k))"
    ) in water_mover

    overaccept_start = water_mover.index("if(mode6overaccepted.eq.1)then")
    overaccept_end = water_mover.index("else", overaccept_start)
    overaccept = water_mover[overaccept_start:overaccept_end]
    assert "dripmode6assignedflux(k)=dmax1" not in overaccept
    assert "callresetmode6waterstep(basehold,hold,htemp)" in overaccept
    assert "dt=dmax1(dt/3.0d0,dtmin)" in overaccept

    assert "common source pressure head" not in water_mover_source.lower()
