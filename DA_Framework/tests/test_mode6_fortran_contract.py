from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIP_SOURCE = REPO_ROOT / "Soil Source" / "Drip.FOR"
WATER_MOVER_SOURCE = REPO_ROOT / "Soil Source" / "Watmov.for"
MATERIAL_SOURCE = REPO_ROOT / "Soil Source" / "SETMAT01.FOR"
OUTPUT_SOURCE = REPO_ROOT / "Soil Source" / "OUTPUT.FOR"
SURFACE_INCLUDE = REPO_ROOT / "Soil Source" / "PuSurface.ins"
PUBLIC_INCLUDE = REPO_ROOT / "Soil Source" / "public.ins"
SYNCHRON_SOURCE = REPO_ROOT / "Soil Source" / "SYNCHRON.FOR"
DATE_FUNCTIONS_SOURCE = REPO_ROOT / "Soil Source" / "dateFunctions.for"
HOURLY_WEATHER_SOURCE = REPO_ROOT / "Soil Source" / "hourwea.for"
DAILY_WEATHER_SOURCE = REPO_ROOT / "Soil Source" / "SETSUR02.FOR"
AUTO_IRRIGATION_SOURCE = REPO_ROOT / "Soil Source" / "AutoIrrigate.for"
IRRIGATION_SOURCE = REPO_ROOT / "Soil Source" / "Irrigation.for"
PONDING_HEAD_SOURCE = REPO_ROOT / "Soil Source" / "PondingByHead.for"
PONDING_FLUX_SOURCE = REPO_ROOT / "Soil Source" / "PondingByFlux.for"
SET_BOUNDARY_SOURCE = REPO_ROOT / "Soil Source" / "SetBoundary.for"


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
    assert "dripmode6atmosheadactive(numbpd)" in include
    assert "dripmode6candidateowner(numbpd)" in include
    assert "dripmode6solverlimit_sum" in include
    assert "dripmode6boundarylimit_sum" in include
    assert "dripmode6stepcuts_sum" in include
    assert "dripmode6mindt" in include
    assert "dripmode6adaptiveiter" in include


def test_mode6_input_contract_allows_only_supported_spread_modes():
    drip = _compact(_source(DRIP_SOURCE))

    assert "dripspreadmode(i).ne.0.and." in drip
    assert "dripspreadmode(i).ne.5.and." in drip
    assert "dripspreadmode(i).ne.6)then" in drip
    assert "dripsourcewidth(i).gt.0.0)then" in drip
    assert "dripsourcewidth(i).le.0.0)then" in drip
    assert "mode5/6dripsourcewidthrequired" in drip
    assert "dripspreadmode(i).eq.6.and.num_nodes(i).ne.1" in drip
    assert "mode6requiresexactlyonedripemitter" in drip


def test_mode6_drip_registers_activity_without_mode5_distribution():
    drip = _compact(_source(DRIP_SOURCE))

    mode6_pos = drip.index("if(dripspreadmode(jj).eq.6)then")
    mode5_pos = drip.index("if(dripspreadmode(jj).eq.5)then")
    assert mode6_pos < mode5_pos
    assert "dripmode6inputflux(mode6source)=dble(sourceflux)" in drip
    assert "desiredradius=min(wetradius(jj,in),maxradius)" in drip
    assert "dripmode6headactive(dripsurfbnd(k))=1" in drip
    assert "dripmode6fluxactive(dripsurfbnd(k))=1" in drip
    assert "dripmode6boundaryowner(dripsurfbnd(k))=mode6source" in drip
    assert "if(sourceflux.gt.releasecap)then" not in drip
    assert "dripmode6rateactive" not in drip
    assert "if(desiredradius.gt.0)then" not in drip
    assert "localcap=0.01*consat" not in drip
    assert "dble(sourceflux)*dble(width(dripsurfbnd(k)))/" in drip
    full_surface_pos = drip.index(
        "if(dripspreadmode(jj).eq.6)then",
        drip.index("edgemaxradius=max("),
    )
    assert drip.index("maxradius=edgemaxradius", full_surface_pos) > full_surface_pos
    assert "if(dripmode6count.ge.1)then" in drip
    assert "gotot520" not in drip
    assert "goto520" in drip
    assert "sourceflux.gt.0.001d0" not in drip


def test_drip_event_uses_step_end_interval_without_edge_volume_shift():
    drip = _compact(_source(DRIP_SOURCE))

    active_interval = (
        "time.gt.tappl_start(jj)+driptimetol.and."
        "time.le.tappl_stop(jj)+driptimetol"
    )
    assert drip.count(active_interval) == 1
    assert "if(time.ge.tappl_start(jj).and.time.lt.tappl_stop(jj))then" in drip
    assert "elseif(time.gt.tappl_stop(jj)+driptimetol)then" in drip


