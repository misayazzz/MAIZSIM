from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WATER_MOVER = REPO_ROOT / "Soil Source" / "Watmov.for"


def _source():
    return "".join(WATER_MOVER.read_text(encoding="utf-8").lower().split())


def test_every_contact_node_starts_as_a_conservative_neumann_boundary():
    mover = _source()
    assert "if(dripmode6contactmeasure(k).gt.1.0d-12)then" in mover
    assert "dripmode6fluxactive(k)=1" in mover
    assert "dripmode6assignedflux(k)=dripmode6inputflux(1)*" in mover
    assert "dripmode6contactmeasure(k)/dripmode6contacttotal" in mover


def test_positive_head_switches_to_zero_head_and_resolves():
    mover = _source()
    assert "if(hnew(n).gt.mode6headtol)then" in mover
    assert "dripmode6headactive(k)=1" in mover
    assert "hnew(n)=0.0" in mover
    assert "mode6needresolve=1" in mover


def test_remaining_supply_never_activates_a_node_outside_contact():
    mover = _source()
    forbidden = (
        "dripmode6currentradius",
        "dripmode6maxradius",
        "mode6newleft",
        "mode6newright",
        "dripsurfbnd(mode6new",
    )
    for text in forbidden:
        assert text not in mover
    assert "remainingfinitesupplybelongstothelocalponding/overflowledger" in mover


def test_retry_rebuilds_the_same_fixed_contact_support():
    mover = _source()
    reset = mover[mover.index("subroutineresetmode6waterstep") :]
    assert "dripmode6contactmeasure(k)" in reset
    assert "dripmode6assignedflux(k)=dripmode6inputflux(i)*" in reset
    assert "dripmode6contactmeasure(k)/dripmode6contacttotal" in reset
    assert "dt=dmax1(dt/3.0d0,dtmin)" in mover
