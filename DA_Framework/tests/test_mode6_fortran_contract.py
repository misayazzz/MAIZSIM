from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIP_SOURCE = REPO_ROOT / "Soil Source" / "Drip.FOR"
WATER_MOVER_SOURCE = REPO_ROOT / "Soil Source" / "Watmov.for"
OUTPUT_SOURCE = REPO_ROOT / "Soil Source" / "OUTPUT.FOR"
SURFACE_INCLUDE = REPO_ROOT / "Soil Source" / "PuSurface.ins"


def _source(path):
    return path.read_text(encoding="utf-8", errors="ignore")


def _compact(text):
    return re.sub(r"[\s!&]+", "", text.lower())


def test_mode6_public_state_is_shared_with_water_mover():
    include = _compact(_source(SURFACE_INCLUDE))

    assert "common/dripmode6c/" in include
    assert "dripmode6demandflux(maxdripmode6d)" in include
    assert "dripmode6assignedflux(numbpd)" in include
    assert "dripmode6fluxactive(numbpd)" in include
    assert "dripmode6headactive(numbpd)" in include
    assert "dripmode6candidateowner(numbpd)" in include
    assert "dripmode6solverlimit_sum" in include


def test_mode6_input_contract_allows_only_supported_spread_modes():
    drip = _compact(_source(DRIP_SOURCE))

    assert "dripspreadmode(i).ne.0.and." in drip
    assert "dripspreadmode(i).ne.5.and." in drip
    assert "dripspreadmode(i).ne.6)then" in drip
    assert "dripsourcewidth(i).gt.0.0)then" in drip
    assert "dripsourcewidth(i).le.0.0)then" in drip
    assert "mode5/6dripsourcewidthrequired" in drip


def test_mode6_drip_registers_activity_without_mode5_distribution():
    drip = _compact(_source(DRIP_SOURCE))

    mode6_pos = drip.index("if(dripspreadmode(jj).eq.6)then")
    mode5_pos = drip.index("if(dripspreadmode(jj).eq.5)then")
    assert mode6_pos < mode5_pos
    assert "dripmode6inputflux(mode6source)=dble(sourceflux)" in drip
    assert "desiredradius=0" in drip
    assert "dripmode6fluxactive(centerbnd)=1" in drip
    assert "dripmode6boundaryowner(centerbnd)=mode6source" in drip
    assert "if(sourceflux.gt.releasecap)then" not in drip
    assert "dripmode6rateactive" not in drip
    assert "if(desiredradius.gt.0)then" not in drip
    assert "localcap=0.01*consat" not in drip
    assert "dripmode6assignedflux(centerbnd)" in drip
    assert "dripspreadmode(jj).eq.6.and.maxwetwidth.ge.surfacewidth-driptol" in drip
    assert "gotot520" not in drip
    assert "goto520" in drip
    assert "0.001d0" not in drip


def test_mode6_water_mover_active_boundary_contract():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "q(i)=baseq(i)" in water_mover
    assert "codew(i)=basecodew(i)" in water_mover
    assert "dripmode6headactive(k).eq.1" in water_mover
    assert "codew(i)=4" in water_mover
    assert "hnew(i)=0.0" in water_mover
    assert "dripmode6fluxactive(k).eq.1" in water_mover
    assert "codew(i)=-4" in water_mover
    assert "q(i)=q(i)+sngl(dripmode6assignedflux(k))" in water_mover
    assert "qact(n)=qn" in water_mover
    assert "dripmode6remainingflux" in water_mover
    assert "goto1111" in water_mover
    assert "mode6maxiter=max(mode6maxiter,2*dripmode6maxradius(mode6source)+3)" in water_mover
    assert "mode6maxiter=min(mode6maxiter,50)" in water_mover
    assert "mode6solvermaxit=max(maxit,60)" in water_mover
    assert "dripmode6solverlimit_sum=dripmode6solverlimit_sum+dt" in water_mover
    assert "mode6boundaryactive=0" in water_mover
    assert "if(mode6boundaryactive.eq.1)then" in water_mover
    assert "hnew(n).gt.sngl(mode6tol)" in water_mover
    assert "dripmode6fluxactive(i).ne.1" in water_mover
    assert "mode6assigned=dmax1(dripmode6assignedflux(k),0.0d0)" in water_mover
    assert "mode6actual=mode6assigned" in water_mover
    assert "mode6actual.gt.mode6assigned+mode6tol" not in water_mover
    assert "dripmode6boundedflux" not in water_mover
    assert "qact(n)=sngl(dripmode6assignedflux(k))" not in water_mover
    assert "dripmode6rateactive" not in water_mover
    assert "mode6assigned-dmax1(dble(qact(n)),0.0d0).gt." not in water_mover
    assert "mode6fluxlimit" not in water_mover
    assert "mode6headpresent" not in water_mover
    assert "mode6nonconv" not in water_mover


def test_mode6_g05_diagnostic_contract():
    output = _source(OUTPUT_SOURCE)
    compact = _compact(output)

    for column in (
        "DripMode6Accepted",
        "DripMode6Remaining",
        "DripMode6HeadNodes",
        "DripMode6FluxNodes",
        "DripMode6Iterations",
        "DripMode6SolverLimit",
        "DripMode6ClosureResidual",
    ):
        assert column in output
    assert "dripmode6accepted_flux/gridwidth*10.0" in compact
    assert "dripmode6solverlimit_sum/dripmode6diag_time" in compact
    assert "dripinput_flux-dripmode6accepted_flux-dripmode6remaining_flux" in compact