def test_mode6_boundaries_are_restored_before_ownership_is_cleared():
    drip = _compact(_source(DRIP_SOURCE))

    restore = drip.index("if(dripmode6candidateowner(i).gt.0.or.")
    clear_owner = drip.index("dripmode6candidateowner(i)=0", restore)
    assert restore < clear_owner
    assert "if(dripmode6atmosheadactive(i).eq.1)then" in drip[restore:clear_owner]
    assert "q(n)=0.0" in drip[restore:clear_owner]
    assert "codew(n)=4" in drip[restore:clear_owner]
    assert "q(n)=-varbw(i,3)*width(i)" in drip[restore:clear_owner]
    assert "codew(n)=-4" in drip[restore:clear_owner]


def test_mode6_atmospheric_active_set_is_trialed_then_committed():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert (
        "mode6atmostrialheadactive(k)="
        "dripmode6atmosheadactive(k)"
        in water_mover
    )
    assert water_mover.count(
        "mode6atmostrialheadactive(k)=dripmode6atmosheadactive(k)"
    ) >= 5
    assert "mode6atmosmaxiter=2*numbp+10" in water_mover
    assert (
        "dripmode6headactive(k).eq.0.and."
        "dripmode6fluxactive(k).eq.0"
        in water_mover
    )
    assert "mode6atmospotentialq=-dble(varbw(k,3))*dble(width(k))" in water_mover
    assert (
        "mode6atmosfluxlower=dmin1(0.0d0,"
        "mode6atmospotentialrounded)"
        in water_mover
    )
    assert (
        "mode6atmosfluxupper=dmax1(0.0d0,"
        "mode6atmospotentialrounded)"
        in water_mover
    )
    assert (
        "mode6atmosfluxroundoff=dabs(dble(spacing(qact(n))))+"
        "dabs(dble(spacing(sngl(mode6atmospotentialrounded))))"
        in water_mover
    )
    assert (
        "mode6atmosactualq.lt.mode6atmosfluxlower-"
        "mode6atmosfluxroundoff.or."
        "mode6atmosactualq.gt.mode6atmosfluxupper+"
        "mode6atmosfluxroundoff"
        in water_mover
    )
    assert (
        "mode6atmosheadroundoff=dabs(spacing(hnew(n)))+"
        "dabs(spacing(dble(hcrita)))"
        in water_mover
    )
    assert (
        "elseif(hnew(n).lt.dble(hcrita)-"
        "mode6atmosheadroundoff)then"
        in water_mover
    )
    atmosphere_switch = water_mover[
        water_mover.index("mode6atmosneedresolve=0") :
        water_mover.index("doi=1,numnp", water_mover.index("mode6atmosneedresolve=0"))
    ]
    assert "tolh" not in atmosphere_switch
    assert "mode6atmositerationcount.gt.mode6atmosmaxiter" in water_mover
    assert "mode6atmosphericactiveboundarydidnotclose" in water_mover

    trial_switch = water_mover.index("mode6atmosneedresolve=0")
    full_mass_audit = water_mover.index("callevaluatemode6newtonmassbalance")
    accepted_commit = water_mover.index(
        "dripmode6atmosheadactive(k)=mode6atmostrialheadactive(k)"
    )
    assert trial_switch < full_mass_audit < accepted_commit


def test_surface_runoff_reset_does_not_fire_during_evaporation():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert (
        "if((hnew(i).ge.criticalh).and.(abs(codew(i)).eq.4)"
        ".and.(q(i).gt.0.0d0))then"
        in water_mover
    )


def test_mode6_water_mover_active_boundary_contract():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "q(i)=baseq(i)" in water_mover
    assert "codew(i)=basecodew(i)" in water_mover
    assert "baseq(i)=-varbw(k,3)*width(k)" in water_mover
    assert "basecodew(i)=-4" in water_mover
    assert "dripmode6headactive(k).eq.1" in water_mover
    assert "codew(i)=4" in water_mover
    assert "hnew(i)=0.0" in water_mover
    assert "dripmode6fluxactive(k).eq.1" in water_mover
    assert "codew(i)=-4" in water_mover
    assert (
        "q(i)=q(i)+sngl(mode6continuation*"
        "dripmode6assignedflux(k))"
        in water_mover
    )
    assert "qact(n)=qn" in water_mover
    assert "dripmode6remainingflux" in water_mover
    assert "goto1111" in water_mover
    assert "mode6maxiter=20*dripsurfcount+50" in water_mover
    assert "mode6solvermaxit=max(maxit,200)" in water_mover
    assert "dripmode6boundarylimit_sum=dripmode6boundarylimit_sum+dt" in water_mover
    assert "iter=min(iter,3)" not in water_mover
    assert "mode6retrycount=mode6retrycount+1" in water_mover
    assert "hnew(i)=basehold(i)" in water_mover
    assert "dripmode6currentradius(i)=0" in water_mover
    assert "mode6failedtoconvergeatminimumwaterstep" in water_mover
    assert "goto619" not in water_mover[
        water_mover.index("if(.not.itcrit)then"):
        water_mover.index("cendofiterationloops")
    ]
    assert "mode6boundaryactive=0" in water_mover
    assert "if(mode6boundaryactive.eq.1)then" in water_mover
    assert "mode6headtol=dmax1(1.0d-8,2.0d0*dble(tolh))" in water_mover
    assert "hnew(n).gt.mode6headtol" in water_mover
    assert "if(dripmode6headactive(k).eq.1)then" in water_mover
    assert (
        "mode6boundaryactual(k)=dble(qact(n)-baseq(n)-qautoirrig(n))"
        in water_mover
    )
    assert (
        "mode6boundaryactual(k)=dmax1(dble(qn-baseq(n)-"
        "qautoirrig(n)),0.0d0)"
        not in water_mover
    )
    assert "elseif(dripmode6fluxactive(k).eq.1)then" in water_mover
    assert (
        "mode6fluxcurrent(mode6source)=mode6fluxcurrent(mode6source)+"
        "dmax1(dripmode6assignedflux(k),0.0d0)"
        in water_mover
    )
    assert "dripmode6acceptedflux(mode6source).gt." in water_mover
    assert "dripmode6inputflux(mode6source)+mode6fluxtol" in water_mover
    assert "mode6headboundaryexceededemittersupply" in water_mover
    assert "subroutineevaluatewaterstepmassbalance" in water_mover
    assert "stepstoragechange=currentstorage-previousstorage" in water_mover
    assert "massresidual=femstoragechange-" in water_mover
    assert "subroutineevaluatewaterroundoff" in water_mover
    assert "spacingold=spacing(thetaprevious(i))" in water_mover
    assert "massroundoffsigma=dsqrt(dmax1(storagevariance+" in water_mover
    assert "mode6massabsolutetolerance=1.0d-6" in water_mover
    assert (
        "mode6masstolerance=dmax1(mode6massabsolutetolerance,"
        "5.0d0*mode6massroundoff+1.0d-4*mode6massscale)"
    ) in water_mover
    assert "callsolvemode6fixedactivesetnewton" in water_mover
    assert "goto6189" in water_mover
    assert "subroutinesolvemode6fixedactivesetnewton" in water_mover
    assert "callsolvemode6ilugmres(jacobian,linearrhs,a1" in water_mover
    assert "parameter(restartlength=30)" in water_mover
    assert "calllusolv(numnodes,maxneighbors" in water_mover
    assert "callmatm2(work,matrix,solution,numnodes" in water_mover
    assert "qact(n)=sngl(physicalresidual(n)+dble(q(n)))" in water_mover
    assert "subroutineevaluatemode6newtonmassbalance" in water_mover
    assert "if(dabs(mode6massresidual).gt.mode6masstolerance)then" in water_mover
    assert "dripmode6iterationcount=max(0,dripmode6iterationcount-1)" not in water_mover
    assert "mode6watermassbalancefailedatminimumstep" in water_mover
    assert "dripmode6nonlinearcuts_sum=" in water_mover
    assert "dripmode6supplycuts_sum=" in water_mover
    assert "dripmode6masscuts_sum=" in water_mover
    assert "dripshare=mode6actual*dble(width(k))/" in water_mover
    assert "dripmode6assignedflux(k)=dripshare" in water_mover
    assert "mode6continuationaccepted=-1.0d0" in water_mover
    assert "20.0d0*dble(wateroutermaxiter)" in water_mover
    assert "dble(max(maxit,20))" in water_mover
    assert "dripmode6adaptiveiter=iter" in water_mover
    assert "if(waterouterretrycount.gt.0)" in water_mover
    assert "max(dripmode6adaptiveiter,7)" in water_mover
    assert not re.search(
        r"(?im)^\s*iter\s*=\s*[36]\s*$",
        _source(WATER_MOVER_SOURCE),
    )
    assert "dmin1(dripmode6inputflux" not in water_mover
    assert "dripmode6boundedflux" not in water_mover
    assert "qact(n)=sngl(dripmode6assignedflux(k))" not in water_mover
    assert "dripmode6rateactive" not in water_mover
    assert "mode6assigned-dmax1(dble(qact(n)),0.0d0).gt." not in water_mover
    assert "mode6fluxlimit" not in water_mover
    assert "mode6headpresent" not in water_mover
    assert "mode6nonconv=" not in water_mover


def test_mode6_time_step_signal_does_not_overwrite_picard_iterations():
    synchronizer = _compact(_source(SYNCHRON_SOURCE))

    assert "adaptiveiter=iter" in synchronizer
    assert "dripmode6active.eq.1.and.dripmode6adaptiveiter.gt.0" in synchronizer
    assert "adaptiveiter=dripmode6adaptiveiter" in synchronizer
    assert "if(adaptiveiter.le.3" in synchronizer
    assert "if(adaptiveiter.ge.7)" in synchronizer
    assert synchronizer.index("dtopt=dmax1(dtopt,dtmin)") < synchronizer.index(
        "dt=dmin1(dtopt,timegap)"
    )
    assert "if(timegap.lt.dtmin)thenpartitioncount=1" in synchronizer
    assert "partitionminimum=max(1,ceiling(timegap/dtmax))" in synchronizer
    assert "partitionmaximum=max(1,idint(timegap/dtmin))" in synchronizer
    assert "dt=timegap/dble(partitioncount)" in synchronizer


def test_drip_event_clock_uses_double_precision_common_state():
    drip = _compact(_source(DRIP_SOURCE))
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    double_declaration = (
        "doubleprecisiontappl_start,tappl_stop,nexttime,"
        "start_hour(max_times),stop_hour(max_times)"
    )
    assert double_declaration in drip
    assert "doubleprecisiontappl_start,tappl_stop" in water_mover
    assert "tappl_start(i)=dble(julday(start_date(i)))+" in drip
    assert "start_hour(i)/24.0d0" in drip
    assert "tappl_stop(i)=dble(julday(stop_date(i)))+" in drip
    assert "stop_hour(i)/24.0d0" in drip
    assert "nexttime=dmin1(nexttime,tappl_start(i))" in drip
    assert "nexttime=dmin1(nexttime,tappl_stop(jj))" in drip
    assert "amin1(nexttime,tappl_" not in drip


def test_hourly_schedulers_use_one_canonical_double_precision_clock():
    date_functions = _compact(_source(DATE_FUNCTIONS_SOURCE))
    hourly_weather = _compact(_source(HOURLY_WEATHER_SOURCE))
    daily_weather = _compact(_source(DAILY_WEATHER_SOURCE))
    auto_irrigation = _compact(_source(AUTO_IRRIGATION_SOURCE))
    irrigation = _compact(_source(IRRIGATION_SOURCE))
    output = _compact(_source(OUTPUT_SOURCE))
    drip = _compact(_source(DRIP_SOURCE))

    assert "doubleprecisionfunctionnextcanonicalhour(currenttime)" in date_functions
    assert "dayanchor=dble(idint(currenttime))" in date_functions
    assert "hourindex=nint(24.0d0*(currenttime-dayanchor))" in date_functions
    assert (
        "nextcanonicalhour=dayanchor+dble(hourindex+1)/24.0d0"
        in date_functions
    )

    hourly_sources = (hourly_weather, daily_weather, auto_irrigation, irrigation)
    for source in hourly_sources:
        assert "parameter(period=1.0d0/24.0d0)" in source
        assert "nextcanonicalhour(time)" in source
        assert "time+period" not in source
        assert "tnext(modnum)+period" not in source

    assert "doubleprecisionperiod,nextcanonicalhour" in output
    assert "tnext(modnum)=nextcanonicalhour(time)" in output
    assert "time+period" not in output
    assert "parameter(period=1.0d0/24.0d0)" in drip


def test_scheduled_irrigation_and_ponding_times_are_double_precision():
    irrigation = _compact(_source(IRRIGATION_SOURCE))
    ponding_head = _compact(_source(PONDING_HEAD_SOURCE))
    ponding_flux = _compact(_source(PONDING_FLUX_SOURCE))
    set_boundary = _compact(_source(SET_BOUNDARY_SOURCE))

    assert "doubleprecisionperiod,tapplirrig,stopirrig," in irrigation
    assert "tapplirrig(i)=dble(julday(date(i)))" in irrigation
    assert "dble(irrgstarthour)/24.0d0" in irrigation
    assert "dble(irrgstarthour+hoursirrigated)/24.0d0" in irrigation

    for source in (ponding_head, ponding_flux):
        assert "doubleprecision::starttime(pondtimenum),endtime(pondtimenum)" in source
        assert "starttime(i)=dble(julday(startdate(i)))+" in source
        assert "dble(starthour(i))/24.0d0" in source
        assert "endtime(i)=dble(julday(enddate(i)))+" in source
        assert "dble(endhour(i))/24.0d0" in source

    assert "doubleprecisionperiod,rpond_starttime,rpond_endtime" in set_boundary
    assert "dble(julday(cdate))+dble(myhour)/24.0d0" in set_boundary


def test_mode6_newton_stops_at_shared_constitutive_breakpoints():
    material = _compact(_source(MATERIAL_SOURCE))
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "subroutinesetmatcurrentbreakpoints(par,hk,hs)" in material
    assert "callsetmatcurrentbreakpoints(par,hk,hs)" in material
    assert "linesearchmaximum=2*numnp+60" in water_mover
    assert "candidatealpha=(hk-basehead(i))/delta(i)" in water_mover
    assert "candidatealpha=(hs-basehead(i))/delta(i)" in water_mover
    assert "halfalpha=0.5d0*alpha" in water_mover
    assert "candidatealpha.gt.nextalpha.and." in water_mover
    assert "candidatealpha.lt.alpha" in water_mover
    assert "hnew(breaknode)=breakhead" in water_mover
    assert water_mover.index("hnew(breaknode)=breakhead") < water_mover.index(
        "callassemblemode6currentresidualjacobian",
        water_mover.index("hnew(breaknode)=breakhead"),
    )
    assert "trialnormsquared.le." in water_mover
    assert "mode6newtonconstitutiveevent" in water_mover


def test_water_retries_subcycle_without_rolling_back_public_time():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "wateroutertime=time" in water_mover
    assert "waterouterstep=step" in water_mover
    assert "waterlocalend=wateroutertime-waterouterstep" in water_mover
    assert "waterremaining=wateroutertime-waterlocalend" in water_mover
    assert "waterremaining-dt.lt.dtmin)dt=waterremaining" in water_mover
    assert "goto1100" in water_mover
    assert "time=wateroutertime" in water_mover
    assert "step=waterouterstep" in water_mover
    assert "waterqintegral(i)/waterouterstep" in water_mover
    assert "watervxintegral(i)/waterouterstep" in water_mover
    assert "time=time+dt-step" not in water_mover


def test_mode6_positive_head_switch_uses_richards_tolerance():
    water_mover = _compact(_source(WATER_MOVER_SOURCE))

    assert "mode6headtol=dmax1(1.0d-8,2.0d0*dble(tolh))" in water_mover
    assert "mode6headtol=dmax1(0.1d0,dble(tolh))" not in water_mover


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
        "DripMode6BoundaryLimit",
        "DripMode6ClosureResidual",
        "DripMode6StepCuts",
        "DripMode6NonlinearCuts",
        "DripMode6SupplyCuts",
        "DripMode6MassCuts",
        "DripMode6MinDtDays",
    ):
        assert column in output
    assert "dripmode6accepted_flux/gridwidth*10.0" in compact
    assert "dripmode6solverlimit_sum/dripmode6diag_time" in compact
    assert "dripmode6boundarylimit_sum/dripmode6diag_time" in compact
    assert "dripmode6stepcuts_sum" in compact
    assert "dripmode6mindt" in compact
    assert "dripinput_flux-dripmode6accepted_flux-dripmode6remaining_flux" in compact


def test_full_domain_water_balance_is_independent_of_drip_ledger():
    public = _compact(_source(PUBLIC_INCLUDE))
    water_mover = _compact(_source(WATER_MOVER_SOURCE))
    output = _compact(_source(OUTPUT_SOURCE))

    assert "common/watermassbalance_public/" in public
    assert "callinitializewatermassbalance()" in water_mover
    assert "callupdatewatermassbalance(thold_1,dt)" in water_mover
    assert "subroutineintegratewaterdomain" in water_mover
    assert "trianglearea*xmultiplier" in water_mover
    assert "if(codew(n).gt.0)then" in water_mover
    assert "boundaryflux=dble(qact(n))" in water_mover
    assert "boundaryflux=dble(q(n))" in water_mover
    assert "currentstorage-previousstorage" in water_mover
    assert "stepin-stepout-stepsink" in water_mover
    assert "dripactualinfil_flux" not in water_mover[
        water_mover.index("subroutineupdatewatermassbalance"):
        water_mover.index("subroutineresetmode6waterstep")
    ]
    assert "watermassbalance.out" in output
    assert "relativeerror_pct" in output
    assert "if(dripmode6active.ne.1)then" in water_mover
    assert "watermassbalancefailedafterpicardrefinement" in water_mover
