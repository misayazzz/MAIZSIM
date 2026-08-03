*|||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||*
* codes that are positive are for prescribed pressure heads (flux is calculated). 
* Codes that are negative or 0 are for prescibed fluxes. 
* for constant or prescribed bc:
*       Dirichlet BC is prescribed or constant head
*       Neumann boundary condition is prescribed or constant flux
* CDT added a drainage boundary Nov 2007. This is like a seepage face but the nodes always have
* drainage and it is usually horizontal.
      subroutine WaterMover ()
      Include 'public.ins'
      Include 'puplant.ins'
      Include 'puweath.ins'
      include 'PuSurface.ins'
      Parameter (NTabD=100,NPar=13)
      
      Double precision A,B,C, B_1, A_1
      Double precision dt,dtOld,t,tOld,PI,DPI,F2,QN
      Double precision ThOld,ThOld_1,hOld,hTemp,hOld_1,
     !                 Th,EpsTh,EpsH,Dif,Mode6BracketLow,
     !                 Mode6BracketHigh,Mode6BoundaryHead,
     !                 BaseHOld,F,DS,Cap,Fc,Sc,
     !                 ConAxx,ConAzz,ConAxz,
     !                 SoilPar,hTab,ConTab,CapTab,ConSat,TheTab,alh1,dlh,
     !                 WaterECNVRG,WaterRCNVRG,WaterACNVRG,
     !                 Mode6DiagBottom,Mode6DiagEmitter,
     !                 Mode6DiagOtherSurface,Mode6DiagEq,
     !                 Mode6DiagDesired,Mode6DiagEqSum,Mode6DiagEqMax
       Double precision DripShare,Mode6OldStorage,
     !                 Mode6AvailableVolume,Mode6AcceptedVolume,
     !                 Mode6NewStorage,Mode6StorageCapacity,
     !                 Mode6OverflowVolume
       Double precision Mode6Accepted(MaxDripMode6D),
     !                 Mode6Remaining(MaxDripMode6D),
     !                 Mode6FluxCapacity(MaxDripMode6D),
     !                 Mode6FluxCurrent(MaxDripMode6D),
     !                 Mode6FluxWeight(MaxDripMode6D),
     !                 Mode6SourceHead(MaxDripMode6D),
     !                 Mode6SourceBracketLow(MaxDripMode6D),
     !                 Mode6SourceBracketHigh(MaxDripMode6D),
     !                 Mode6BoundaryActual(NumBPD),
     !                 Mode6BoundaryCapacity(NumBPD),
     !                 Mode6Actual,Mode6HeadTol,Mode6FluxTol,
     !                 Mode6MeasureTol,Mode6Term,
     !                 Mode6MassResidual,Mode6MassScale,
     !                 Mode6MassRoundoff,Mode6MassTolerance,
     !                 Mode6MassAbsoluteTolerance
      real ATG,HSP
      Double precision Mode6Correction,Mode6CorrectionChange,
     !                 Mode6Relaxation,Mode6RelaxNumerator,
     !                 Mode6RelaxDenominator,Mode6RelaxPrevious,
     !                 Mode6RawEps,Mode6TrustFactor,
     !                 Mode6TrustLimit,
     !                 Mode6Continuation,Mode6ContinuationAccepted
      Double precision Mode6CorrectionVector(NumNPD)
      Double precision WaterOuterTime,WaterOuterStep,WaterLocalEnd,
     !                 WaterRemaining,WaterNextDt,WaterTimeTol,
     !                 WaterQIntegral(NumNPD),
     !                 WaterQActIntegral(NumNPD),
     !                 WaterVxIntegral(NumNPD),
     !                 WaterVzIntegral(NumNPD)
cccz move it to "PuSurface.ins" for public use 
cccz  Double precision CriticalH, CriticalH_R
      Logical Explic,ItCrit,FreeD,BadHead
      Real BaseQ(NumNPD)
      Dimension hOld_1(NumNPD),Dif(NumNPD),
     !          Mode6BracketLow(NumNPD),Mode6BracketHigh(NumNPD),
     !          Mode6BoundaryHead(NumNPD),BaseHOld(NumNPD)
       Integer trigger_Runoff,p_Runoff,
     !        Mode6NeedResolve,Mode6Source,Mode6Bnd,
     !        Mode6HeadCount,Mode6FluxCount,Mode6ActiveCount,
     !        Mode6MaxIter,Mode6SolverMaxIt,Mode6Converted,
     !        Mode6BoundaryActive,Mode6LimitedClosure,
     !        Mode6RetryCount,Mode6OverAccepted,Mode6FluxNodeUpdate
      Integer WaterSubstepCount,WaterOuterMaxIter,WaterOuterRetryCount
      Integer Mode6NewtonSuccess,Mode6NewtonIterations,
     !        Mode6NewtonFailure,Mode6NewtonDetailedDiagnostics,
     !        Mode6ContinuationRetryAvailable,
     !        Mode6AtmosNeedResolve,Mode6AtmosIterationCount,
     !        Mode6AtmosMaxIter,Mode6AtmosToHeadCount,
     !        Mode6AtmosToFluxCount,Mode6AtmosLastToHeadCount,
     !        Mode6AtmosLastToFluxCount,Mode6AtmosPrevToHeadCount,
     !        Mode6AtmosPrevToFluxCount
      Double precision Mode6NewtonResidualMax,Mode6NewtonResidualSum,
     !                 Mode6NewtonAlpha,Mode6NewtonLinearError,
     !                 Mode6AtmosPotentialQ,Mode6AtmosPotentialRounded,
     !                 Mode6AtmosActualQ,Mode6AtmosFluxLower,
     !                 Mode6AtmosFluxUpper,Mode6AtmosFluxRoundoff,
     !                 Mode6AtmosHeadRoundoff
      Integer BaseCodeW(NumNPD)
      Integer Mode6HasLow(NumNPD),Mode6HasHigh(NumNPD)
      Integer Mode6SourceHasLow(MaxDripMode6D),
     !        Mode6SourceHasHigh(MaxDripMode6D)
      Integer Mode6AtmosTrialHeadActive(NumBPD)
      Integer Mode6AtmosSwitchCount(NumBPD)
      Integer Mode6AtmosLastDirection(NumBPD),
     !        Mode6AtmosPreviousDirection(NumBPD),
     !        Mode6AtmosLastIteration(NumBPD),
     !        Mode6AtmosPreviousIteration(NumBPD)
      Double precision Mode6AtmosLastHGap(NumBPD),
     !                 Mode6AtmosLastActual(NumBPD),
     !                 Mode6AtmosLastPotential(NumBPD),
     !                 Mode6AtmosPreviousHGap(NumBPD),
     !                 Mode6AtmosPreviousActual(NumBPD),
     !                 Mode6AtmosPreviousPotential(NumBPD)
      Dimension A(MBandD,NumNPD),B(NumNPD),F(NumNPD),DS(NumNPD),
     !    Cap(NumNPD),ListE(NumElD),E(3,3),iLoc(3),Fc(NumNPD),
     !    Sc(NumNPD),B_1(NumNPD),ThOld_1(NumNPD),A_1(MBandD,NumNPD)
      Dimension Bii(3),Cii(3)
      Common /WaterM/ ThOld(NumNPD),hTemp(NumNPD),hOld(NumNPD),
     !                ConAxx(NumElD),ConAzz(NumElD),ConAxz(NumElD),
     !                MaxIt,TolTh,TolH,dt,dtOld,tOld,
     !                thR(NMatD),hSat(NMatD),
     !                isat(NumBPD),FreeD
      Common /HydPar/ SoilPar(NPar,NMatD),
     !                hTab(NTabD),ConTab(NTabD,NMatD),
     !                CapTab(NTabD,NMatD),ConSat(NMatD),
     !                TheTab(NTabD,NMatD),alh1,dlh
      If (lInput.eq.0) goto 11  
        FreeD=.true.
        CriticalH=5.1D0
c       CriticalH_R=0.01D0
  
        hOld(:) = hNew(:)
        hTemp(:) = hOld(:)
        RO(:)=0.0
*
        ConAxz(:)=0.
        ConAxx(:)=1.
        ConAzz(:)=1.
      
      Explic=.false.
*
      im=50
      il=0
      Open(40,file=WaterFile, status='old',ERR=10)
      im=im+1
      il=il+1
      Read(40,*,ERR=10) 
      im=im+1
      il=il+1
      Read(40,*,ERR=10)
      im=im+1
      il=il+1
      Read(40,*,ERR=10) MaxIt,TolTh,TolH,
     !                  hCritA,CriticalH,dtMx(1),hTab1,hTabN,EPSI_Heat,
     !                   EPSI_Solute
        close(40) 

        
      call IADMake(KX,NumNP,NumEl,NumElD,MBandD,IAD,IADN,IADD)
c  assign bulk density      
      call SetMat(lInput,NumNP,hNew,hOld,NMat,MatNumN,Con,Cap,
     !                  BlkDn,hTemp,Explic,ThNew,hTab1,hTabN,
     !                  hSat,ThSat,ThR, ThAvail,ThFull,
     !                  FracOM, FracSind, FracClay,
     !                  TupperLimit, TLowerLimit,soilair,
     !                  SoilFile,ThAMin,ThATr)
c  need to initialize arrays after assigning h values if water ws input
     
          hOld(:) = hNew(:)
          hTemp(:) = hOld(:)
      
             
      call Veloc(NumNP,NumEl,NumElD,hNew,x,y,KX,ListNE,Con,
     !                   ConAxx,ConAzz,ConAxz,Vx,Vz)
c   Calculate Total Available Water in Profile
     
      
      ThOld(:)=ThNew(:)
      Call InitializeWaterMassBalance()

      dt=Step
      Movers(1)=1
      Return
C
C   Routine calculations
C       

 11    continue
c The synchronizer has already advanced the public clock and every crop,
c management, and surface module has used that complete outer interval.
c Richards retries therefore run as internal water substeps and must not
c shorten or roll back the public Time/Step contract.
      WaterOuterTime=Time
      WaterOuterStep=Step
      WaterLocalEnd=WaterOuterTime-WaterOuterStep
      WaterRemaining=WaterOuterStep
      WaterNextDt=WaterOuterStep
      WaterTimeTol=dmax1(1.0D-12,
     !  1.0D-10*dabs(WaterOuterStep))
      WaterSubstepCount=0
      WaterOuterMaxIter=0
      WaterOuterRetryCount=0
      Do i=1,NumNP
        WaterQIntegral(i)=0.0D0
        WaterQActIntegral(i)=0.0D0
        WaterVxIntegral(i)=0.0D0
        WaterVzIntegral(i)=0.0D0
      EndDo
      If(DripMode6Active.eq.1) DripMode6AdaptiveIter=0

 1100 Continue
      tOld=WaterLocalEnd
      dt=dmin1(WaterNextDt,WaterRemaining)
      Mode6AtmosIterationCount=0
      Mode6AtmosMaxIter=2*NumBP+10
      Mode6AtmosLastToHeadCount=0
      Mode6AtmosLastToFluxCount=0
      Mode6AtmosPrevToHeadCount=0
      Mode6AtmosPrevToFluxCount=0
      Do k=1,NumBP
        Mode6AtmosTrialHeadActive(k)=
     !    DripMode6AtmosHeadActive(k)
        Mode6AtmosSwitchCount(k)=0
        Mode6AtmosLastDirection(k)=0
        Mode6AtmosPreviousDirection(k)=0
        Mode6AtmosLastIteration(k)=0
        Mode6AtmosPreviousIteration(k)=0
      EndDo
c Avoid creating a terminal remainder below the admissible Richards step.
c Advancing the current accepted substep to the exact outer endpoint is a
c time-partition correction, not a bypass of the nonlinear solve.
      If(WaterRemaining.gt.dt.and.
     !  WaterRemaining-dt.lt.dtMin) dt=WaterRemaining
      t=tOld+dt
      Time=t
      Step=dt
      If(DripMode6Active.eq.1) then
c Reoffer only the ponded volume present at the start of this accepted
c Richards substep.  Retries leave this storage untouched.  The fixed
c contact quadrature is the sole spatial support for the finite supply.
        Mode6OldStorage=0.0D0
        Do k=1,NumBP
          Mode6OldStorage=Mode6OldStorage+DripSurfaceStorage(k)
          DripMode6AssignedFlux(k)=0.0D0
          DripMode6FluxActive(k)=0
          DripMode6HeadActive(k)=0
          DripMode6BoundaryOwner(k)=0
        EndDo
        DripMode6StorageStart(1)=Mode6OldStorage
        DripMode6InputFlux(1)=DripMode6ExternalFlux(1)+
     !    Mode6OldStorage/dt
        DripMode6RemainingFlux(1)=DripMode6InputFlux(1)
        DripMode6AcceptedFlux(1)=0.0D0
        Mode6FluxTol=dmax1(1.0D-4,
     !    1.0D-4*dabs(DripMode6InputFlux(1)))
        If(DripMode6InputFlux(1).gt.Mode6FluxTol) then
          DripMode6Count=1
          DripMode6Closed(1)=0
          Do k=1,NumBP
            If(DripMode6ContactMeasure(k).gt.1.0D-12) then
              DripMode6FluxActive(k)=1
              DripMode6BoundaryOwner(k)=1
              DripMode6AssignedFlux(k)=DripMode6InputFlux(1)*
     !          DripMode6ContactMeasure(k)/DripMode6ContactTotal
            Endif
          EndDo
        Else
          DripMode6Active=0
          DripMode6Count=0
          DripMode6Closed(1)=1
          DripBypassRunoff=0
          Do k=1,NumBP
            If(DripMode6CandidateOwner(k).gt.0) then
              n=KXB(k)
              If(DripMode6AtmosHeadActive(k).eq.1) then
                Q(n)=0.0
                CodeW(n)=4
              Else
                Q(n)=-VarBW(k,3)*Width(k)
                CodeW(n)=-4
              Endif
            Endif
          EndDo
        Endif
      Endif
      If(DripMode6Active.eq.1.and.WaterSubstepCount.gt.0)
     !  DripMode6IterationCount=0
      Do i=1,NumNP
        BaseQ(i)=Q(i)
        BaseCodeW(i)=CodeW(i)
        BaseHOld(i)=hOld(i)
      Enddo
      If(DripMode6Active.ne.1) then
c A Mode 6 emitter can temporarily cover an atmospheric hCritA node.  Once
c the event ends, restore the independently accepted atmospheric Dirichlet
c value before the unchanged legacy Picard solve starts.
        Do k=1,NumBP
          If(DripMode6AtmosHeadActive(k).eq.1) then
            i=KXB(k)
            CodeW(i)=4
            Q(i)=0.0
            hNew(i)=hCritA
            BaseCodeW(i)=4
            BaseQ(i)=0.0
          Endif
        EndDo
      Endif
      If(DripMode6Active.eq.1) then
c Q and CodeW can still contain the preceding Mode 6 water substep.  Rebuild
c every atmospheric surface candidate from the independent trial state before
c applying the emitter overlay.  This preserves flux/hCritA complementarity
c across internal substeps without carrying emitter discharge into BaseQ.
        Do k=1,NumBP
          i=KXB(k)
          If(iabs(BaseCodeW(i)).eq.4.or.
     !      DripMode6CandidateOwner(k).gt.0) then
            If(Mode6AtmosTrialHeadActive(k).eq.1) then
              BaseQ(i)=0.0
              BaseCodeW(i)=4
            Else
              BaseQ(i)=-VarBW(k,3)*Width(k)
              BaseCodeW(i)=-4
            Endif
          Endif
        EndDo
      Endif
      Mode6RetryCount=0
      Mode6Continuation=1.0
      Mode6ContinuationAccepted=-1.0D0

c
c   Start of iteration loop
c
 1111  Iter=0
      Time=t
      Step=dt
      Explic=.false.
      If(DripMode6Active.eq.1) then
        Mode6Relaxation=1.0D0
        Do i=1,NumNP
          Dif(i)=0.0D0
        EndDo
      Endif
      If(DripMode6Active.eq.1.and.DripMode6IterationCount.eq.0.and.
     !  Mode6ContinuationAccepted.lt.-0.5D0) then
        Do i=1,NumNP
          Dif(i)=0.0
          Mode6BracketLow(i)=0.0
          Mode6BracketHigh(i)=0.0
          Mode6BoundaryHead(i)=0.0
          Mode6HasLow(i)=0
          Mode6HasHigh(i)=0
        EndDo
        Do k=1,NumBP
          Mode6BoundaryCapacity(k)=0.0D0
        EndDo
        Do Mode6Source=1,DripMode6Count
          Mode6SourceHead(Mode6Source)=0.0D0
          Mode6SourceBracketLow(Mode6Source)=0.0D0
          Mode6SourceBracketHigh(Mode6Source)=0.0D0
          Mode6SourceHasLow(Mode6Source)=0
          Mode6SourceHasHigh(Mode6Source)=0
        EndDo
        Mode6ContinuationAccepted=0.0D0
      Endif

      Do i=1,NumNP
        Q(i)=BaseQ(i)
        CodeW(i)=BaseCodeW(i)
      Enddo
      If(DripMode6Active.eq.1) then
c Atmospheric and drip active sets are stored independently, but exactly one
c boundary condition is assembled at a node.  Apply atmospheric hCritA only
c where no drip head/flux state owns the current solve; the drip overlay below
c has strict priority at all other candidates.
        Do k=1,NumBP
          If(Mode6AtmosTrialHeadActive(k).eq.1.and.
     !      DripMode6HeadActive(k).eq.0.and.
     !      DripMode6FluxActive(k).eq.0) then
            i=KXB(k)
            CodeW(i)=4
            Q(i)=0.0
            hNew(i)=hCritA
          Endif
        EndDo
      Endif

cccz set the auto irrgation part before the iteration
      do k=1, NumBp
        i=KXB(k)
        if(abs(CodeW(i)).eq.4) then
           Q(i)=Q(i)+Qautoirrig(i)
           if (Q(i).gt.0.0) CodeW(i)=-4  !cccz make sure bc changes if Qn goes > 0 (infiltration) after adding the autoirrigation
        endif
      enddo
      If(DripMode6Active.eq.1) then
        Do k=1,NumBP
          i=KXB(k)
          If(DripMode6HeadActive(k).eq.1) then
            CodeW(i)=4
            hNew(i)=0.0
            Q(i)=0.0
          ElseIf(DripMode6FluxActive(k).eq.1) then
            CodeW(i)=-4
            Q(i)=Q(i)+sngl(Mode6Continuation*
     !        DripMode6AssignedFlux(k))
          Endif
        EndDo
      Endif

        Fc(:)=0.
        Sc(:)=0.
        ThAvail(:)=0.0
cccz Let us initialize the RO (runoff array) 
        RO(:)=0.0
cccz

C
C  Recasting sinks 
C

cccz directly take the sink and nodearea 
         Fc(:)=Sink(:)
         Sc(:)=NodeArea(:)
    

C
C  Start of an iteration
C                
12    Continue

*
      If(DripMode6Active.eq.1) then
c Solve one fixed HYDRUS activity set with a current-state consistent
c Newton method.  Ordinary non-drip water steps continue through the
c unchanged Picard path below.
        Mode6ContinuationRetryAvailable=0
        If(Mode6ContinuationAccepted.lt.
     !    Mode6Continuation-1.0D-12) then
          If(Mode6ContinuationAccepted.le.1.0D-12.and.
     !      Mode6Continuation.ge.1.0D0-1.0D-12) then
            Mode6ContinuationRetryAvailable=1
          ElseIf(Mode6Continuation-Mode6ContinuationAccepted.gt.
     !      0.0625D0) then
            Mode6ContinuationRetryAvailable=1
          Endif
        Endif
        Mode6NewtonDetailedDiagnostics=0
        If(dt.le.dtMin*(1.0D0+1.0D-12).and.
     !    Mode6ContinuationRetryAvailable.eq.0)
     !    Mode6NewtonDetailedDiagnostics=1
        Call SolveMode6FixedActiveSetNewton(ThOld,Fc,Cap,ConAxx,
     !    ConAzz,ConAxz,dt,Mode6NewtonSuccess,Mode6NewtonIterations,
     !    Mode6NewtonResidualMax,Mode6NewtonResidualSum,
     !    Mode6NewtonAlpha,Mode6NewtonLinearError,Mode6NewtonFailure,
     !    Mode6NewtonDetailedDiagnostics)
        Iter=Mode6NewtonIterations
        If(Mode6NewtonSuccess.ne.1) then
          If(Mode6NewtonDetailedDiagnostics.eq.1) then
            Write(*,*) 'Mode6 Newton final failure: code=',
     !        Mode6NewtonFailure,' dt=',dt,
     !        ' iterations=',Mode6NewtonIterations,
     !        ' residual_max=',Mode6NewtonResidualMax,
     !        ' residual_sum=',Mode6NewtonResidualSum,
     !        ' alpha=',Mode6NewtonAlpha,
     !        ' linear_error=',Mode6NewtonLinearError
          Endif
c Retain the established Mode 6 load continuation as the outer nonlinear
c globalization.  Intermediate loads are only initial guesses for the same
c old-time state; the water step is accepted only at full emitter flux.
          If(Mode6ContinuationAccepted.lt.
     !      Mode6Continuation-1.0D-12) then
            If(Mode6ContinuationAccepted.le.1.0D-12.and.
     !        Mode6Continuation.ge.1.0D0-1.0D-12) then
              Mode6Continuation=0.25D0
            ElseIf(Mode6Continuation-Mode6ContinuationAccepted.gt.
     !        0.0625D0) then
              Mode6Continuation=0.5D0*(Mode6Continuation+
     !          Mode6ContinuationAccepted)
            Else
              GoTo 6188
            Endif
            Do i=1,NumNP
              If(Mode6ContinuationAccepted.gt.1.0D-12) then
                hNew(i)=Mode6BoundaryHead(i)
                hTemp(i)=Mode6BoundaryHead(i)
              Else
                hNew(i)=BaseHOld(i)
                hTemp(i)=BaseHOld(i)
              Endif
            EndDo
            GoTo 1111
          Endif
 6188     Continue
          If(dt.le.dtMin) then
            Stop 'Mode 6 Newton failed at minimum water step'
          Endif
          Mode6RetryCount=Mode6RetryCount+1
          DripMode6NonlinearCuts_Sum=
     !      DripMode6NonlinearCuts_Sum+1.0D0
          Write(*,*) 'Mode6 Newton dt cut: code=',Mode6NewtonFailure,
     !      ' old_dt=',dt,' new_dt=',dmax1(dt/3.0D0,dtMin),
     !      ' cumulative_cut=',Mode6RetryCount
          Call ResetMode6WaterStep(BaseHOld,hOld,hTemp)
          Do k=1,NumBP
            Mode6AtmosTrialHeadActive(k)=
     !        DripMode6AtmosHeadActive(k)
            Mode6AtmosSwitchCount(k)=0
          EndDo
          Mode6AtmosIterationCount=0
          Mode6Continuation=1.0D0
          Mode6ContinuationAccepted=-1.0D0
          dt=dmax1(dt/3.0D0,dtMin)
          dtOpt=dt
          t=tOld+dt
          GoTo 1111
        Endif
c Update only the current-dt atmospheric trial set after a successful Newton
c solve.  This is the legacy 608-644 physical complementarity condition:
c flux state requires h>=hCritA, while head state requires actual flux to lie
c between zero and the prescribed atmospheric flux.  At the discrete corner,
c both gaps can be zero within the representation accuracy of REAL QAct,
c VarBW, Width, and hCritA.  The spacing sums below propagate those stored
c precisions; they are roundoff bounds, not TolH or empirical hysteresis.
c Failed Newton and continuation trials never modify the accepted common state.
        Mode6AtmosNeedResolve=0
        Mode6AtmosToHeadCount=0
        Mode6AtmosToFluxCount=0
        Do k=1,NumBP
          n=KXB(k)
          If((iabs(BaseCodeW(n)).eq.4.or.
     !      DripMode6CandidateOwner(k).gt.0).and.
     !      DripMode6HeadActive(k).eq.0.and.
     !      DripMode6FluxActive(k).eq.0) then
            Mode6AtmosPotentialQ=
     !        -dble(VarBW(k,3))*dble(Width(k))
            Mode6AtmosPotentialRounded=
     !        dble(sngl(Mode6AtmosPotentialQ))
            Mode6AtmosActualQ=dble(QAct(n))
            Mode6AtmosFluxLower=dmin1(0.0D0,
     !        Mode6AtmosPotentialRounded)
            Mode6AtmosFluxUpper=dmax1(0.0D0,
     !        Mode6AtmosPotentialRounded)
            Mode6AtmosFluxRoundoff=dabs(dble(spacing(QAct(n))))+
     !        dabs(dble(spacing(sngl(Mode6AtmosPotentialRounded))))
            Mode6AtmosHeadRoundoff=dabs(spacing(hNew(n)))+
     !        dabs(spacing(dble(hCritA)))
            If(Mode6AtmosTrialHeadActive(k).eq.1) then
              If(Mode6AtmosActualQ.lt.Mode6AtmosFluxLower-
     !          Mode6AtmosFluxRoundoff.or.
     !          Mode6AtmosActualQ.gt.Mode6AtmosFluxUpper+
     !          Mode6AtmosFluxRoundoff) then
                If(Mode6AtmosSwitchCount(k).eq.0) then
                  Mode6AtmosLastDirection(k)=0
                  Mode6AtmosPreviousDirection(k)=0
                Endif
                Mode6AtmosPreviousDirection(k)=
     !            Mode6AtmosLastDirection(k)
                Mode6AtmosPreviousIteration(k)=
     !            Mode6AtmosLastIteration(k)
                Mode6AtmosPreviousHGap(k)=Mode6AtmosLastHGap(k)
                Mode6AtmosPreviousActual(k)=Mode6AtmosLastActual(k)
                Mode6AtmosPreviousPotential(k)=
     !            Mode6AtmosLastPotential(k)
                Mode6AtmosLastDirection(k)=-1
                Mode6AtmosLastIteration(k)=
     !            Mode6AtmosIterationCount+1
                Mode6AtmosLastHGap(k)=hNew(n)-dble(hCritA)
                Mode6AtmosLastActual(k)=Mode6AtmosActualQ
                Mode6AtmosLastPotential(k)=
     !            Mode6AtmosPotentialRounded
                Mode6AtmosToFluxCount=Mode6AtmosToFluxCount+1
                Mode6AtmosTrialHeadActive(k)=0
                Mode6AtmosSwitchCount(k)=
     !            Mode6AtmosSwitchCount(k)+1
                BaseCodeW(n)=-4
                BaseQ(n)=sngl(Mode6AtmosPotentialQ)
                Mode6AtmosNeedResolve=1
              Endif
            ElseIf(hNew(n).lt.dble(hCritA)-
     !        Mode6AtmosHeadRoundoff) then
              If(Mode6AtmosSwitchCount(k).eq.0) then
                Mode6AtmosLastDirection(k)=0
                Mode6AtmosPreviousDirection(k)=0
              Endif
              Mode6AtmosPreviousDirection(k)=
     !          Mode6AtmosLastDirection(k)
              Mode6AtmosPreviousIteration(k)=
     !          Mode6AtmosLastIteration(k)
              Mode6AtmosPreviousHGap(k)=Mode6AtmosLastHGap(k)
              Mode6AtmosPreviousActual(k)=Mode6AtmosLastActual(k)
              Mode6AtmosPreviousPotential(k)=
     !          Mode6AtmosLastPotential(k)
              Mode6AtmosLastDirection(k)=1
              Mode6AtmosLastIteration(k)=Mode6AtmosIterationCount+1
              Mode6AtmosLastHGap(k)=hNew(n)-dble(hCritA)
              Mode6AtmosLastActual(k)=Mode6AtmosActualQ
              Mode6AtmosLastPotential(k)=
     !          Mode6AtmosPotentialRounded
              Mode6AtmosToHeadCount=Mode6AtmosToHeadCount+1
              Mode6AtmosTrialHeadActive(k)=1
              Mode6AtmosSwitchCount(k)=
     !          Mode6AtmosSwitchCount(k)+1
              BaseCodeW(n)=4
              BaseQ(n)=0.0
              hNew(n)=dble(hCritA)
              Mode6AtmosNeedResolve=1
            Endif
          Endif
        EndDo
        If(Mode6AtmosNeedResolve.eq.1) then
          Mode6AtmosPrevToHeadCount=Mode6AtmosLastToHeadCount
          Mode6AtmosPrevToFluxCount=Mode6AtmosLastToFluxCount
          Mode6AtmosLastToHeadCount=Mode6AtmosToHeadCount
          Mode6AtmosLastToFluxCount=Mode6AtmosToFluxCount
          Mode6AtmosIterationCount=Mode6AtmosIterationCount+1
          If(Mode6AtmosIterationCount.gt.Mode6AtmosMaxIter) then
            Mode6NewtonFailure=7
            If(dt.le.dtMin) then
              Write(*,*) 'Mode6 atmospheric active-set diagnostics:',
     !          ' time=',Time,' dt=',dt,
     !          ' iterations=',Mode6AtmosIterationCount
              Write(*,*) 'Mode6 atmospheric candidate counts:',
     !          ' previous_to_head=',Mode6AtmosPrevToHeadCount,
     !          ' previous_to_flux=',Mode6AtmosPrevToFluxCount,
     !          ' last_to_head=',Mode6AtmosLastToHeadCount,
     !          ' last_to_flux=',Mode6AtmosLastToFluxCount
              Do k=1,NumBP
                If(Mode6AtmosSwitchCount(k).gt.0) then
                  n=KXB(k)
                  Write(*,*) 'Mode6 atmospheric boundary:',
     !              ' boundary=',k,' node=',n,' x=',x(n),
     !              ' switches=',Mode6AtmosSwitchCount(k),
     !              ' trial_state=',Mode6AtmosTrialHeadActive(k)
                  Write(*,*) 'Mode6 atmospheric previous switch:',
     !              ' iteration=',Mode6AtmosPreviousIteration(k),
     !              ' direction=',Mode6AtmosPreviousDirection(k),
     !              ' h_gap=',Mode6AtmosPreviousHGap(k),
     !              ' actual=',Mode6AtmosPreviousActual(k),
     !              ' potential=',Mode6AtmosPreviousPotential(k)
                  Write(*,*) 'Mode6 atmospheric last switch:',
     !              ' iteration=',Mode6AtmosLastIteration(k),
     !              ' direction=',Mode6AtmosLastDirection(k),
     !              ' h_gap=',Mode6AtmosLastHGap(k),
     !              ' actual=',Mode6AtmosLastActual(k),
     !              ' potential=',Mode6AtmosLastPotential(k)
                Endif
              EndDo
              Stop 'Mode 6 atmospheric active boundary did not close'
            Endif
            Mode6RetryCount=Mode6RetryCount+1
            DripMode6NonlinearCuts_Sum=
     !        DripMode6NonlinearCuts_Sum+1.0D0
            Write(*,*) 'Mode6 Newton dt cut: code=',
     !        Mode6NewtonFailure,' old_dt=',dt,
     !        ' new_dt=',dmax1(dt/3.0D0,dtMin),
     !        ' cumulative_cut=',Mode6RetryCount
            Call ResetMode6WaterStep(BaseHOld,hOld,hTemp)
            Do k=1,NumBP
              Mode6AtmosTrialHeadActive(k)=
     !          DripMode6AtmosHeadActive(k)
              Mode6AtmosSwitchCount(k)=0
            EndDo
            Mode6AtmosIterationCount=0
            Mode6Continuation=1.0D0
            Mode6ContinuationAccepted=-1.0D0
            dt=dmax1(dt/3.0D0,dtMin)
            dtOpt=dt
            t=tOld+dt
            GoTo 1111
          Endif
c Re-solve the changed atmospheric set at the identical water dt and emitter
c continuation load.  The accepted common state remains untouched here.
          GoTo 1111
        Endif
        Do i=1,NumNP
          hTemp(i)=hNew(i)
        EndDo
        GoTo 6189
      Endif

c             If (Iter.le.1) then
C
C  SetMat: hydraulic properties for every node based on
C  new values of pressure head
C
      call SetMat(lInput,NumNP,hNew,hOld,NMat,MatNumN,Con,Cap,
     !                  BlkDn, hTemp,Explic,ThNew,hTab1,hTabN,
     !                  hSat,ThSat,ThR, ThAvail,ThFull,
     !                  FracOM, FracSind, FracClay,
     !                  TupperLimit, TLowerLimit,soilair,
     !                  SoilFile,ThAMin,ThATr)

c
c  RESET: assembling of the matrixes
c
      xMul=1.

      !B(:)=0.
      !F(:)=0.
      Do 212 i=1,NumNP
 
        B(i)=0.
        F(i)=0.
C added 1 line
        if(lOrt) B1(i)=hNew(i) 
        If (Iter.eq.0) DS(i)=0.
        Do 211 j=1,MBandD
           A(j,i)=0.
211     Continue
212   Continue
C
C     Loop on elements
C
      Do 216 n=1,NumEL
        CondI=ConAxx(n)
        CondJ=ConAzz(n)
        CondK=ConAxz(n)
        NUS=4
        If (KX(n,3).eq.KX(n,4)) NUS=3
        Do 215 k=1,NUS-2
          i=KX(N,1)
          j=KX(N,k+1)
          l=KX(N,k+2)
          iLoc(1)=1
          iLoc(2)=k+1
          iLoc(3)=k+2
          Ci=x(l)-x(j)
          Cj=x(i)-x(l)
          Ck=x(j)-x(i)
          Bi=y(j)-y(l)
          Bj=y(l)-y(i)
          Bk=y(i)-y(j)
          AE=(Ck*Bj-Cj*Bk)/2.
          CapE=(CAP(i)+CAP(j)+CAP(l))/3.0
          ConE=(Con(i)+Con(j)+Con(l))/3.0
          If (KAT.eq.1) xMul=2.*3.1416*(x(i)+x(j)+x(l))/3.
          AMul=xMul*ConE/4./AE
          BMul=xMul*ConE/2.
          FMul=xMul*AE/12.
          If (Iter.eq.0) then
            SinkE=Fc(i)+Fc(j)+Fc(l)
            DS(i)=DS(i)+Fmul*(SinkE+Fc(i))
            DS(j)=DS(j)+Fmul*(SinkE+Fc(j))
            DS(l)=DS(l)+Fmul*(SinkE+Fc(l))
          Endif
          F(i)=F(i)+FMul*4.
          F(j)=F(j)+FMul*4.
          F(l)=F(l)+FMul*4.
          If (KAT.ge.1) then
            B(i)=B(i)+BMul*(CondK*Bi+CondJ*Ci)
            B(j)=B(j)+BMul*(CondK*Bj+CondJ*Cj)
            B(l)=B(l)+BMul*(CondK*Bk+CondJ*Ck)
          Endif
          E(1,1)=CondI*Bi*Bi+2.*CondK*Bi*Ci+CondJ*Ci*Ci
          E(1,2)=CondI*Bi*Bj+CondK*(Bi*Cj+Ci*Bj)+CondJ*Ci*Cj
          E(1,3)=CondI*Bi*Bk+CondK*(Bi*Ck+Ci*Bk)+CondJ*Ci*Ck
          E(2,1)=E(1,2)
          E(2,2)=CondI*Bj*Bj+2.*CondK*Bj*Cj+CondJ*Cj*Cj
          E(2,3)=CondI*Bj*Bk+CondK*(Bj*Ck+Bk*Cj)+CondJ*Cj*Ck
          E(3,1)=E(1,3)
          E(3,2)=E(2,3)
          E(3,3)=CondI*Bk*Bk+2.*CondK*Bk*Ck+CondJ*Ck*Ck
          Do 214 i=1,3
            iG=KX(n,iLoc(i))
            Do 213 j=1,3
              jG=KX(n,iLoc(j))
              if(lOrt) then
                call Find(iG,jG,kk,NumNP,MBandD,IAD,IADN)
                A(kk,iG)=A(kk,iG)+AMul*E(i,j)
              else
                iB=iG-jG+1
                if(iB.ge.1) A(iB,jG)=A(iB,jG)+AMul*E(i,j)
                end if
213         Continue
214       Continue
215     Continue
216   Continue
c
c     Determine boundary fluxes
c
        B_1=B       !dt save B matrix for flux calcs later
        A_1=A 
      Do 220 n=1,NumNP
                   
        If (CodeW(n).lt.1) goto 220
        QN=B(n)+DS(n)+F(n)*(ThNew(n)-ThOld(n))/dt
        if(lOrt) then
          do 1117 j=1,IADN(n)
            QN=QN+A(j,n)*hNew(IAD(j,n))
1117        continue
        else
        QN=QN+A(1,n)*hNew(n)
        Do 219 j=2,MBand
          k=n-j+1
          If (k.ge.1) then
217          QN=QN+A(j,k)*hNew(k)
          End if
          k=n+j-1
          If (k.le.NumNP) then
            QN=QN+A(j,n)*hNew(k)
          End if
219     Continue
        End if
        Q(n)=QN
220   Continue


c
c     Complete construction of RHS vector and form effective matrix
c
      Do 221 i=1,NumNP
        j=1
        if(lOrt) j=IADD(i)  
        A(j,i)=A(j,i)+F(i)*Cap(i)/dt
        B(i)=F(i)*Cap(i)*hNew(i)/dt-F(i)*(ThNew(i)-ThOld(i))/dt+
     !     Q(i)-B(i)-DS(i)

221   Continue
c
c     Modify conditions on seepage faces
c
      If (NSeep.ne.0) then
        Do 312 i=1,NSeep
          iCheck=0
          NS=NSP(i)
          Do 311 j=1,NS
            n=NP(i,j)
            If (CodeW(n).eq.-2) then
              If (hNew(n).lt.0.) then
                iCheck=1
              Else
                CodeW(n)=2
                hNew(n)=0.
              Endif
            Else
              If (iCheck.gt.0.or.Q(n).ge.0.) then
                CodeW(n)=-2
                Q(n)=0.
                iCheck=1
              End if
            Endif
311       Continue
312     Continue
      Endif
c
c     Modify conditions on Drainage boundaries
c
      If (NDrain.ne.0) then
        Do 3120 i=1,NDrain
          NDS=NDR(i)
c          iCheck=0
          Do 3110 j=1,NDS
            n=ND(i,j)
            If (CodeW(n).eq.-5) then
              if (hNew(n).ge.0) then
                 CodeW(n)=5
                 hNew(n)=0.
                endif
              Else
                If (Q(n).ge.0.) then
                  CodeW(n)=-5
                  Q(n)=0
              Endif
            Endif
3110       Continue
3120     Continue
      Endif

*     Free Drainage    
       if(FreeD) then      
        do i=1,NumBP
          n=KXB(i)
          k=CodeW(n)
          if(k.eq.-7) Q(n)=-Width(i)*Con(n)
         End do
      end if  
c
c     Modify potential surface flux boundaries
c
      If (NSurf.ne.0) then
        Do 313 i=1,NumBP
          n=KXB(i)
          k=CodeW(n)
          If (Explic.and.iabs(k).eq.4) then
             CodeW(n)=-iabs(k)
             Goto 313
          Endif


c
c   Critical surface pressure on the soil-atmosphere surface
c   valid for evaporation only
c
         If (K.eq.4) then
            If(DripMode6HeadActive(i).eq.1.or.
     !        DripMode6FluxActive(i).eq.1) Goto 3131
            If (abs(Q(n)).gt.abs(-VarBW(i,3)*Width(i))
     &                          .or.Q(n)*(-VarBW(i,3)).le.0) then
              CodeW(n)=-4
                 Q(n)=-VarBW(i,3)*Width(i)
            Endif

          Goto 3131
         Endif
c
c   Surface flux on on the soil-atmosphere surface
c
          If (K.eq.-4) then
            If (hNew(n).le.hCritA) then
              CodeW(n)=4
              hNew(n)=hCritA
               Goto 3131
            Endif
         Endif
3131     continue
c
c    pond  on  the soil-atmosphere surface
cMisha 18/9 2006
cMK----------------------------------------------------------------------------------     
 


		if ((CodeW(n).eq.-4).and.(q(n).gt.0).and.
     !      ((DripMode6Active.ne.1).or.
     !      (DripMode6FluxActive(i).ne.1))) then
c Ponded infiltration measurement is from Misha Kouznetzov
			HSP=0.009D0 !EMPIRICAL PARAMETER, HSP~=dz/3 - was 0.03
			PI=3.141592653589793238D0
			DPI=1.0d0/PI
c            ATG=0.0D0
			ATG=aTAN((hNew(N))/HSP)+PI/2.0d0 !Continuous Heaviside step function
c Delta is the derivative of the step function x hnew			
			Delta=HSP/(HSP*HSP+hNew(n)*hNew(n))*hNew(n) 
c F2 is a weighting function			
			F2=(ATG+delta)*DPI
			F2=Dmin1(F2,1.0D0)
			
		   IF(HNEW(N).LT.CriticalH) F2=1.0D-10
         		HNEWS=DMAX1(hNew(N),0.0D0)
  	      	HOLDS=DMAX1(hold(N),0.0D0)	
c update right and left sides of equation for flux due to the change in the ponded
c head (if any) 
	          j=1
			   if(lOrt) j=IADD(n)              
			    A(j,n)=A(j,n)+Width(i)*F2/dt
			    B(n)=B(n)+Width(i)*(F2*hNew(n)-(HNEWS-HOLDS))/dt          
			      
		 endif   !codew= -4

 
c   pond   on the soil-atmosphere surface
cMisha 18/9 2006
cMK-----------------     
CMK  	          
313       Continue
	Endif  !NSurf <> 0


c
c===== Dirich: constant head boundaries. Prscribed pressure heads
c===== are incorporated directly into matrices
c
      Do 412 n=1,NumNP
        If (CodeW(n).lt.1) goto 412
C added 4 lines
        if(lOrt) then
              A(IADD(n),n)=10.d30
                B(n)=10.d30*hNew(n)
         else
          Do 411 m=2,MBand
          k=n-m+1
          If (k.gt.0) then
            B(k)=B(k)-A(m,k)*hNew(n)
            A(m,k)=0.
          Endif
           l=n+m-1
          If (NumNP-l.ge.0) then
            B(l)=B(l)-A(m,n)*hNew(n)
          Endif
            A(m,n)=0.
411      Continue
          A(1,n)=1.
          B(n)=hNew(n)
C added 1 line
           end if
412      Continue

cdt this is where the old solver sits
c
c  Solving of the system of equations   
c

      if(lOrt) then
        WaterECNVRG=ECNVRG
        WaterRCNVRG=RCNVRG
        WaterACNVRG=ACNVRG
        If(DripMode6Active.eq.1) then
c The Mode 6 mass target cannot be resolved with the legacy 1e-6 linear
c tolerance.  The water matrix and solver state are REAL64, so use a
c uniformly tighter linear solve during an active Mode 6 event.
          WaterECNVRG=dmin1(WaterECNVRG,1.0D-10)
          WaterRCNVRG=dmin1(WaterRCNVRG,1.0D-10)
          WaterACNVRG=dmin1(WaterACNVRG,1.0D-10)
        Endif
        call ILU (A,NumNP,MBandD,IAD,IADN,IADD,A1)
        call OrthoMin(A,B1,B,NumNP,MBandD,NumNPD,IAD,IADN,IADD,A1,VRV,
     !                RES,RQI,RQ,QQ,QI,RQIDOT,
     !                WaterECNVRG,WaterRCNVRG,WaterACNVRG,0,
     !                MNorth,MaxItO,1)
	endif
      if (.not.lOrt) then 
c*   Reduction
      Do 513 n=1,NumNP
        Do 512 m=2,MBand
        If (abs(A(m,n)).lt.1.e-30) goto 512
          C=A(m,n)/A(1,n)
          i=n+m-1
          If (i.gt.NumNP) goto 512
          j=0
          Do 511 k=m,MBand
            j=j+1
            A(j,i)=A(j,i)-C*A(k,n)
511       Continue
          A(m,n)=C
          B(i)=B(i)-A(m,n)*B(n)
512     Continue
        B(n)=B(n)/A(1,n)
513   Continue
c*   Back substitution
      n=NumNP
514   Do 515 k=2,MBand
        l=n+k-1
        If (l.gt.NumNP) goto 516
        B(n)=B(n)-A(k,n)*B(l)
515   Continue
516   n=n-1
      If (n.gt.0) goto 514
C
C   End of an iteration
C 
      EndIf 
cdt  conventional solver ends here

      Mode6RelaxNumerator=0.0D0
      Mode6RelaxDenominator=0.0D0
      Mode6TrustFactor=1.0D0
      Do i=1,NumNP
        hTemp(i)=hNew(i)
        If(lOrt) B(i)=B1(i)
        Mode6CorrectionVector(i)=B(i)-hTemp(i)
        If(DripMode6Active.eq.1) then
c A uniform trust region globalizes the modified-Picard iteration.  In
c the dry range it limits one raw update to half the current pressure
c scale; close to saturation it retains a 10-cm minimum radius based on
c the existing hSat-20 convergence transition.  The raw correction is
c still tested below, so this limiter cannot declare false convergence.
          m=MatNumN(i)
          Mode6TrustLimit=0.5D0*dmax1(dabs(hTemp(i)),
     !      dabs(dble(hSat(m))-20.0D0))
          If(dabs(Mode6CorrectionVector(i)).gt.
     !      Mode6TrustLimit) then
            Mode6TrustFactor=dmin1(Mode6TrustFactor,
     !        Mode6TrustLimit/dabs(Mode6CorrectionVector(i)))
          Endif
        Endif
        If(DripMode6Active.eq.1.and.Iter.gt.0) then
          Mode6CorrectionChange=Mode6CorrectionVector(i)-Dif(i)
          Mode6RelaxNumerator=Mode6RelaxNumerator+
     !      Dif(i)*Mode6CorrectionChange
          Mode6RelaxDenominator=Mode6RelaxDenominator+
     !      Mode6CorrectionChange*Mode6CorrectionChange
        Endif
      EndDo
      If(DripMode6Active.eq.1.and.Iter.gt.0.and.
     !  Mode6RelaxDenominator.gt.1.0D-30) then
c Vector Aitken relaxation suppresses alternating modified-Picard
c corrections without changing the complete physical boundary load.
c The raw, unrelaxed correction is checked below, so the lower safeguard
c cannot create false convergence.
        Mode6RelaxPrevious=Mode6Relaxation
        Mode6Relaxation=-Mode6RelaxPrevious*Mode6RelaxNumerator/
     !    Mode6RelaxDenominator
        Mode6Relaxation=dmax1(0.01D0,
     !    dmin1(dmin1(1.0D0,2.0D0*Mode6RelaxPrevious),
     !    Mode6Relaxation))
      Endif
      If(DripMode6Active.eq.1)
     !  Mode6Relaxation=dmin1(Mode6Relaxation,Mode6TrustFactor)
      Do 613 i=1,NumNP
        If(DripMode6Active.eq.1) then
          hNew(i)=hTemp(i)+Mode6Relaxation*
     !      Mode6CorrectionVector(i)
          Dif(i)=Mode6CorrectionVector(i)
        Else
          hNew(i)=B(i)
        Endif
 613  Continue
      hMax=0.0
      BadHead=.false.
      do i=1,NumNP
         If(hNew(i).ne.hNew(i)) then
            BadHead=.true.
            hMax=1.0E30
         Else
            hAbs=Abs(hNew(i))
            if (hAbs.gt.hMax) hMax = hAbs
            If(hAbs.gt.1.0E30) BadHead=.true.
         Endif
      enddo
      Iter =Iter+1
      If(BadHead) then
        If(Explic) Stop 'WaterMover non-finite head'
        Explic=.true.
        Do 614 i=1,NumNP
          hNew(i)=hOld(i)
          hTemp(i)=hOld(i)
 614    Continue
        Goto 12
      Endif
      If (Explic) goto 619
C
C    Test for convergence
C
       ItCrit=.true.
       do 615 i=1,NumNp
            m=MatNumN(i)
            EpsTh=0.
            EpsH=0.
            hlev=hSat(m)-20.0
            if (hTemp(i).lt.hLev.and.hNew(i).lt.hLev) then
               Th=ThNew(i)+cap(i)*(hNew(i)-hTemp(i))
     !            /(ThSat(m)-ThR(m))
               EpsTh=abs(ThNew(i)-Th)
             else
               EpsH=abs(hNew(i)-hTemp(i))
c               Dif(i)=EpsH
             endif
             if (EpsTh.gt.TolTh.or.EpsH.gt.TolH)then
                   ItCrit=.false.
                   goto 616
             endif
             If(DripMode6Active.eq.1) then
c A relaxed Picard update is converged only when the corresponding
c unrelaxed fixed-point correction also satisfies the configured water
c tolerance.  This prevents a small Aitken factor from masking residual.
               Mode6RawEps=0.0D0
               If(hTemp(i).lt.hLev.and.hNew(i).lt.hLev) then
                 Mode6RawEps=dabs(Cap(i)*Mode6CorrectionVector(i)/
     !             (ThSat(m)-ThR(m)))
                 If(Mode6RawEps.gt.dble(TolTh)) then
                   ItCrit=.false.
                   GoTo 616
                 Endif
               Else
                 Mode6RawEps=dabs(Mode6CorrectionVector(i))
                 If(Mode6RawEps.gt.dble(TolH)) then
                   ItCrit=.false.
                   GoTo 616
                 Endif
               Endif
             Endif
 615     continue
 616   Continue
      If(ItCrit.and.DripMode6Active.eq.1) then
c A small Picard head correction is not sufficient at short water steps:
c the capacity term divided by dt can still leave a material Neumann-flux
c defect.  Reconstruct every active emitter equation and require the sum
c of absolute flux defects for each source to satisfy the same relative
c source-closure tolerance used by the complementarity update.
        Do Mode6Source=1,DripMode6Count
          Mode6FluxCapacity(Mode6Source)=0.0D0
        EndDo
        Do k=1,NumBP
          If(DripMode6FluxActive(k).eq.1) then
            Mode6Source=DripMode6BoundaryOwner(k)
            n=KXB(k)
            QN=B_1(n)+DS(n)+F(n)*(ThNew(n)-ThOld(n))/dt
            If(lOrt) then
              Do j=1,IADN(n)
                QN=QN+A_1(j,n)*hNew(IAD(j,n))
              EndDo
            Else
              QN=QN+A_1(1,n)*hNew(n)
              Do j=2,MBand
                Mode6Node=n-j+1
                If(Mode6Node.ge.1)
     !            QN=QN+A_1(j,Mode6Node)*hNew(Mode6Node)
                Mode6Node=n+j-1
                If(Mode6Node.le.NumNP)
     !            QN=QN+A_1(j,n)*hNew(Mode6Node)
              EndDo
            Endif
            If(Mode6Source.gt.0) then
              Mode6FluxCapacity(Mode6Source)=
     !          Mode6FluxCapacity(Mode6Source)+
     !          dabs(QN-dble(Q(n)))
            Endif
          Endif
        EndDo
        Do Mode6Source=1,DripMode6Count
          Mode6FluxTol=dmax1(1.0D-4,
     !      1.0D-4*dabs(DripMode6InputFlux(Mode6Source)))
          If(Mode6FluxCapacity(Mode6Source).gt.Mode6FluxTol)
     !      ItCrit=.false.
        EndDo
      Endif
      If (.not.ItCrit) then
        Mode6SolverMaxIt=MaxIt
        If(DripMode6Active.eq.1) Mode6SolverMaxIt=max(MaxIt,200)
        If (Iter.lt.Mode6SolverMaxIt.AND.
     !      hMax.lt.10.*abs(hCritA)) then
c adjust for runoff within an iteration
 

          Goto 12
        Else
            If(DripMode6Active.eq.1.and.
     !        Mode6ContinuationAccepted.lt.
     !        Mode6Continuation-1.0D-12) then
c Safeguarded load continuation only globalizes the nonlinear solve.  The
c accepted water step is always recomputed at the complete physical flux.
              If(Mode6ContinuationAccepted.le.1.0D-12.and.
     !          Mode6Continuation.ge.1.0D0-1.0D-12) then
                Mode6Continuation=0.25D0
              ElseIf(Mode6Continuation-Mode6ContinuationAccepted.gt.
     !          0.0625D0) then
                Mode6Continuation=0.5D0*(Mode6Continuation+
     !            Mode6ContinuationAccepted)
              Else
                GoTo 6171
              Endif
              Do i=1,NumNP
                If(Mode6ContinuationAccepted.gt.1.0D-12) then
                  hNew(i)=Mode6BoundaryHead(i)
                  hTemp(i)=Mode6BoundaryHead(i)
                Else
                  hNew(i)=BaseHOld(i)
                  hTemp(i)=BaseHOld(i)
                Endif
              EndDo
              GoTo 1111
            Endif
 6171       Continue
            If (dt.le.dtMin) then
            If(DripMode6Active.eq.1) then
              Mode6HeadCount=0
              Mode6FluxCount=0
              Mode6HeadTol=-1.0D30
              Mode6MeasureTol=-1.0D30
              Do k=1,NumBP
                If(DripMode6HeadActive(k).eq.1)
     !            Mode6HeadCount=Mode6HeadCount+1
                If(DripMode6FluxActive(k).eq.1) then
                  Mode6FluxCount=Mode6FluxCount+1
                  n=KXB(k)
                  Mode6HeadTol=dmax1(Mode6HeadTol,dble(hNew(n)))
                  Mode6MeasureTol=dmax1(Mode6MeasureTol,
     !              dble(hTemp(n)))
                Endif
              EndDo
              Mode6Actual=-1.0D0
              Mode6Node=0
              Do i=1,NumNP
                m=MatNumN(i)
                EpsTh=0.0
                EpsH=0.0
                hLev=hSat(m)-20.0
                If(hTemp(i).lt.hLev.and.hNew(i).lt.hLev) then
                  Th=ThNew(i)+cap(i)*(hNew(i)-hTemp(i))/
     !              (ThSat(m)-ThR(m))
                  EpsTh=abs(ThNew(i)-Th)
                Else
                  EpsH=abs(hNew(i)-hTemp(i))
                Endif
                If(dble(max(EpsTh,EpsH)).gt.Mode6Actual) then
                  Mode6Actual=dble(max(EpsTh,EpsH))
                  Mode6Node=i
                Endif
              EndDo
              Write(*,*) 'Mode6 nonconvergence diagnostics:',
     !          ' dt=',dt,' iterations=',Iter,' hmax=',hMax,
     !          ' active_h_new_max=',Mode6HeadTol,
     !          ' active_h_prev_max=',Mode6MeasureTol,
     !          ' head_nodes=',Mode6HeadCount,
     !          ' flux_nodes=',Mode6FluxCount
              If(Mode6Node.gt.0) then
                Write(*,*) 'Mode6 max nonlinear change:',
     !            ' node=',Mode6Node,' x=',x(Mode6Node),
     !            ' y=',y(Mode6Node),
     !            ' h_new=',hNew(Mode6Node),
     !            ' h_prev=',hTemp(Mode6Node),
     !            ' error=',Mode6Actual
              Endif
              Do k=1,NumBP
                If(DripMode6FluxActive(k).eq.1) then
                  n=KXB(k)
                  QN=B_1(n)+DS(n)+
     !              F(n)*(ThNew(n)-ThOld(n))/dt
                  If(lOrt) then
                    Do j=1,IADN(n)
                      QN=QN+A_1(j,n)*hNew(IAD(j,n))
                    EndDo
                  Else
                    QN=QN+A_1(1,n)*hNew(n)
                    Do j=2,MBand
                      Mode6Node=n-j+1
                      If(Mode6Node.ge.1)
     !                  QN=QN+A_1(j,Mode6Node)*
     !                  hNew(Mode6Node)
                      Mode6Node=n+j-1
                      If(Mode6Node.le.NumNP)
     !                  QN=QN+A_1(j,n)*hNew(Mode6Node)
                    EndDo
                  Endif
                   Write(*,*) 'Mode6 Neumann residual:',
     !              ' node=',n,' prescribed=',Q(n),
     !              ' reconstructed=',QN,
     !              ' difference=',dble(QN)-dble(Q(n)),
     !              ' raw_correction=',Mode6CorrectionVector(n),
     !              ' relaxation=',Mode6Relaxation,
     !              ' continuation=',Mode6Continuation
                Endif
              EndDo
              Stop 'Mode 6 failed to converge at minimum water step'
            Endif
            Explic=.true.
            Do 617 i=1,NumNP
              hNew(i) =hOld(i)
              hTemp(i)=hOld(i)
617         Continue
            Goto 12
          Else
C
C   Save new boundary conditions If any
C
            If(DripMode6Active.eq.1) then
c A failed nonlinear solution is never used to update the Mode 6 active
c set.  Reduce the water step and restart from the emitter-only Neumann
c boundary and the last accepted water state.
              Mode6RetryCount=Mode6RetryCount+1
              DripMode6NonlinearCuts_Sum=
     !          DripMode6NonlinearCuts_Sum+1.0D0
              Call ResetMode6WaterStep(BaseHOld,hOld,hTemp)
              Do k=1,NumBP
                Mode6AtmosTrialHeadActive(k)=
     !            DripMode6AtmosHeadActive(k)
                Mode6AtmosSwitchCount(k)=0
              EndDo
              Mode6AtmosIterationCount=0
              Mode6Continuation=1.0
              Mode6ContinuationAccepted=-1.0D0
            Else
              Do i=1,NumNP
                hOld(i)=BaseHOld(i)
                hNew(i)=BaseHOld(i)
                hTemp(i)=BaseHOld(i)
              Enddo
            Endif
            dt=dmax1(dt/3.0D0,dtMin)
            dtOpt=dt
            t=tOld+dt
            goto 1111
          Endif
        Endif
      Endif
 6189 Continue
      If(DripMode6Active.eq.1.and.Mode6Continuation.lt.1.0) then
c Nonlinear flux continuation uses intermediate loads only as initial
c guesses for the same old-time state.  No time or water is accepted
c until the complete emitter flux has converged.
        Do i=1,NumNP
          Mode6BoundaryHead(i)=hNew(i)
        EndDo
        Mode6ContinuationAccepted=Mode6Continuation
        Mode6Continuation=dmin1(1.0D0,2.0D0*Mode6Continuation)
        GoTo 1111
      Endif
c
c  end of iteration loops
c
 619   Continue
      If(DripMode6Active.eq.1) then
        Mode6BoundaryActive=0
        Do k=1,NumBP
          If(DripMode6HeadActive(k).eq.1.or.
     !      DripMode6FluxActive(k).eq.1) Mode6BoundaryActive=1
        EndDo
        If(Mode6BoundaryActive.eq.1) then
c HYDRUS changes a surface-drip Neumann node to h=0 when the prescribed
c flux requires positive pressure.  The Neumann and trial Dirichlet states
c are separate nonlinear solves, each resolved only to TolH.  Require their
c sign separation to exceed the combined two-solve error band; this avoids
c binary active-set cycling without introducing a dimensional wetting
c parameter.
        Mode6HeadTol=dmax1(1.0D-8,2.0D0*dble(TolH))
        Mode6MeasureTol=1.0D-10
        Mode6LimitedClosure=0
        Mode6ActiveCount=0
        Do k=1,NumBP
          If(DripMode6CandidateOwner(k).gt.0)
     !      Mode6ActiveCount=Mode6ActiveCount+1
        EndDo
        Mode6MaxIter=20*max(1,Mode6ActiveCount)+50
        DripMode6IterationCount=DripMode6IterationCount+1
        Mode6NeedResolve=0
        Do Mode6Source=1,DripMode6Count
          Mode6Accepted(Mode6Source)=0.0D0
          Mode6Remaining(Mode6Source)=0.0D0
          Mode6FluxCapacity(Mode6Source)=0.0D0
          Mode6FluxCurrent(Mode6Source)=0.0D0
          Mode6FluxWeight(Mode6Source)=0.0D0
        EndDo
        Do k=1,NumBP
          Mode6BoundaryActual(k)=0.0D0
          Mode6Source=DripMode6BoundaryOwner(k)
          If(Mode6Source.gt.0) then
            n=KXB(k)
            Mode6BoundaryActual(k)=dble(QAct(n)-BaseQ(n)-
     !        Qautoirrig(n))
            If(DripMode6HeadActive(k).eq.1) then
c Use the signed zero-head boundary contribution.  A local outward flux is
c part of the Richards-domain balance and must increase the residual emitter
c supply assigned to the Neumann frontier; clipping it to zero closes only a
c positive-flux ledger and systematically under-supplies the soil domain.
              Mode6Accepted(Mode6Source)=
     !          Mode6Accepted(Mode6Source)+Mode6BoundaryActual(k)
            ElseIf(DripMode6FluxActive(k).eq.1) then
              Mode6FluxCurrent(Mode6Source)=
     !          Mode6FluxCurrent(Mode6Source)+
     !          dmax1(DripMode6AssignedFlux(k),0.0D0)
              Mode6FluxWeight(Mode6Source)=
     !          Mode6FluxWeight(Mode6Source)+
     !          DripMode6ContactMeasure(k)
            Endif
          Endif
        EndDo
        Do Mode6Source=1,DripMode6Count
          Mode6FluxTol=dmax1(1.0D-4,
     !      1.0D-4*dabs(DripMode6InputFlux(Mode6Source)))
 1595     Continue
          If(Mode6Accepted(Mode6Source).gt.
     !      DripMode6InputFlux(Mode6Source)+Mode6FluxTol) then
c Coupling can raise the intake of zero-head contact nodes after the active
c set changes.  Return the largest accepting head node to the Neumann set
c until the retained head set no longer exceeds the finite supply.  This
c selection depends only on the fixed contact set, never on a wetting radius.
            Mode6Bnd=0
            Mode6Actual=-1.0D30
            Do k=1,NumBP
              If(DripMode6BoundaryOwner(k).eq.Mode6Source.and.
     !          DripMode6HeadActive(k).eq.1) then
                If(Mode6BoundaryActual(k).gt.Mode6Actual) then
                  Mode6Actual=Mode6BoundaryActual(k)
                  Mode6Bnd=k
                Endif
              Endif
            EndDo
            If(Mode6Bnd.le.0) then
              Stop 'Mode 6 head set exceeds finite supply'
            Endif
            n=KXB(Mode6Bnd)
            DripMode6HeadActive(Mode6Bnd)=0
            DripMode6FluxActive(Mode6Bnd)=1
            DripMode6AssignedFlux(Mode6Bnd)=0.0D0
            Mode6Accepted(Mode6Source)=
     !        Mode6Accepted(Mode6Source)-
     !        Mode6BoundaryActual(Mode6Bnd)
            Mode6FluxWeight(Mode6Source)=
     !        Mode6FluxWeight(Mode6Source)+
     !        DripMode6ContactMeasure(Mode6Bnd)
            Mode6SourceHasLow(Mode6Source)=0
            Mode6SourceHasHigh(Mode6Source)=0
            GoTo 1595
          Endif
        EndDo
        Do Mode6Source=1,DripMode6Count
          Mode6FluxTol=dmax1(1.0D-4,
     !      1.0D-4*dabs(DripMode6InputFlux(Mode6Source)))
          If(Mode6FluxWeight(Mode6Source).gt.Mode6MeasureTol) then
c The zero-head intake depends on the simultaneous Neumann frontier load.
c Solve the scalar source closure
c
c   head_intake(frontier_flux) + frontier_flux = emitter_supply
c
c with a safeguarded bracket.  Direct fixed-point replacement of the
c frontier by supply-head_intake can oscillate for wet clay because the
c zero-head intake changes strongly with the frontier load.
            Mode6Term=Mode6Accepted(Mode6Source)+
     !        Mode6FluxCurrent(Mode6Source)-
     !        DripMode6InputFlux(Mode6Source)
            If(dabs(Mode6Term).gt.Mode6FluxTol) then
              If(Mode6Term.lt.0.0D0) then
                Mode6SourceBracketLow(Mode6Source)=
     !            Mode6FluxCurrent(Mode6Source)
                Mode6SourceHasLow(Mode6Source)=1
              Else
                Mode6SourceBracketHigh(Mode6Source)=
     !            Mode6FluxCurrent(Mode6Source)
                Mode6SourceHasHigh(Mode6Source)=1
              Endif
              If(Mode6SourceHasLow(Mode6Source).eq.1.and.
     !          Mode6SourceHasHigh(Mode6Source).eq.1) then
                Mode6Actual=0.5D0*(
     !            Mode6SourceBracketLow(Mode6Source)+
     !            Mode6SourceBracketHigh(Mode6Source))
              Else
                Mode6Actual=dmax1(
     !            DripMode6InputFlux(Mode6Source)-
     !            Mode6Accepted(Mode6Source),0.0D0)
              Endif
              Mode6FluxNodeUpdate=0
              Do k=1,NumBP
                If(DripMode6BoundaryOwner(k).eq.Mode6Source.and.
     !            DripMode6FluxActive(k).eq.1) then
                  DripShare=Mode6Actual*DripMode6ContactMeasure(k)/
     !              Mode6FluxWeight(Mode6Source)
                  If(dabs(DripMode6AssignedFlux(k)-DripShare).gt.
     !              dmax1(1.0D-10,Mode6FluxTol*
     !              DripMode6ContactMeasure(k)/
     !              Mode6FluxWeight(Mode6Source)))
     !              Mode6FluxNodeUpdate=1
                  DripMode6AssignedFlux(k)=DripShare
                Endif
              EndDo
              If(Mode6FluxNodeUpdate.eq.1) Mode6NeedResolve=1
            Else
              Mode6Accepted(Mode6Source)=
     !          Mode6Accepted(Mode6Source)+
     !          Mode6FluxCurrent(Mode6Source)
            Endif
          Endif
        EndDo
        If(Mode6NeedResolve.eq.1) then
          If(DripMode6IterationCount.lt.Mode6MaxIter) then
            Mode6Continuation=1.0D0
            Mode6ContinuationAccepted=0.0D0
            GoTo 1111
          Else
            Mode6NeedResolve=0
            Mode6LimitedClosure=1
          Endif
        Endif
        If(DripMode6IterationCount.lt.Mode6MaxIter) then
          Mode6OverAccepted=0
          Do Mode6Source=1,DripMode6Count
            If(DripMode6Closed(Mode6Source).eq.0) then
              DripMode6AcceptedFlux(Mode6Source)=
     !          Mode6Accepted(Mode6Source)
              Mode6Remaining(Mode6Source)=dmax1(
     !          DripMode6InputFlux(Mode6Source)-
     !          DripMode6AcceptedFlux(Mode6Source),0.0D0)
              DripMode6RemainingFlux(Mode6Source)=
     !          Mode6Remaining(Mode6Source)
              Mode6FluxTol=dmax1(1.0D-4,
     !          1.0D-4*dabs(DripMode6InputFlux(Mode6Source)))
              If(DripMode6AcceptedFlux(Mode6Source).gt.
     !          DripMode6InputFlux(Mode6Source)+Mode6FluxTol)
     !          Mode6OverAccepted=1
              Mode6Converted=0
              Do k=1,NumBP
                If(DripMode6BoundaryOwner(k).eq.Mode6Source.and.
     !            DripMode6FluxActive(k).eq.1) then
                  n=KXB(k)
                  If(hNew(n).gt.Mode6HeadTol) then
                    DripMode6FluxActive(k)=0
                    DripMode6HeadActive(k)=1
                    DripMode6AssignedFlux(k)=0.0D0
                    hNew(n)=0.0
                    Mode6SourceHasLow(Mode6Source)=0
                    Mode6SourceHasHigh(Mode6Source)=0
                    Mode6Converted=1
                  Endif
                Endif
              EndDo
              If(Mode6Converted.eq.1) then
                Mode6NeedResolve=1
              Else
c Every physical contact node has now satisfied complementarity.  Any
c remaining finite supply belongs to the local ponding/overflow ledger;
c no new surface node is activated.
                DripMode6Closed(Mode6Source)=1
              Endif
            Endif
          EndDo
          If(Mode6OverAccepted.eq.1) then
c The frontier is an exact Neumann boundary set by
c DripMode6AssignedFlux.  If the coupled zero-head intake changes enough
c that the already-resolved frontier plus head set exceeds finite supply,
c reject this active-set state and retry at a shorter water step.  Do not
c accept or clip the over-supplied Richards solution.
            If(Mode6RetryCount.eq.0.or.dt.le.dtMin) then
              Mode6HeadCount=0
              Mode6FluxCount=0
              Do k=1,NumBP
                If(DripMode6HeadActive(k).eq.1)
     !            Mode6HeadCount=Mode6HeadCount+1
                If(DripMode6FluxActive(k).eq.1)
     !            Mode6FluxCount=Mode6FluxCount+1
              EndDo
              Do Mode6Source=1,DripMode6Count
                Write(*,*) 'Mode6 overaccept diagnostics:',
     !            ' dt=',dt,
     !            ' input=',DripMode6InputFlux(Mode6Source),
     !            ' accepted=',DripMode6AcceptedFlux(Mode6Source),
     !            ' remaining=',Mode6Remaining(Mode6Source),
     !            ' head_nodes=',Mode6HeadCount,
     !            ' flux_nodes=',Mode6FluxCount
              EndDo
            Endif
            If(dt.le.dtMin) then
              Stop 'Mode 6 head boundary exceeded emitter supply'
            Endif
            Mode6RetryCount=Mode6RetryCount+1
            DripMode6SupplyCuts_Sum=DripMode6SupplyCuts_Sum+1.0D0
            Call ResetMode6WaterStep(BaseHOld,hOld,hTemp)
            Do k=1,NumBP
              Mode6AtmosTrialHeadActive(k)=
     !          DripMode6AtmosHeadActive(k)
              Mode6AtmosSwitchCount(k)=0
            EndDo
            Mode6AtmosIterationCount=0
            Mode6Continuation=1.0
            Mode6ContinuationAccepted=-1.0D0
            dt=dmax1(dt/3.0D0,dtMin)
            dtOpt=dt
            t=tOld+dt
            GoTo 1111
          Endif
        Else
c A finite-supply active set that reaches its iteration limit is not a
c converged water state.  Reject the step and restart from the last accepted
c state at a shorter time step, consistently with the Richards iteration.
          If(dt.le.dtMin) then
            Mode6HeadCount=0
            Mode6FluxCount=0
            Do k=1,NumBP
              If(DripMode6HeadActive(k).eq.1)
     !          Mode6HeadCount=Mode6HeadCount+1
              If(DripMode6FluxActive(k).eq.1)
     !          Mode6FluxCount=Mode6FluxCount+1
            EndDo
            Do Mode6Source=1,DripMode6Count
              Write(*,*) 'Mode6 active-set limit diagnostics:',
     !          ' dt=',dt,
     !          ' iterations=',DripMode6IterationCount,
     !          ' input=',DripMode6InputFlux(Mode6Source),
     !          ' accepted=',DripMode6AcceptedFlux(Mode6Source),
     !          ' remaining=',Mode6Remaining(Mode6Source),
     !          ' head_nodes=',Mode6HeadCount,
     !          ' flux_nodes=',Mode6FluxCount
            EndDo
            Do k=1,NumBP
              If(DripMode6BoundaryOwner(k).gt.0.and.
     !          (DripMode6HeadActive(k).eq.1.or.
     !          DripMode6FluxActive(k).eq.1)) then
                n=KXB(k)
                Write(*,*) 'Mode6 active boundary node:',
     !            ' node=',n,' h=',hNew(n),
     !            ' h_prev=',hTemp(n),
     !            ' raw_correction=',Mode6CorrectionVector(n),
     !            ' cap=',Cap(n),
     !            ' actual=',Mode6BoundaryActual(k),
     !            ' assigned=',DripMode6AssignedFlux(k),
     !            ' head=',DripMode6HeadActive(k),
     !            ' flux=',DripMode6FluxActive(k)
              Endif
            EndDo
            Stop 'Mode 6 active boundary iteration did not close'
          Endif
          Mode6RetryCount=Mode6RetryCount+1
          DripMode6SupplyCuts_Sum=DripMode6SupplyCuts_Sum+1.0D0
          Call ResetMode6WaterStep(BaseHOld,hOld,hTemp)
          Do k=1,NumBP
            Mode6AtmosTrialHeadActive(k)=
     !        DripMode6AtmosHeadActive(k)
            Mode6AtmosSwitchCount(k)=0
          EndDo
          Mode6AtmosIterationCount=0
          Mode6Continuation=1.0D0
          Mode6ContinuationAccepted=-1.0D0
          dt=dmax1(dt/3.0D0,dtMin)
          dtOpt=dt
          t=tOld+dt
          GoTo 1111
        Endif
        If(Mode6NeedResolve.eq.1) then
          Mode6Continuation=1.0D0
          Mode6ContinuationAccepted=0.0D0
          GoTo 1111
        Endif
c A converged Mode 6 step is audited with the same current theta and actual
c physical boundary fluxes returned by Newton.  No lagged SetMat or J*h
c boundary reconstruction is used.
        Call EvaluateMode6NewtonMassBalance(ThOld,Fc,dt,
     !    Mode6MassResidual,Mode6MassScale,Mode6MassRoundoff)
c Use a mixed absolute-relative criterion because the integrated relative
c scale tends to zero with dt.  The 1E-6 cm2 absolute floor is about
c 18,750 times below the independent 0.005-mm per-step validation threshold
c on HUTD06; it prevents cancellation-dominated cuts at very small dt
c without hiding a resolved mass-balance error.
        Mode6MassAbsoluteTolerance=1.0D-6
        Mode6MassTolerance=dmax1(Mode6MassAbsoluteTolerance,
     !    5.0D0*Mode6MassRoundoff+1.0D-4*Mode6MassScale)
        If(dabs(Mode6MassResidual).gt.Mode6MassTolerance) then
          If(Mode6RetryCount.lt.8) then
            Write(*,*) 'Mode6 mass retry diagnostics: dt=',dt,
     !        ' residual=',Mode6MassResidual,
     !        ' tolerance=',Mode6MassTolerance,
     !        ' scale=',Mode6MassScale
          Endif
          If(dt.le.dtMin) then
            Mode6DiagBottom=0.0D0
            Mode6DiagEmitter=0.0D0
            Mode6DiagOtherSurface=0.0D0
            Do k=1,NumBP
              n=KXB(k)
              Mode6Term=dble(QAct(n))
              If(CodeW(n).eq.-7) then
                Mode6DiagBottom=Mode6DiagBottom+Mode6Term
              ElseIf(DripMode6BoundaryOwner(k).gt.0) then
                Mode6DiagEmitter=Mode6DiagEmitter+Mode6Term
              Else
                Mode6DiagOtherSurface=Mode6DiagOtherSurface+Mode6Term
              Endif
            EndDo
            Write(*,*) 'Mode6 mass diagnostics: dt=',dt,
     !        ' residual=',Mode6MassResidual,
     !        ' tolerance=',Mode6MassTolerance,
     !        ' scale=',Mode6MassScale
            Write(*,*) 'Mode6 flux diagnostics: emitter=',
     !        Mode6DiagEmitter,' other_surface=',
     !        Mode6DiagOtherSurface,' bottom=',Mode6DiagBottom
            Stop 'Mode 6 water mass balance failed at minimum step'
          Endif
          Mode6RetryCount=Mode6RetryCount+1
          DripMode6MassCuts_Sum=DripMode6MassCuts_Sum+1.0D0
          Call ResetMode6WaterStep(BaseHOld,hOld,hTemp)
          Do k=1,NumBP
            Mode6AtmosTrialHeadActive(k)=
     !        DripMode6AtmosHeadActive(k)
            Mode6AtmosSwitchCount(k)=0
          EndDo
          Mode6AtmosIterationCount=0
          Mode6Continuation=1.0
          Mode6ContinuationAccepted=-1.0D0
          dt=dmax1(dt/3.0D0,dtMin)
          dtOpt=dt
          t=tOld+dt
          GoTo 1111
        Endif
        Do k=1,NumBP
          DripMode6AtmosHeadActive(k)=
     !      Mode6AtmosTrialHeadActive(k)
        EndDo
        Mode6HeadCount=0
        Mode6FluxCount=0
        Mode6ActiveCount=0
        Do k=1,NumBP
          If(DripMode6BoundaryOwner(k).gt.0) then
            If(DripMode6HeadActive(k).eq.1) then
              Mode6HeadCount=Mode6HeadCount+1
            Endif
            If(DripMode6FluxActive(k).eq.1) then
              Mode6FluxCount=Mode6FluxCount+1
            Endif
            If(DripMode6HeadActive(k).eq.1.or.
     !        DripMode6FluxActive(k).eq.1) then
              Mode6ActiveCount=Mode6ActiveCount+1
            Endif
          Endif
        EndDo
        Do Mode6Source=1,DripMode6Count
          DripMode6AcceptedFlux(Mode6Source)=
     !      Mode6Accepted(Mode6Source)
          DripMode6RemainingFlux(Mode6Source)=dmax1(
     !      DripMode6InputFlux(Mode6Source)-
     !      DripMode6AcceptedFlux(Mode6Source),0.0D0)
          DripInput_Flux=DripInput_Flux+
     !      DripMode6ExternalFlux(Mode6Source)*dt
          DripActualInfil_Flux=DripActualInfil_Flux+
     !      DripMode6AcceptedFlux(Mode6Source)*dt
          DripMode6Available_Flux=DripMode6Available_Flux+
     !      DripMode6InputFlux(Mode6Source)*dt
          DripMode6Accepted_Flux=DripMode6Accepted_Flux+
     !      DripMode6AcceptedFlux(Mode6Source)*dt
          DripMode6Remaining_Flux=DripMode6Remaining_Flux+
     !      DripMode6RemainingFlux(Mode6Source)*dt
          Mode6FluxTol=dmax1(1.0D-4,
     !      1.0D-4*dabs(DripMode6InputFlux(Mode6Source)))

c Close the physical source ledger after, and only after, the Richards
c state has passed Newton and mass-balance acceptance.  Solver availability
c contains reoffered ponding; external input does not.  Residual water is
c stored on the same fixed contact quadrature before any overflow is booked.
          Mode6OldStorage=DripMode6StorageStart(Mode6Source)
          Mode6AvailableVolume=Mode6OldStorage+
     !      DripMode6ExternalFlux(Mode6Source)*dt
          Mode6AcceptedVolume=
     !      DripMode6AcceptedFlux(Mode6Source)*dt
          Mode6NewStorage=Mode6AvailableVolume-Mode6AcceptedVolume
          If(Mode6NewStorage.lt.-dmax1(1.0D-10,
     !      Mode6FluxTol*dt)) then
            Stop 'Mode 6 accepted more than external plus stored water'
          Endif
          Mode6NewStorage=dmax1(Mode6NewStorage,0.0D0)
          Mode6StorageCapacity=DripMode6ContactTotal*
     !      dmax1(CriticalH,0.0D0)
          Mode6OverflowVolume=dmax1(
     !      Mode6NewStorage-Mode6StorageCapacity,0.0D0)
          Mode6NewStorage=dmin1(Mode6NewStorage,
     !      Mode6StorageCapacity)
          DripStorageChange_Flux=DripStorageChange_Flux+
     !      Mode6NewStorage-Mode6OldStorage
          DripOverflow_Flux=DripOverflow_Flux+Mode6OverflowVolume
          Do k=1,NumBP
            If(DripMode6ContactMeasure(k).gt.1.0D-12) then
              DripSurfaceStorage(k)=Mode6NewStorage*
     !          DripMode6ContactMeasure(k)/DripMode6ContactTotal
            Else
              DripSurfaceStorage(k)=0.0D0
            Endif
          EndDo
        EndDo
        DripMode6HeadNodes_Sum=DripMode6HeadNodes_Sum+
     !    dble(Mode6HeadCount)*dt
        DripMode6FluxNodes_Sum=DripMode6FluxNodes_Sum+
     !    dble(Mode6FluxCount)*dt
        DripMode6Iterations_Sum=DripMode6Iterations_Sum+
     !    dble(DripMode6IterationCount)*dt
        DripMode6StepCuts_Sum=DripMode6StepCuts_Sum+
     !    dble(Mode6RetryCount)
        DripMode6MinDt=dmin1(DripMode6MinDt,dt)
        If(Mode6LimitedClosure.eq.1) then
          DripMode6BoundaryLimit_Sum=DripMode6BoundaryLimit_Sum+dt
        Endif
        DripMode6Diag_Time=DripMode6Diag_Time+dt
      Endif
      Endif
c Apply the same discrete-domain conservation acceptance test to ordinary
c atmospheric water steps.  A recently wetted Mode 6 footprint can remain
c strongly nonlinear after the emitter event ends; accepting it on nodal
c head/theta increments alone permits a large unbalanced storage change.
      If(DripMode6Active.ne.1) then
        Call SetMat(lInput,NumNP,hNew,hOld,NMat,MatNumN,Con,Cap,
     !    BlkDn,hTemp,Explic,ThNew,hTab1,hTabN,hSat,ThSat,ThR,
     !    ThAvail,ThFull,FracOM,FracSind,FracClay,TupperLimit,
     !    TLowerLimit,soilair,SoilFile,ThAMin,ThATr)
        Call EvaluateWaterStepMassBalance(ThOld,dt,A_1,B_1,DS,F,
     !    Mode6MassResidual,Mode6MassScale,Mode6MassRoundoff)
        Mode6MassAbsoluteTolerance=1.0D-6
        Mode6MassTolerance=dmax1(Mode6MassAbsoluteTolerance,
     !    5.0D0*Mode6MassRoundoff+1.0D-4*Mode6MassScale)
        If(dabs(Mode6MassResidual).gt.Mode6MassTolerance) then
          Mode6SolverMaxIt=max(MaxIt,200)
          If(Iter.lt.Mode6SolverMaxIt) GoTo 12
          If(dt.le.dtMin) then
            Write(*,*) 'Water mass refinement failed: time=',Time,
     !        ' dt=',dt,' residual=',Mode6MassResidual,
     !        ' tolerance=',Mode6MassTolerance,' iterations=',Iter
            Stop 'Water mass balance failed after Picard refinement'
          Endif
          Mode6RetryCount=Mode6RetryCount+1
          Do i=1,NumNP
            hOld(i)=BaseHOld(i)
            hNew(i)=BaseHOld(i)
            hTemp(i)=BaseHOld(i)
          EndDo
          dt=dmax1(dt/3.0D0,dtMin)
          dtOpt=dt
          t=tOld+dt
          GoTo 1111
        Endif
c Keep the accepted atmospheric state synchronized with ordinary legacy
c Picard steps so a later Mode 6 event overlays, rather than replaces, it.
        Do k=1,NumBP
          n=KXB(k)
          If(iabs(CodeW(n)).eq.4) then
            If(CodeW(n).eq.4) then
              DripMode6AtmosHeadActive(k)=1
            Else
              DripMode6AtmosHeadActive(k)=0
            Endif
          Endif
        EndDo
      Endif
      Do 20 i=1,NumNP
        If (CodeW(i).eq.99) then
          Q(i)=0.
          CodeW(i)=0
        Endif
        If (hNew(i).eq.hCritA) hNew(i)=0.999*hCritA
20    Continue
      WaterLocalEnd=tOld+dt
      Time=WaterLocalEnd
      dtOld=dt
      Step=dt
      




c
c   Calculation of velocities
c
          
           
                         
      call Veloc(NumNP,NumEl,NumElD,hNew,x,y,KX,ListNE,Con,
     !                  ConAxx,ConAzz,ConAxz,Vx,Vz)
      If(DripMode6Active.ne.1) then
        call SetMat(lInput,NumNP,hNew,hOld,NMat,MatNumN,Con,Cap,
     !                 BlkDn, hTemp,Explic,ThNew,hTab1,hTabN,
     !                 hSat,ThSat,ThR, ThAvail,ThFull,
     !                 FracOM, FracSind, FracClay,
     !                 TupperLimit, TLowerLimit,soilair,
     !                 SoilFile,ThAMin,ThATr)
      Endif



c     
c     Final assignments
c


      Do i=1,NumNP
         hOld_1(i)=hOld(i)  !save h old and th old for runoff calculations
         ThOld_1(i)=ThOld(i)
         hOld(i) =hNew(i)  
         ThOld(i)=ThNew(i)
cdt it seems this if statement should be in the first part of this do block
c  hNew will always be the same as hOld?         
        If (CodeW(i).lt.1) then
          hTemp(i)=hNew(i)+(hNew(i)-hOld(i))*dt/dtOld
          hNew(i) =hTemp(i)
        Else
          hTemp(i)=hNew(i)
        Endif
      Enddo
      
cdt - calculate actual boundary fluxes to see what we have
      If(DripMode6Active.ne.1) then
        Do 1299 n=1,NumNP
          If (CodeW(n).gt.0.or.CodeW(n).eq.-4) then
          QN=B_1(n)+DS(n)+F(n)*(ThNew(n)-ThOld_1(n))/dt
             do 1199 j=1,IADN(n)
                QN=QN+A_1(j,n)*hNew(IAD(j,n))
 1199        continue
           QAct(n)=QN
          End if
 1299   Continue
      Endif
      Do i=1,NumNP
        WaterQIntegral(i)=WaterQIntegral(i)+dble(Q(i))*dt
        WaterQActIntegral(i)=WaterQActIntegral(i)+dble(QAct(i))*dt
        WaterVxIntegral(i)=WaterVxIntegral(i)+dble(Vx(i))*dt
        WaterVzIntegral(i)=WaterVzIntegral(i)+dble(Vz(i))*dt
      EndDo
      Call UpdateWaterMassBalance(ThOld_1,dt)

cdt - calculate available water content in root zone

      ThetaAvailRZ=0.0
      Do n=1,NumEl
		   NUS=4
		   if(KX(n,3).eq.KX(n,4)) NUS=3
		   Sum1=0.
		   Sum2=0.
c*         Loop on subelements
		   do k=1,NUS-2
			 i=KX(n,1)
			 j=KX(n,k+1)
			 l=KX(n,k+2)
			 Cii(1)=x(l)-x(j)
			 Cii(2)=x(i)-x(l)
			 Cii(3)=x(j)-x(i)
			 Bii(1)=y(j)-y(l)
			 Bii(2)=y(l)-y(i)
			 Bii(3)=y(i)-y(j)
			 AE=(Cii(3)*Bii(2)-Cii(2)*Bii(3))/2.
			 Thi=0.0
			 Thj=0.0
			 thl=0.0
			 if (rtwt(i).ge.1e-6) Thi=ThAvail(i)
			 if (rtwt(j).ge.1e-6) Thj=ThAvail(j)
			 if (rtwt(l).ge.1e-6) Thl=Thavail(l)
			 ThetaAvailRZ=ThetaAvailRZ+AE*(Thi+Thj+Thl)/3.
		   Enddo

		   
		Enddo
      



cccz start to calculate the runoff
cccz this is the water source part, i.e., the exfiltration from soil surface
c only calculate this when the surface nodes are atmospheric boundary nodes
      do k=1, NumBp
        i=KXB(k)
        if ((hnew(i).ge.CriticalH).and.(abs(codeW(i)).eq.4)
     !      .and.(Q(i).gt.0.0D0)) then
          RO(i)=max(Q(i)-Qact(i),0.0D0)
          hNew(i)=CriticalH+h_Pond(k)         ! cccz could be CriticalH_R, but we force it to 
          hOld(i)=hNew(i)
        endif
       Enddo
cccz turn this on for Ex_4 plastic mulching
cccz #ifdef EX_4P
cccz                 if (k.ge.2.and.k.le.7) then
cccz                    RO(k)=max(Q(k),0.0D0)
cccz                    hOld(k)=hNew(k)
cccz                endif
cccz #endif
cccz turn this on for Ex_4 plastic mulching

       
c CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC

      WaterSubstepCount=WaterSubstepCount+1
      WaterOuterMaxIter=max(WaterOuterMaxIter,Iter)
      WaterOuterRetryCount=WaterOuterRetryCount+Mode6RetryCount
      WaterRemaining=WaterOuterTime-WaterLocalEnd
      If(WaterRemaining.gt.WaterTimeTol) then
        WaterNextDt=dmin1(dt,WaterRemaining)
        GoTo 1100
      Endif

c Publish the synchronizer's complete interval unchanged.  Downstream
c solute/heat transport receives time-averaged hydraulic fluxes and
c velocities from all accepted internal water substeps.
      Time=WaterOuterTime
      Step=WaterOuterStep
      If(WaterOuterStep.gt.0.0D0) then
        Do i=1,NumNP
          Q(i)=sngl(WaterQIntegral(i)/WaterOuterStep)
          QAct(i)=sngl(WaterQActIntegral(i)/WaterOuterStep)
          Vx(i)=sngl(WaterVxIntegral(i)/WaterOuterStep)
          Vz(i)=sngl(WaterVzIntegral(i)/WaterOuterStep)
        EndDo
      Endif
c The legacy synchronizer thresholds (3/7) were calibrated for a
c 20-iteration water solver.  Scale the measured outer-step maximum onto
c that same workload range when stricter runs raise MaxIt (for example 200);
c this preserves the actual Picard signal without treating 7/200 iterations
c as a near-failure.  Any rejected local solve still forces a shrink signal.
      Iter=max(1,ceiling(20.0D0*dble(WaterOuterMaxIter)/
     !  dble(max(MaxIt,20))))
      If(DripMode6Active.eq.1) then
        DripMode6AdaptiveIter=Iter
        If(WaterOuterRetryCount.gt.0) DripMode6AdaptiveIter=
     !    max(DripMode6AdaptiveIter,7)
      Endif
      Return
10    Call errmes(im,il)
      Return
      End

      Subroutine AssembleMode6CurrentResidualJacobian(NumNP,NumEl,
     !  NumElD,MaxNB,hCurrent,ThetaOld,MatNum,KX,x,y,KAT,
     !  ConAxx,ConAzz,ConAxz,Fc,Q,dt,IAD,IADN,Jacobian,Residual)
c Assemble the fixed-active-set Richards residual and its consistent
c current-state Jacobian for the Mode 6 Newton solve.
      Implicit None
      Integer NumNP,NumEl,NumElD,MaxNB,KAT
      Integer MatNum(NumNP),KX(NumElD,4)
      Integer IAD(MaxNB,NumNP),IADN(NumNP)
      Real x(NumNP),y(NumNP),Q(NumNP)
      Double precision ConAxx(NumEl),ConAzz(NumEl),ConAxz(NumEl)
      Double precision Fc(NumNP)
      Double precision hCurrent(NumNP),ThetaOld(NumNP),dt
      Double precision Jacobian(MaxNB,NumNP),Residual(NumNP)
      Integer NTabD,NPar,NMatD
      Parameter (NTabD=100,NPar=13,NMatD=15)
      Double precision SoilPar,hTab,ConTab,CapTab,ConSat,TheTab,alh1,dlh
      Common /HydPar/ SoilPar(NPar,NMatD),
     !                hTab(NTabD),ConTab(NTabD,NMatD),
     !                CapTab(NTabD,NMatD),ConSat(NMatD),
     !                TheTab(NTabD,NMatD),alh1,dlh
      Double precision ConCurrent(NumNP),DCon(NumNP)
      Double precision ThetaCurrent(NumNP),DTheta(NumNP)
      Double precision BLocal(3),CLocal(3),Stiffness(3,3)
      Double precision XMultiplier,PiValue,AreaElement,MassElement
      Double precision ConductivityElement,GravityTerm,PressureGravity
      Double precision SinkSum,SinkTerm,CondI,CondJ,CondK,JacobianTerm
      Integer Nodes(3),NodeCount
      Integer i,j,e,k,LocalRow,LocalColumn,GlobalRow,GlobalColumn
      Integer Material,Slot

      PiValue=3.141592653589793238D0
      Do i=1,NumNP
        Material=MatNum(i)
        Call SetMatCurrentPoint(hCurrent(i),SoilPar(1,Material),
     !    ConCurrent(i),DCon(i),ThetaCurrent(i),DTheta(i))
        Residual(i)=0.0D0
        Do j=1,MaxNB
          Jacobian(j,i)=0.0D0
        EndDo
      EndDo

      Do e=1,NumEl
        CondI=dble(ConAxx(e))
        CondJ=dble(ConAzz(e))
        CondK=dble(ConAxz(e))
        NodeCount=4
        If(KX(e,3).eq.KX(e,4)) NodeCount=3
        Do k=1,NodeCount-2
          Nodes(1)=KX(e,1)
          Nodes(2)=KX(e,k+1)
          Nodes(3)=KX(e,k+2)
          BLocal(1)=dble(y(Nodes(2)))-dble(y(Nodes(3)))
          BLocal(2)=dble(y(Nodes(3)))-dble(y(Nodes(1)))
          BLocal(3)=dble(y(Nodes(1)))-dble(y(Nodes(2)))
          CLocal(1)=dble(x(Nodes(3)))-dble(x(Nodes(2)))
          CLocal(2)=dble(x(Nodes(1)))-dble(x(Nodes(3)))
          CLocal(3)=dble(x(Nodes(2)))-dble(x(Nodes(1)))
          AreaElement=(CLocal(3)*BLocal(2)-
     !      CLocal(2)*BLocal(3))/2.0D0
          XMultiplier=1.0D0
          If(KAT.eq.1) XMultiplier=2.0D0*PiValue*
     !      (dble(x(Nodes(1)))+dble(x(Nodes(2)))+
     !      dble(x(Nodes(3))))/3.0D0
          MassElement=XMultiplier*AreaElement/3.0D0
          ConductivityElement=(ConCurrent(Nodes(1))+
     !      ConCurrent(Nodes(2))+ConCurrent(Nodes(3)))/3.0D0
          SinkSum=dble(Fc(Nodes(1)))+dble(Fc(Nodes(2)))+
     !      dble(Fc(Nodes(3)))

          Do LocalRow=1,3
            Do LocalColumn=1,3
              Stiffness(LocalRow,LocalColumn)=XMultiplier/
     !          (4.0D0*AreaElement)*
     !          (CondI*BLocal(LocalRow)*BLocal(LocalColumn)+
     !          CondK*(BLocal(LocalRow)*CLocal(LocalColumn)+
     !          CLocal(LocalRow)*BLocal(LocalColumn))+
     !          CondJ*CLocal(LocalRow)*CLocal(LocalColumn))
            EndDo
          EndDo

          Do LocalRow=1,3
            GlobalRow=Nodes(LocalRow)
            GravityTerm=0.0D0
            If(KAT.ge.1) GravityTerm=XMultiplier/2.0D0*
     !        (CondK*BLocal(LocalRow)+CondJ*CLocal(LocalRow))
            PressureGravity=GravityTerm
            Do LocalColumn=1,3
              GlobalColumn=Nodes(LocalColumn)
              PressureGravity=PressureGravity+
     !          Stiffness(LocalRow,LocalColumn)*
     !          hCurrent(GlobalColumn)
            EndDo
            SinkTerm=XMultiplier*AreaElement/12.0D0*
     !        (SinkSum+dble(Fc(GlobalRow)))
            Residual(GlobalRow)=Residual(GlobalRow)+
     !        ConductivityElement*PressureGravity+
     !        MassElement/dt*
     !        (ThetaCurrent(GlobalRow)-ThetaOld(GlobalRow))+
     !        SinkTerm

            Do LocalColumn=1,3
              GlobalColumn=Nodes(LocalColumn)
              JacobianTerm=ConductivityElement*
     !          Stiffness(LocalRow,LocalColumn)+
     !          DCon(GlobalColumn)/3.0D0*PressureGravity
              If(LocalColumn.eq.LocalRow) JacobianTerm=JacobianTerm+
     !          MassElement/dt*DTheta(GlobalRow)
              Call Find(GlobalRow,GlobalColumn,Slot,NumNP,MaxNB,
     !          IAD,IADN)
              If(Slot.le.0) Stop 'Mode 6 Newton adjacency missing'
              Jacobian(Slot,GlobalRow)=Jacobian(Slot,GlobalRow)+
     !          JacobianTerm
            EndDo
          EndDo
        EndDo
      EndDo

      Do i=1,NumNP
        Residual(i)=Residual(i)-dble(Q(i))
      EndDo
      Return
      End

      Subroutine SolveMode6FixedActiveSetNewton(ThetaOld,Fc,Cap,
     !  ConAxx,ConAzz,ConAxz,AcceptedDt,Success,NewtonIterations,
     !  FinalResidualMax,FinalResidualSum,LastAlpha,LinearError,
     !  FailureCode,DetailedDiagnostics)
c Consistent Newton solve for one fixed Mode 6 HYDRUS activity set.
c CodeW>0 rows prescribe zero head increments.  Free rows retain the
c complete current-state physical residual and nonsymmetric Jacobian.
      Include 'public.ins'
      Include 'PuSurface.ins'
      Integer NTabD,NPar
      Parameter (NTabD=100,NPar=13)
      Double precision SoilPar,hTab,ConTab,CapTab,ConSat,TheTab,alh1,dlh
      Common /HydPar/ SoilPar(NPar,NMatD),
     !                hTab(NTabD),ConTab(NTabD,NMatD),
     !                CapTab(NTabD,NMatD),ConSat(NMatD),
     !                TheTab(NTabD,NMatD),alh1,dlh
      Double precision ThetaOld(NumNPD),Fc(NumNPD),Cap(NumNPD)
      Double precision ConAxx(NumElD),ConAzz(NumElD),ConAxz(NumElD)
      Double precision AcceptedDt,FinalResidualMax,FinalResidualSum
      Double precision LastAlpha,LinearError
      Double precision Jacobian(MBandD,NumNPD)
      Double precision PhysicalResidual(NumNPD),TrialResidual(NumNPD)
      Double precision BaseHead(NumNPD),Delta(NumNPD)
      Double precision LinearRHS(NumNPD)
      Double precision FluxTolerance,SourceTolerance,NewtonTolerance
      Double precision ResidualMax,ResidualSum,ResidualNormSquared
      Double precision TrialNormSquared,JDelta,Slope,Alpha,NextAlpha
      Double precision HalfAlpha,CandidateAlpha,BreakHead,TrialHead
      Double precision Hk,Hs
      Double precision LinearTolerance,LinearScale
      Double precision GMRESTrueResidual
      Double precision RowNormMinimum,RowNormMaximum,RowNorm
      Double precision DiagonalMinimum,DiagonalMaximum,DiagonalMagnitude
      Double precision OffDiagonalSum,DominanceMinimum,DominanceMaximum
      Double precision DominanceRatio,PreconditionedResidualMax
      Double precision ArmijoAlpha(2*NumNPD+64)
      Double precision ArmijoMerit(2*NumNPD+64)
      Double precision ArmijoBound(2*NumNPD+64)
      Double precision ConCurrent,DConCurrent,ThetaCurrent,DThetaCurrent
      Integer Success,NewtonIterations,FailureCode,DetailedDiagnostics
      Integer NewtonStep,LineSearchStep,LineSearchCount
      Integer LineSearchMaximum,TrialChanged,Accepted,Material,i,j,k,n
      Integer GMRESSuccess,GMRESIterations,GMRESRestarts,GMRESStatus
      Integer BreakNode,BreakKind

      Success=0
      FailureCode=0
      NewtonIterations=0
      FinalResidualMax=0.0D0
      FinalResidualSum=0.0D0
      LastAlpha=1.0D0
      LinearError=0.0D0
      FluxTolerance=1.0D-4
      If(DripMode6Count.gt.0) then
        FluxTolerance=1.0D300
        Do k=1,DripMode6Count
          SourceTolerance=dmax1(1.0D-4,
     !      1.0D-4*dabs(DripMode6InputFlux(k)))
          FluxTolerance=dmin1(FluxTolerance,SourceTolerance)
        EndDo
      Endif
      NewtonTolerance=0.1D0*FluxTolerance
      Do i=1,NumNP
        Delta(i)=0.0D0
      EndDo

      Do NewtonStep=0,50
        Call AssembleMode6CurrentResidualJacobian(NumNP,NumEl,NumElD,
     !    MBandD,hNew,ThetaOld,MatNumN,KX,x,y,KAT,ConAxx,ConAzz,
     !    ConAxz,Fc,Q,AcceptedDt,IAD,IADN,Jacobian,
     !    PhysicalResidual)
        ResidualMax=0.0D0
        ResidualSum=0.0D0
        ResidualNormSquared=0.0D0
        Do i=1,NumNP
          If(CodeW(i).lt.1) then
            If(PhysicalResidual(i).ne.PhysicalResidual(i).or.
     !        dabs(PhysicalResidual(i)).gt.1.0D300) then
              FailureCode=6
              GoTo 910
            Endif
            ResidualMax=dmax1(ResidualMax,dabs(PhysicalResidual(i)))
            ResidualSum=ResidualSum+dabs(PhysicalResidual(i))
            ResidualNormSquared=ResidualNormSquared+
     !        PhysicalResidual(i)*PhysicalResidual(i)
          Endif
        EndDo
        FinalResidualMax=ResidualMax
        FinalResidualSum=ResidualSum
        NewtonIterations=NewtonStep
        If(ResidualMax.le.NewtonTolerance.and.
     !    ResidualSum.le.NewtonTolerance) then
          Success=1
          GoTo 920
        Endif
        If(NewtonStep.ge.50) then
          FailureCode=5
          GoTo 910
        Endif

        Do i=1,NumNP
          BaseHead(i)=hNew(i)
          B1(i)=0.0D0
          LinearRHS(i)=-PhysicalResidual(i)
          If(CodeW(i).gt.0) then
            LinearRHS(i)=0.0D0
            Do j=1,IADN(i)
              Jacobian(j,i)=0.0D0
            EndDo
            Jacobian(IADD(i),i)=1.0D0
          Endif
        EndDo
        Call ILU(Jacobian,NumNP,MBandD,IAD,IADN,IADD,A1)
        Do i=1,NumNP
          If(A1(IADD(i),i).ne.A1(IADD(i),i).or.
     !      dabs(A1(IADD(i),i)).gt.1.0D300) then
            FailureCode=1
            GoTo 910
          Endif
        EndDo
        LinearScale=0.0D0
        Do i=1,NumNP
          If(CodeW(i).lt.1) LinearScale=dmax1(LinearScale,
     !      dabs(PhysicalResidual(i)))
        EndDo
        LinearTolerance=dmax1(1.0D-10,
     !    1.0D-8*dmax1(LinearScale,1.0D-12))

c Solve the nonsymmetric Newton system with right-preconditioned restarted
c ILU-GMRES(30).  The total Krylov budget remains the established MaxItO.
        Call SolveMode6ILUGMRES(Jacobian,LinearRHS,A1,NumNP,MBandD,
     !    NumNPD,IAD,IADN,IADD,B1,LinearTolerance,MaxItO,
     !    GMRESSuccess,GMRESIterations,GMRESRestarts,
     !    GMRESTrueResidual,GMRESStatus)
        Do i=1,NumNP
          Delta(i)=B1(i)
          If(CodeW(i).gt.0) Delta(i)=0.0D0
        EndDo

c Verify the solution against the original physical J*delta+R equation.
        LinearError=0.0D0
        Slope=0.0D0
        Do i=1,NumNP
          If(CodeW(i).lt.1) then
            JDelta=0.0D0
            Do j=1,IADN(i)
              JDelta=JDelta+Jacobian(j,i)*Delta(IAD(j,i))
            EndDo
            LinearRHS(i)=-(JDelta+PhysicalResidual(i))
            LinearError=dmax1(LinearError,
     !        dabs(JDelta+PhysicalResidual(i)))
            Slope=Slope+PhysicalResidual(i)*JDelta
          Else
            LinearRHS(i)=0.0D0
          Endif
        EndDo
        If(GMRESSuccess.ne.1.or.LinearError.gt.LinearTolerance) then
          RowNormMinimum=1.0D300
          RowNormMaximum=0.0D0
          DiagonalMinimum=1.0D300
          DiagonalMaximum=0.0D0
          DominanceMinimum=1.0D300
          DominanceMaximum=0.0D0
          Do i=1,NumNP
            If(CodeW(i).lt.1) then
              RowNorm=0.0D0
              OffDiagonalSum=0.0D0
              Do j=1,IADN(i)
                RowNorm=dmax1(RowNorm,dabs(Jacobian(j,i)))
                If(j.ne.IADD(i)) OffDiagonalSum=OffDiagonalSum+
     !            dabs(Jacobian(j,i))
              EndDo
              DiagonalMagnitude=dabs(Jacobian(IADD(i),i))
              DominanceRatio=DiagonalMagnitude/
     !          dmax1(OffDiagonalSum,1.0D-300)
              RowNormMinimum=dmin1(RowNormMinimum,RowNorm)
              RowNormMaximum=dmax1(RowNormMaximum,RowNorm)
              DiagonalMinimum=dmin1(DiagonalMinimum,DiagonalMagnitude)
              DiagonalMaximum=dmax1(DiagonalMaximum,DiagonalMagnitude)
              DominanceMinimum=dmin1(DominanceMinimum,DominanceRatio)
              DominanceMaximum=dmax1(DominanceMaximum,DominanceRatio)
            Endif
          EndDo
          Do i=1,NumNP
            B1(i)=LinearRHS(i)
          EndDo
          Call LUSOLV(NumNP,MBandD,IAD,IADN,IADD,A1,B1)
          PreconditionedResidualMax=0.0D0
          Do i=1,NumNP
            If(CodeW(i).lt.1) PreconditionedResidualMax=dmax1(
     !        PreconditionedResidualMax,dabs(B1(i)))
          EndDo
          Write(*,*) 'Mode6 Jacobian row diagnostic: norm_min=',
     !      RowNormMinimum,' norm_max=',RowNormMaximum,
     !      ' diagonal_min=',DiagonalMinimum,
     !      ' diagonal_max=',DiagonalMaximum
          Write(*,*) 'Mode6 Jacobian dominance diagnostic: ratio_min=',
     !      DominanceMinimum,' ratio_max=',DominanceMaximum,
     !      ' preconditioned_residual_max=',PreconditionedResidualMax
          Write(*,*) 'Mode6 GMRES diagnostic: status=',GMRESStatus,
     !      ' iterations=',GMRESIterations,' restarts=',GMRESRestarts,
     !      ' true_residual=',GMRESTrueResidual,
     !      ' explicit_error=',LinearError,
     !      ' tolerance=',LinearTolerance
          FailureCode=2
          GoTo 910
        Endif
        If(Slope.ge.0.0D0.or.Slope.ne.Slope) then
          FailureCode=3
          GoTo 910
        Endif

c The hydraulic law is continuous but its derivative changes at Hk and Hs.
c Enrich ordinary backtracking with every constitutive event on the Newton
c ray.  The search moves from the full step toward zero, testing the largest
c breakpoint before the next halving.  It can therefore cross several
c physical branches while never jumping over an untested derivative change.
c This is a piecewise-smooth globalization, not a head clamp: the complete
c physical residual and the unchanged Armijo condition accept every step.
        Alpha=1.0D0
        BreakNode=0
        BreakKind=0
        BreakHead=0.0D0
        Accepted=0
        LineSearchCount=0
        LineSearchMaximum=2*NumNP+60
        Do LineSearchStep=0,LineSearchMaximum
          TrialChanged=0
          Do i=1,NumNP
            If(CodeW(i).lt.1) then
              hNew(i)=BaseHead(i)+Alpha*Delta(i)
              If(hNew(i).ne.BaseHead(i)) TrialChanged=1
            Else
              hNew(i)=BaseHead(i)
            Endif
          EndDo
          If(BreakNode.gt.0) then
            hNew(BreakNode)=BreakHead
            If(hNew(BreakNode).ne.BaseHead(BreakNode))
     !        TrialChanged=1
          Endif
          If(TrialChanged.eq.0) GoTo 904
          Call AssembleMode6CurrentResidualJacobian(NumNP,NumEl,
     !      NumElD,MBandD,hNew,ThetaOld,MatNumN,KX,x,y,KAT,
     !      ConAxx,ConAzz,ConAxz,Fc,Q,AcceptedDt,IAD,IADN,
     !      Jacobian,TrialResidual)
          TrialNormSquared=0.0D0
          Do i=1,NumNP
            If(CodeW(i).lt.1) then
              If(TrialResidual(i).ne.TrialResidual(i).or.
     !          dabs(TrialResidual(i)).gt.1.0D300) then
                TrialNormSquared=1.0D300
              Else
                TrialNormSquared=TrialNormSquared+
     !            TrialResidual(i)*TrialResidual(i)
              Endif
            Endif
          EndDo
          ArmijoAlpha(LineSearchStep+1)=Alpha
          ArmijoMerit(LineSearchStep+1)=0.5D0*TrialNormSquared
          ArmijoBound(LineSearchStep+1)=0.5D0*ResidualNormSquared+
     !      1.0D-4*Alpha*Slope
          LineSearchCount=LineSearchStep+1
          If(0.5D0*TrialNormSquared.le.
     !      0.5D0*ResidualNormSquared+1.0D-4*Alpha*Slope) then
            Accepted=1
            GoTo 905
          Endif
          If(LineSearchStep.lt.LineSearchMaximum) then
            HalfAlpha=0.5D0*Alpha
            NextAlpha=HalfAlpha
            BreakNode=0
            BreakKind=0
            BreakHead=0.0D0
            Do i=1,NumNP
              If(CodeW(i).lt.1.and.Delta(i).ne.0.0D0) then
                Material=MatNumN(i)
                Call SetMatCurrentBreakpoints(SoilPar(1,Material),
     !            Hk,Hs)
                TrialHead=BaseHead(i)+Delta(i)
                If((BaseHead(i).lt.Hk.and.TrialHead.ge.Hk).or.
     !            (BaseHead(i).gt.Hk.and.TrialHead.le.Hk)) then
                  CandidateAlpha=(Hk-BaseHead(i))/Delta(i)
                  If(CandidateAlpha.gt.NextAlpha.and.
     !              CandidateAlpha.lt.Alpha) then
                    NextAlpha=CandidateAlpha
                    BreakNode=i
                    BreakKind=1
                    BreakHead=Hk
                  Endif
                Endif
                If((BaseHead(i).lt.Hs.and.TrialHead.ge.Hs).or.
     !            (BaseHead(i).gt.Hs.and.TrialHead.le.Hs)) then
                  CandidateAlpha=(Hs-BaseHead(i))/Delta(i)
                  If(CandidateAlpha.gt.NextAlpha.and.
     !              CandidateAlpha.lt.Alpha) then
                    NextAlpha=CandidateAlpha
                    BreakNode=i
                    BreakKind=2
                    BreakHead=Hs
                  Endif
                Endif
              Endif
            EndDo
            Alpha=NextAlpha
          Endif
        EndDo
 904    Continue
 905    Continue
        LastAlpha=Alpha
        If(Accepted.ne.1) then
          Do i=1,NumNP
            hNew(i)=BaseHead(i)
          EndDo
          FailureCode=4
          GoTo 910
        Endif
        If(DetailedDiagnostics.eq.1.and.LineSearchStep.eq.0.and.
     !    BreakNode.gt.0) then
          Write(*,*) 'Mode6 Newton constitutive event: node=',
     !      BreakNode,' kind=',BreakKind,' head=',BreakHead,
     !      ' alpha=',Alpha
        Endif
      EndDo

 910  Continue
      If(DetailedDiagnostics.eq.1) then
        If(FailureCode.eq.4) then
          Do LineSearchStep=1,LineSearchCount
            Write(*,*) 'Mode6 Newton Armijo diagnostic: alpha=',
     !        ArmijoAlpha(LineSearchStep),' merit0=',
     !        0.5D0*ResidualNormSquared,' merit=',
     !        ArmijoMerit(LineSearchStep),' bound=',
     !        ArmijoBound(LineSearchStep),' slope=',Slope
          EndDo
        Endif
        Call DiagnoseMode6NewtonFailure(ThetaOld,Fc,ConAxx,ConAzz,
     !    ConAxz,AcceptedDt,Delta,FailureCode)
      Endif
      Return

 920  Continue
c Reassemble at the accepted state, update every current hydraulic property,
c and recover actual flux on every boundary from the physical residual.
      Call AssembleMode6CurrentResidualJacobian(NumNP,NumEl,NumElD,
     !  MBandD,hNew,ThetaOld,MatNumN,KX,x,y,KAT,ConAxx,ConAzz,
     !  ConAxz,Fc,Q,AcceptedDt,IAD,IADN,Jacobian,PhysicalResidual)
      Do i=1,NumNP
        Material=MatNumN(i)
        Call SetMatCurrentPoint(hNew(i),SoilPar(1,Material),
     !    ConCurrent,DConCurrent,ThetaCurrent,DThetaCurrent)
        Con(i)=ConCurrent
        Cap(i)=DThetaCurrent
        ThNew(i)=ThetaCurrent
c Keep crop-facing derived water states synchronized with Newton's current
c theta without re-entering the lagged legacy SetMat path.
        soilair(i)=sngl(dmax1(dble(thSat(Material))-ThetaCurrent,
     !    1.0D-4))
        If(ThetaCurrent.lt.dble(TLowerLimit(Material))) then
          ThAvail(i)=0.0
        Else
          ThAvail(i)=sngl(dmax1(dmin1(ThetaCurrent,
     !      dble(TUpperLimit(Material)))-
     !      dble(TLowerLimit(Material)),0.0D0))
        Endif
      EndDo
      Do k=1,NumBP
        n=KXB(k)
        QAct(n)=sngl(PhysicalResidual(n)+dble(Q(n)))
      EndDo
      Return
      End

      Subroutine SolveMode6ILUGMRES(Matrix,RightHandSide,ILUFactors,
     !  NumNodes,MaxNeighbors,MaxNodes,Adjacency,AdjacencyCount,
     !  DiagonalPosition,Solution,Tolerance,MaxIterations,Success,
     !  Iterations,RestartCount,TrueResidualMax,Status)
c Right-preconditioned restarted GMRES for the Mode 6 Newton increment.
c Modified Gram-Schmidt is followed by one reorthogonalization pass.
c The unpreconditioned physical residual is recomputed after every cycle.
      Implicit None
      Integer RestartLength
      Parameter (RestartLength=30)
      Integer NumNodes,MaxNeighbors,MaxNodes,MaxIterations
      Integer Adjacency(MaxNeighbors,NumNodes),AdjacencyCount(NumNodes)
      Integer DiagonalPosition(NumNodes)
      Integer Success,Iterations,RestartCount,Status
      Double precision Matrix(MaxNeighbors,NumNodes)
      Double precision RightHandSide(NumNodes)
      Double precision ILUFactors(MaxNeighbors,NumNodes)
      Double precision Solution(NumNodes),Tolerance,TrueResidualMax
      Double precision, Allocatable :: KrylovBasis(:,:)
      Double precision, Allocatable :: PreconditionedBasis(:,:)
      Double precision, Allocatable :: Hessenberg(:,:)
      Double precision, Allocatable :: Cosine(:),Sine(:)
      Double precision, Allocatable :: GVector(:),YVector(:)
      Double precision, Allocatable :: Residual(:),Work(:)
      Double precision ResidualNorm,VectorNorm,InitialVectorNorm
      Double precision ScaleNorm,SumSquares,AbsoluteValue
      Double precision DotValue,SecondDot,Temporary,RotationScale
      Double precision RotationNorm,EstimatedResidual,BackSum
      Integer i,j,k,CycleLength,InnerIterations,HappyBreakdown

      Allocate(KrylovBasis(NumNodes,RestartLength+1))
      Allocate(PreconditionedBasis(NumNodes,RestartLength))
      Allocate(Hessenberg(RestartLength+1,RestartLength))
      Allocate(Cosine(RestartLength),Sine(RestartLength))
      Allocate(GVector(RestartLength+1),YVector(RestartLength))
      Allocate(Residual(NumNodes),Work(NumNodes))

      Success=0
      Status=1
      Iterations=0
      RestartCount=0
      TrueResidualMax=0.0D0
      Do i=1,NumNodes
        Solution(i)=0.0D0
      EndDo

 100  Continue
c Form the true unpreconditioned residual b-A*x at every restart.
      Call MATM2(Work,Matrix,Solution,NumNodes,Adjacency,
     !  AdjacencyCount,MaxNeighbors)
      TrueResidualMax=0.0D0
      ScaleNorm=0.0D0
      SumSquares=1.0D0
      Do i=1,NumNodes
        Residual(i)=RightHandSide(i)-Work(i)
        If(Residual(i).ne.Residual(i).or.
     !    dabs(Residual(i)).gt.1.0D300) then
          Status=2
          Return
        Endif
        AbsoluteValue=dabs(Residual(i))
        TrueResidualMax=dmax1(TrueResidualMax,AbsoluteValue)
        If(AbsoluteValue.gt.0.0D0) then
          If(ScaleNorm.lt.AbsoluteValue) then
            SumSquares=1.0D0+SumSquares*
     !        (ScaleNorm/AbsoluteValue)*(ScaleNorm/AbsoluteValue)
            ScaleNorm=AbsoluteValue
          Else
            SumSquares=SumSquares+
     !        (AbsoluteValue/ScaleNorm)*(AbsoluteValue/ScaleNorm)
          Endif
        Endif
      EndDo
      If(TrueResidualMax.le.Tolerance) then
        Success=1
        Status=0
        Return
      Endif
      If(Iterations.ge.MaxIterations) Return
      If(ScaleNorm.gt.0.0D0) then
        ResidualNorm=ScaleNorm*dsqrt(SumSquares)
      Else
        ResidualNorm=0.0D0
      Endif
      If(ResidualNorm.le.0.0D0.or.ResidualNorm.ne.ResidualNorm) then
        Status=2
        Return
      Endif

      RestartCount=RestartCount+1
      CycleLength=min0(RestartLength,MaxIterations-Iterations)
      Do i=1,NumNodes
        KrylovBasis(i,1)=Residual(i)/ResidualNorm
      EndDo
      Do i=1,RestartLength+1
        GVector(i)=0.0D0
      EndDo
      GVector(1)=ResidualNorm
      InnerIterations=0
      HappyBreakdown=0

      Do j=1,CycleLength
c Right preconditioning: z_j=M^{-1}*v_j, followed by w=A*z_j.
        Do i=1,NumNodes
          PreconditionedBasis(i,j)=KrylovBasis(i,j)
        EndDo
        Call LUSOLV(NumNodes,MaxNeighbors,Adjacency,AdjacencyCount,
     !    DiagonalPosition,ILUFactors,PreconditionedBasis(1,j))
        Call MATM2(Work,Matrix,PreconditionedBasis(1,j),NumNodes,
     !    Adjacency,AdjacencyCount,MaxNeighbors)

c Stable two-norm of the incoming Arnoldi vector.
        ScaleNorm=0.0D0
        SumSquares=1.0D0
        Do i=1,NumNodes
          If(Work(i).ne.Work(i).or.dabs(Work(i)).gt.1.0D300) then
            Status=2
            Return
          Endif
          AbsoluteValue=dabs(Work(i))
          If(AbsoluteValue.gt.0.0D0) then
            If(ScaleNorm.lt.AbsoluteValue) then
              SumSquares=1.0D0+SumSquares*
     !          (ScaleNorm/AbsoluteValue)*(ScaleNorm/AbsoluteValue)
              ScaleNorm=AbsoluteValue
            Else
              SumSquares=SumSquares+
     !          (AbsoluteValue/ScaleNorm)*(AbsoluteValue/ScaleNorm)
            Endif
          Endif
        EndDo
        If(ScaleNorm.gt.0.0D0) then
          InitialVectorNorm=ScaleNorm*dsqrt(SumSquares)
        Else
          InitialVectorNorm=0.0D0
        Endif

c Modified Gram-Schmidt.
        Do k=1,j
          DotValue=0.0D0
          Do i=1,NumNodes
            DotValue=DotValue+KrylovBasis(i,k)*Work(i)
          EndDo
          Hessenberg(k,j)=DotValue
          Do i=1,NumNodes
            Work(i)=Work(i)-DotValue*KrylovBasis(i,k)
          EndDo
        EndDo
c One explicit reorthogonalization pass.
        Do k=1,j
          SecondDot=0.0D0
          Do i=1,NumNodes
            SecondDot=SecondDot+KrylovBasis(i,k)*Work(i)
          EndDo
          Hessenberg(k,j)=Hessenberg(k,j)+SecondDot
          Do i=1,NumNodes
            Work(i)=Work(i)-SecondDot*KrylovBasis(i,k)
          EndDo
        EndDo

        ScaleNorm=0.0D0
        SumSquares=1.0D0
        Do i=1,NumNodes
          AbsoluteValue=dabs(Work(i))
          If(AbsoluteValue.gt.0.0D0) then
            If(ScaleNorm.lt.AbsoluteValue) then
              SumSquares=1.0D0+SumSquares*
     !          (ScaleNorm/AbsoluteValue)*(ScaleNorm/AbsoluteValue)
              ScaleNorm=AbsoluteValue
            Else
              SumSquares=SumSquares+
     !          (AbsoluteValue/ScaleNorm)*(AbsoluteValue/ScaleNorm)
            Endif
          Endif
        EndDo
        If(ScaleNorm.gt.0.0D0) then
          VectorNorm=ScaleNorm*dsqrt(SumSquares)
        Else
          VectorNorm=0.0D0
        Endif
        Hessenberg(j+1,j)=VectorNorm
        If(VectorNorm.le.1.0D-14*
     !    dmax1(InitialVectorNorm,1.0D-300)) then
          Hessenberg(j+1,j)=0.0D0
          HappyBreakdown=1
        Else
          Do i=1,NumNodes
            KrylovBasis(i,j+1)=Work(i)/VectorNorm
          EndDo
        Endif

c Apply prior Givens rotations to the new Hessenberg column.
        Do k=1,j-1
          Temporary=Cosine(k)*Hessenberg(k,j)+
     !      Sine(k)*Hessenberg(k+1,j)
          Hessenberg(k+1,j)=-Sine(k)*Hessenberg(k,j)+
     !      Cosine(k)*Hessenberg(k+1,j)
          Hessenberg(k,j)=Temporary
        EndDo
c Construct a stable new Givens rotation.
        RotationScale=dmax1(dabs(Hessenberg(j,j)),
     !    dabs(Hessenberg(j+1,j)))
        If(RotationScale.le.0.0D0) then
          Cosine(j)=1.0D0
          Sine(j)=0.0D0
        Else
          RotationNorm=RotationScale*dsqrt(
     !      (Hessenberg(j,j)/RotationScale)*
     !      (Hessenberg(j,j)/RotationScale)+
     !      (Hessenberg(j+1,j)/RotationScale)*
     !      (Hessenberg(j+1,j)/RotationScale))
          Cosine(j)=Hessenberg(j,j)/RotationNorm
          Sine(j)=Hessenberg(j+1,j)/RotationNorm
        Endif
        Hessenberg(j,j)=Cosine(j)*Hessenberg(j,j)+
     !    Sine(j)*Hessenberg(j+1,j)
        Hessenberg(j+1,j)=0.0D0
        Temporary=Cosine(j)*GVector(j)+Sine(j)*GVector(j+1)
        GVector(j+1)=-Sine(j)*GVector(j)+
     !    Cosine(j)*GVector(j+1)
        GVector(j)=Temporary
        EstimatedResidual=dabs(GVector(j+1))
        Iterations=Iterations+1
        InnerIterations=j
        If(EstimatedResidual.le.Tolerance.or.HappyBreakdown.eq.1) Exit
      EndDo

c Solve the small upper-triangular least-squares system.
      Do j=1,InnerIterations
        YVector(j)=0.0D0
      EndDo
      Do j=InnerIterations,1,-1
        If(dabs(Hessenberg(j,j)).le.1.0D-300.or.
     !    Hessenberg(j,j).ne.Hessenberg(j,j)) then
          Status=2
          Return
        Endif
        BackSum=0.0D0
        Do k=j+1,InnerIterations
          BackSum=BackSum+Hessenberg(j,k)*YVector(k)
        EndDo
        YVector(j)=(GVector(j)-BackSum)/Hessenberg(j,j)
      EndDo
      Do j=1,InnerIterations
        Do i=1,NumNodes
          Solution(i)=Solution(i)+
     !      PreconditionedBasis(i,j)*YVector(j)
        EndDo
      EndDo
      GoTo 100
      End

      Subroutine DiagnoseMode6NewtonFailure(ThetaOld,Fc,ConAxx,
     !  ConAzz,ConAxz,AcceptedDt,Delta,FailureCode)
c Read-only mathematical diagnostics at the rejected fixed-active-set state.
      Include 'public.ins'
      Include 'PuSurface.ins'
      Integer NTabD,NPar
      Parameter (NTabD=100,NPar=13)
      Double precision SoilPar,hTab,ConTab,CapTab,ConSat,TheTab,alh1,dlh
      Common /HydPar/ SoilPar(NPar,NMatD),
     !                hTab(NTabD),ConTab(NTabD,NMatD),
     !                CapTab(NTabD,NMatD),ConSat(NMatD),
     !                TheTab(NTabD,NMatD),alh1,dlh
      Double precision ThetaOld(NumNPD),Fc(NumNPD),AcceptedDt
      Double precision ConAxx(NumElD),ConAzz(NumElD),ConAxz(NumElD)
      Double precision Delta(NumNPD),Jacobian(MBandD,NumNPD)
      Double precision BaseHead(NumNPD),ResidualBase(NumNPD)
      Double precision ResidualPlus(NumNPD),ResidualMinus(NumNPD)
      Double precision JacobianDelta(NumNPD)
      Double precision ResidualMax,ResidualSum,DeltaMax,FDEpsilon
      Double precision FDValue,JVError,JVScale,JVRelative
      Double precision ConCurrent,DConCurrent,ThetaCurrent,DThetaCurrent
      Double precision Qs,Qa,Qm,Alfa,ExponentN,ExponentM,Qees,Qeek,Hs,Hk
      Double precision TrialHead
      Integer FailureCode,ResidualNode,DeltaNode,JVNode,Material
      Integer CrossHkCount,CrossHsCount,CrossHkMax,CrossHsMax
      Integer HeadCount,FluxCount,i,j,k,n

      Do i=1,NumNP
        BaseHead(i)=hNew(i)
      EndDo
      Call AssembleMode6CurrentResidualJacobian(NumNP,NumEl,NumElD,
     !  MBandD,hNew,ThetaOld,MatNumN,KX,x,y,KAT,ConAxx,ConAzz,
     !  ConAxz,Fc,Q,AcceptedDt,IAD,IADN,Jacobian,ResidualBase)
      ResidualMax=0.0D0
      ResidualSum=0.0D0
      ResidualNode=0
      DeltaMax=0.0D0
      DeltaNode=0
      CrossHkCount=0
      CrossHsCount=0
      CrossHkMax=0
      CrossHsMax=0
      Do i=1,NumNP
        If(CodeW(i).lt.1) then
          ResidualSum=ResidualSum+dabs(ResidualBase(i))
          If(dabs(ResidualBase(i)).gt.ResidualMax) then
            ResidualMax=dabs(ResidualBase(i))
            ResidualNode=i
          Endif
          If(dabs(Delta(i)).gt.DeltaMax) then
            DeltaMax=dabs(Delta(i))
            DeltaNode=i
          Endif
          Material=MatNumN(i)
          Qs=SoilPar(2,Material)
          Qa=SoilPar(3,Material)
          Qm=SoilPar(4,Material)
          Alfa=SoilPar(5,Material)
          ExponentN=SoilPar(6,Material)
          ExponentM=1.0D0-1.0D0/ExponentN
          Qees=dmin1((Qs-Qa)/(Qm-Qa),0.999999999999999D0)
          Qeek=dmin1((SoilPar(9,Material)-Qa)/(Qm-Qa),Qees)
          Hs=-1.0D0/Alfa*
     !      (Qees**(-1.0D0/ExponentM)-1.0D0)**
     !      (1.0D0/ExponentN)
          Hk=-1.0D0/Alfa*
     !      (Qeek**(-1.0D0/ExponentM)-1.0D0)**
     !      (1.0D0/ExponentN)
          TrialHead=BaseHead(i)+Delta(i)
          If((BaseHead(i)-Hk)*(TrialHead-Hk).le.0.0D0.and.
     !      BaseHead(i).ne.TrialHead) CrossHkCount=CrossHkCount+1
          If((BaseHead(i)-Hs)*(TrialHead-Hs).le.0.0D0.and.
     !      BaseHead(i).ne.TrialHead) CrossHsCount=CrossHsCount+1
        Endif
      EndDo
      If(DeltaNode.gt.0) then
        Material=MatNumN(DeltaNode)
        Qs=SoilPar(2,Material)
        Qa=SoilPar(3,Material)
        Qm=SoilPar(4,Material)
        Alfa=SoilPar(5,Material)
        ExponentN=SoilPar(6,Material)
        ExponentM=1.0D0-1.0D0/ExponentN
        Qees=dmin1((Qs-Qa)/(Qm-Qa),0.999999999999999D0)
        Qeek=dmin1((SoilPar(9,Material)-Qa)/(Qm-Qa),Qees)
        Hs=-1.0D0/Alfa*
     !    (Qees**(-1.0D0/ExponentM)-1.0D0)**
     !    (1.0D0/ExponentN)
        Hk=-1.0D0/Alfa*
     !    (Qeek**(-1.0D0/ExponentM)-1.0D0)**
     !    (1.0D0/ExponentN)
        TrialHead=BaseHead(DeltaNode)+Delta(DeltaNode)
        If((BaseHead(DeltaNode)-Hk)*(TrialHead-Hk).le.0.0D0.and.
     !    BaseHead(DeltaNode).ne.TrialHead) CrossHkMax=1
        If((BaseHead(DeltaNode)-Hs)*(TrialHead-Hs).le.0.0D0.and.
     !    BaseHead(DeltaNode).ne.TrialHead) CrossHsMax=1
      Endif
      HeadCount=0
      FluxCount=0
      Do k=1,NumBP
        If(DripMode6HeadActive(k).eq.1) HeadCount=HeadCount+1
        If(DripMode6FluxActive(k).eq.1) FluxCount=FluxCount+1
      EndDo
      Write(*,*) 'Mode6 Newton rejected-state diagnostic: time=',Time,
     !  ' dt=',AcceptedDt,' code=',FailureCode,' head_nodes=',HeadCount,
     !  ' flux_nodes=',FluxCount,' residual_max=',ResidualMax,
     !  ' residual_sum=',ResidualSum
      If(ResidualNode.gt.0) then
        Material=MatNumN(ResidualNode)
        Call SetMatCurrentPoint(hNew(ResidualNode),
     !    SoilPar(1,Material),ConCurrent,DConCurrent,ThetaCurrent,
     !    DThetaCurrent)
        Qs=SoilPar(2,Material)
        Qa=SoilPar(3,Material)
        Qm=SoilPar(4,Material)
        Alfa=SoilPar(5,Material)
        ExponentN=SoilPar(6,Material)
        ExponentM=1.0D0-1.0D0/ExponentN
        Qees=dmin1((Qs-Qa)/(Qm-Qa),0.999999999999999D0)
        Qeek=dmin1((SoilPar(9,Material)-Qa)/(Qm-Qa),Qees)
        Hs=-1.0D0/Alfa*
     !    (Qees**(-1.0D0/ExponentM)-1.0D0)**
     !    (1.0D0/ExponentN)
        Hk=-1.0D0/Alfa*
     !    (Qeek**(-1.0D0/ExponentM)-1.0D0)**
     !    (1.0D0/ExponentN)
        Write(*,*) 'Mode6 Newton max residual node: node=',
     !    ResidualNode,' x=',x(ResidualNode),' y=',y(ResidualNode),
     !    ' h=',hNew(ResidualNode),' theta=',ThetaCurrent,
     !    ' K=',ConCurrent,' dtheta=',DThetaCurrent,
     !    ' dK=',DConCurrent,' Hk=',Hk,' Hs=',Hs
      Endif
      If(DeltaNode.gt.0) then
        Write(*,*) 'Mode6 Newton max delta node: node=',DeltaNode,
     !    ' x=',x(DeltaNode),' y=',y(DeltaNode),
     !    ' h=',BaseHead(DeltaNode),' delta=',Delta(DeltaNode),
     !    ' cross_Hk=',CrossHkMax,' cross_Hs=',CrossHsMax,
     !    ' all_cross_Hk=',CrossHkCount,
     !    ' all_cross_Hs=',CrossHsCount
      Endif

      If(FailureCode.ge.2.and.FailureCode.le.4.and.
     !  DeltaMax.gt.0.0D0) then
        Do i=1,NumNP
          JacobianDelta(i)=0.0D0
          If(CodeW(i).lt.1) then
            Do j=1,IADN(i)
              JacobianDelta(i)=JacobianDelta(i)+
     !          Jacobian(j,i)*Delta(IAD(j,i))
            EndDo
          Endif
        EndDo
        FDEpsilon=1.0D-6/dmax1(DeltaMax,1.0D-30)
        Do i=1,NumNP
          If(CodeW(i).lt.1) hNew(i)=BaseHead(i)+FDEpsilon*Delta(i)
        EndDo
        Call AssembleMode6CurrentResidualJacobian(NumNP,NumEl,
     !    NumElD,MBandD,hNew,ThetaOld,MatNumN,KX,x,y,KAT,
     !    ConAxx,ConAzz,ConAxz,Fc,Q,AcceptedDt,IAD,IADN,
     !    Jacobian,ResidualPlus)
        Do i=1,NumNP
          If(CodeW(i).lt.1) hNew(i)=BaseHead(i)-FDEpsilon*Delta(i)
        EndDo
        Call AssembleMode6CurrentResidualJacobian(NumNP,NumEl,
     !    NumElD,MBandD,hNew,ThetaOld,MatNumN,KX,x,y,KAT,
     !    ConAxx,ConAzz,ConAxz,Fc,Q,AcceptedDt,IAD,IADN,
     !    Jacobian,ResidualMinus)
        JVError=0.0D0
        JVScale=0.0D0
        JVNode=0
        Do i=1,NumNP
          hNew(i)=BaseHead(i)
          If(CodeW(i).lt.1) then
            FDValue=(ResidualPlus(i)-ResidualMinus(i))/
     !        (2.0D0*FDEpsilon)
            If(dabs(FDValue-JacobianDelta(i)).gt.JVError) then
              JVError=dabs(FDValue-JacobianDelta(i))
              JVNode=i
            Endif
            JVScale=dmax1(JVScale,dabs(FDValue),
     !        dabs(JacobianDelta(i)))
          Endif
        EndDo
        JVRelative=JVError/dmax1(JVScale,1.0D-30)
        Write(*,*) 'Mode6 Newton Jv diagnostic: epsilon=',FDEpsilon,
     !    ' error=',JVError,' relative=',JVRelative,' node=',JVNode
      Endif
      Return
      End

      Subroutine EvaluateMode6NewtonMassBalance(ThetaPrevious,Fc,
     !  AcceptedDt,MassResidual,MassScale,MassRoundoffSigma)
c Audit Mode 6 with Newton's current theta and actual physical QAct fluxes.
      Include 'public.ins'
      Include 'PuSurface.ins'
      Double precision ThetaPrevious(NumNPD),Fc(NumNPD),AcceptedDt
      Double precision MassResidual,MassScale,MassRoundoffSigma
      Double precision PreviousStorage,CurrentStorage,SinkIntegral
      Double precision StorageVariance,SinkVariance,FluxVariance
      Double precision NetFlux,FluxMagnitude,ActualFlux,FluxSpacing
      Double precision TriangleArea,XMultiplier,PiValue

      Call IntegrateWaterDomain(ThetaPrevious,ThNew,PreviousStorage,
     !  CurrentStorage,SinkIntegral)
      Call EvaluateWaterRoundoff(ThetaPrevious,ThNew,StorageVariance,
     !  SinkVariance)
      SinkIntegral=0.0D0
      PiValue=3.141592653589793238D0
      Do e=1,NumEl
        NUS=4
        If(KX(e,3).eq.KX(e,4)) NUS=3
        Do k=1,NUS-2
          i=KX(e,1)
          j=KX(e,k+1)
          l=KX(e,k+2)
          TriangleArea=((dble(x(j))-dble(x(i)))*
     !      (dble(y(l))-dble(y(i)))-
     !      (dble(x(l))-dble(x(i)))*
     !      (dble(y(j))-dble(y(i))))/2.0D0
          XMultiplier=1.0D0
          If(KAT.eq.1) XMultiplier=2.0D0*PiValue*
     !      (dble(x(i))+dble(x(j))+dble(x(l)))/3.0D0
          SinkIntegral=SinkIntegral+TriangleArea*XMultiplier*
     !      (Fc(i)+Fc(j)+Fc(l))/3.0D0
        EndDo
      EndDo
      NetFlux=0.0D0
      FluxMagnitude=0.0D0
      FluxVariance=0.0D0
      Do k=1,NumBP
        n=KXB(k)
        ActualFlux=dble(QAct(n))
        NetFlux=NetFlux+ActualFlux
        FluxMagnitude=FluxMagnitude+dabs(ActualFlux)
        FluxSpacing=dble(spacing(QAct(n)))
        FluxVariance=FluxVariance+
     !    (AcceptedDt*FluxSpacing)**2/12.0D0
      EndDo
      MassResidual=(CurrentStorage-PreviousStorage)-
     !  AcceptedDt*(NetFlux-SinkIntegral)
      MassScale=dabs(CurrentStorage-PreviousStorage)+
     !  AcceptedDt*(FluxMagnitude+dabs(SinkIntegral))
      MassRoundoffSigma=dsqrt(dmax1(StorageVariance+
     !  AcceptedDt**2*SinkVariance+FluxVariance,0.0D0))
      Return
      End

      Subroutine InitializeWaterMassBalance()
      Include 'public.ins'
      Double precision Storage,PreviousStorage,SinkIntegral

      Call IntegrateWaterDomain(ThNew,ThNew,PreviousStorage,Storage,
     !  SinkIntegral)
      WaterMBInitialStorage=Storage
      WaterMBCurrentStorage=Storage
      WaterMBCumulativeIn=0.0D0
      WaterMBCumulativeOut=0.0D0
      WaterMBCumulativeSink=0.0D0
      WaterMBCumulativeResidual=0.0D0
      WaterMBMaxStepResidual=0.0D0
      WaterMBAcceptedSteps=0
      WaterMBInitialized=1
      Return
      End

      Subroutine UpdateWaterMassBalance(ThPrevious,AcceptedDt)
      Include 'public.ins'
      Include 'PuSurface.ins'
       Double precision ThPrevious(NumNPD)
      Double precision AcceptedDt,PreviousStorage,CurrentStorage,
     !  StepIn,StepOut,StepSink,BoundaryFlux,StepResidual,SinkIntegral

      If(WaterMBInitialized.ne.1) Call InitializeWaterMassBalance()
      StepIn=0.0D0
      StepOut=0.0D0
      Call IntegrateWaterDomain(ThPrevious,ThNew,PreviousStorage,
     !  CurrentStorage,SinkIntegral)
      StepSink=SinkIntegral*AcceptedDt
      Do k=1,NumBP
        n=KXB(k)
c QAct is the converged soil flux for prescribed-head boundaries.  Flux
c boundaries retain Q.  Positive flux is into the soil.
        If(DripMode6Active.eq.1) then
          BoundaryFlux=dble(QAct(n))
        ElseIf(CodeW(n).gt.0) then
          BoundaryFlux=dble(QAct(n))
        Else
          BoundaryFlux=dble(Q(n))
        Endif
        StepIn=StepIn+dmax1(BoundaryFlux,0.0D0)*AcceptedDt
        StepOut=StepOut+dmax1(-BoundaryFlux,0.0D0)*AcceptedDt
      EndDo
      StepResidual=(CurrentStorage-PreviousStorage)-
     !  (StepIn-StepOut-StepSink)
      WaterMBCurrentStorage=CurrentStorage
      WaterMBCumulativeIn=WaterMBCumulativeIn+StepIn
      WaterMBCumulativeOut=WaterMBCumulativeOut+StepOut
      WaterMBCumulativeSink=WaterMBCumulativeSink+StepSink
      WaterMBCumulativeResidual=
     !  (WaterMBCurrentStorage-WaterMBInitialStorage)-
     !  (WaterMBCumulativeIn-WaterMBCumulativeOut-
     !  WaterMBCumulativeSink)
      WaterMBMaxStepResidual=dmax1(WaterMBMaxStepResidual,
     !  dabs(StepResidual))
      WaterMBAcceptedSteps=WaterMBAcceptedSteps+1
      Return
      End

      Subroutine EvaluateWaterStepMassBalance(ThetaPrevious,AcceptedDt,
     !  AMass,BMass,DSMass,FMass,MassResidual,MassScale,
     !  MassRoundoffSigma)
      Include 'public.ins'
      Include 'PuSurface.ins'
       Double precision ThetaPrevious(NumNPD),DSMass(NumNPD),
     !                  FMass(NumNPD)
      Double precision AcceptedDt,AMass(MBandD,NumNPD),
     !  BMass(NumNPD),MassResidual,MassScale,MassRoundoffSigma,
     !  PreviousStorage,
     !  CurrentStorage,SinkIntegral,NetFlux,FluxMagnitude,ActualFlux,
     !  StepStorageChange,StorageVariance,SinkVariance,FluxVariance,
     !  FluxSpacing,FEMStorageChange,FEMSinkIntegral

      Call IntegrateWaterDomain(ThetaPrevious,ThNew,PreviousStorage,
     !  CurrentStorage,SinkIntegral)
      Call EvaluateWaterRoundoff(ThetaPrevious,ThNew,StorageVariance,
     !  SinkVariance)
      NetFlux=0.0D0
      FluxMagnitude=0.0D0
      FluxVariance=0.0D0
      Do k=1,NumBP
        n=KXB(k)
        If(CodeW(n).gt.0) then
          ActualFlux=BMass(n)+dble(DSMass(n))+
     !      dble(FMass(n))*
     !      dble(ThNew(n)-ThetaPrevious(n))/AcceptedDt
          If(lOrt) then
            Do j=1,IADN(n)
              ActualFlux=ActualFlux+
     !          AMass(j,n)*dble(hNew(IAD(j,n)))
            EndDo
          Else
            ActualFlux=ActualFlux+AMass(1,n)*dble(hNew(n))
            Do j=2,MBand
              m=n-j+1
              If(m.ge.1) ActualFlux=ActualFlux+
     !          AMass(j,m)*dble(hNew(m))
              m=n+j-1
              If(m.le.NumNP) ActualFlux=ActualFlux+
     !          AMass(j,n)*dble(hNew(m))
            EndDo
          Endif
        Else
          ActualFlux=dble(Q(n))
        Endif
        FluxSpacing=dble(spacing(sngl(ActualFlux)))
        FluxVariance=FluxVariance+
     !    (AcceptedDt*FluxSpacing)**2/12.0D0
        NetFlux=NetFlux+ActualFlux
        FluxMagnitude=FluxMagnitude+dabs(ActualFlux)
      EndDo
      FEMStorageChange=0.0D0
      FEMSinkIntegral=0.0D0
      Do i=1,NumNP
c Use the same lumped water-capacity weights and assembled sink vector as
c the discrete Richards equation.  The independent triangle integration
c remains in WaterMassBalance.out as the external domain-scale audit.
        FEMStorageChange=FEMStorageChange+
     !    FMass(i)*(ThNew(i)-ThetaPrevious(i))
        FEMSinkIntegral=FEMSinkIntegral+DSMass(i)
      EndDo
      StepStorageChange=CurrentStorage-PreviousStorage
      MassResidual=FEMStorageChange-
     !  AcceptedDt*(NetFlux-FEMSinkIntegral)
      MassScale=dabs(FEMStorageChange)+
     !  AcceptedDt*(FluxMagnitude+dabs(FEMSinkIntegral))
      MassRoundoffSigma=dsqrt(dmax1(StorageVariance+
     !  AcceptedDt**2*SinkVariance+FluxVariance,0.0D0))
      Return
      End

      Subroutine EvaluateWaterRoundoff(ThetaPrevious,ThetaCurrent,
     !  StorageVariance,SinkVariance)
      Include 'public.ins'
       Double precision ThetaPrevious(NumNPD),ThetaCurrent(NumNPD)
      Double precision NodeWeight(NumNPD),StorageVariance,SinkVariance,
     !  TriangleArea,XMultiplier,PiValue,Weight,SpacingOld,
     !  SpacingCurrent,SpacingSink

      Do i=1,NumNP
        NodeWeight(i)=0.0D0
      EndDo
      PiValue=3.141592653589793238D0
      Do e=1,NumEl
        NUS=4
        If(KX(e,3).eq.KX(e,4)) NUS=3
        Do k=1,NUS-2
          i=KX(e,1)
          j=KX(e,k+1)
          l=KX(e,k+2)
          TriangleArea=((dble(x(j))-dble(x(i)))*
     !      (dble(y(l))-dble(y(i)))-
     !      (dble(x(l))-dble(x(i)))*
     !      (dble(y(j))-dble(y(i))))/2.0D0
          XMultiplier=1.0D0
          If(KAT.eq.1) XMultiplier=2.0D0*PiValue*
     !      (dble(x(i))+dble(x(j))+dble(x(l)))/3.0D0
          Weight=TriangleArea*XMultiplier/3.0D0
          NodeWeight(i)=NodeWeight(i)+Weight
          NodeWeight(j)=NodeWeight(j)+Weight
          NodeWeight(l)=NodeWeight(l)+Weight
        EndDo
      EndDo
      StorageVariance=0.0D0
      SinkVariance=0.0D0
      Do i=1,NumNP
        SpacingOld=spacing(ThetaPrevious(i))
        SpacingCurrent=spacing(ThetaCurrent(i))
        SpacingSink=dble(spacing(Sink(i)))
        StorageVariance=StorageVariance+NodeWeight(i)**2*
     !    (SpacingOld**2+SpacingCurrent**2)/12.0D0
        SinkVariance=SinkVariance+NodeWeight(i)**2*
     !    SpacingSink**2/12.0D0
      EndDo
      Return
      End

      Subroutine IntegrateWaterDomain(ThetaPrevious,ThetaCurrent,
     !  PreviousStorage,CurrentStorage,SinkIntegral)
      Include 'public.ins'
       Double precision ThetaPrevious(NumNPD),ThetaCurrent(NumNPD)
      Double precision PreviousStorage,CurrentStorage,SinkIntegral,
     !  TriangleArea,XMultiplier,PiValue

      PreviousStorage=0.0D0
      CurrentStorage=0.0D0
      SinkIntegral=0.0D0
      PiValue=3.141592653589793238D0
      Do e=1,NumEl
        NUS=4
        If(KX(e,3).eq.KX(e,4)) NUS=3
        Do k=1,NUS-2
          i=KX(e,1)
          j=KX(e,k+1)
          l=KX(e,k+2)
          TriangleArea=((dble(x(j))-dble(x(i)))*
     !      (dble(y(l))-dble(y(i)))-
     !      (dble(x(l))-dble(x(i)))*
     !      (dble(y(j))-dble(y(i))))/2.0D0
          XMultiplier=1.0D0
          If(KAT.eq.1) XMultiplier=2.0D0*PiValue*
     !      (dble(x(i))+dble(x(j))+dble(x(l)))/3.0D0
          PreviousStorage=PreviousStorage+TriangleArea*XMultiplier*
     !      (dble(ThetaPrevious(i))+dble(ThetaPrevious(j))+
     !      dble(ThetaPrevious(l)))/3.0D0
          CurrentStorage=CurrentStorage+TriangleArea*XMultiplier*
     !      (dble(ThetaCurrent(i))+dble(ThetaCurrent(j))+
     !      dble(ThetaCurrent(l)))/3.0D0
          SinkIntegral=SinkIntegral+TriangleArea*XMultiplier*
     !      (dble(Sink(i))+dble(Sink(j))+dble(Sink(l)))/3.0D0
        EndDo
      EndDo
      Return
      End
c*
      Subroutine ResetMode6WaterStep(BaseHOld,hOld,hTemp)
      Include 'public.ins'
      Include 'PuSurface.ins'
       Double precision BaseHOld(NumNPD),hOld(NumNPD),hTemp(NumNPD)
      Double Precision Mode6FluxTol

      DripMode6IterationCount=0
      Do i=1,NumNP
        hOld(i)=BaseHOld(i)
        hNew(i)=BaseHOld(i)
        hTemp(i)=BaseHOld(i)
      EndDo
      Do k=1,NumBP
        DripMode6AssignedFlux(k)=0.0D0
        DripMode6FluxActive(k)=0
        DripMode6HeadActive(k)=0
        DripMode6BoundaryOwner(k)=0
      EndDo
      Do i=1,DripMode6Count
        DripMode6AcceptedFlux(i)=0.0D0
        DripMode6RemainingFlux(i)=DripMode6InputFlux(i)
        Mode6FluxTol=dmax1(1.0D-4,
     !    1.0D-4*dabs(DripMode6InputFlux(i)))
        If(DripMode6InputFlux(i).gt.Mode6FluxTol) then
          DripMode6Closed(i)=0
          Do k=1,NumBP
            If(DripMode6ContactMeasure(k).gt.1.0D-12) then
              DripMode6FluxActive(k)=1
              DripMode6AssignedFlux(k)=DripMode6InputFlux(i)*
     !          DripMode6ContactMeasure(k)/DripMode6ContactTotal
              DripMode6BoundaryOwner(k)=i
            Endif
          EndDo
        Else
          DripMode6Closed(i)=1
        Endif
      EndDo
      Return
      End
c*
      subroutine Veloc(NumNP,NumEl,NumElD,hNew,x,y,KX,ListNE,Con,ConAxx,
     !                 ConAzz,ConAxz,Vx,Vz)
      Double precision hNew,Con,ConAxx,ConAzz,ConAxz
      Dimension hNew(NumNP),x(NumNP),y(NumNP),ListNE(NumNP),Con(NumNP),
     !          KX(NumElD,4),Vx(NumNP),Vz(NumNP),ConAxx(NumEl),
     !          ConAzz(NumEl),ConAxz(NumEl),List(3)
      Integer e
      Do 11 i=1,NumNP
        Vx(i)=0.
        Vz(i)=0.
11    Continue    
      Do 14 e=1,NumEl
        CAxx=ConAxx(e)
        CAzz=ConAzz(e)
        CAxz=ConAxz(e)
        NCorn=4
        If(KX(e,3).eq.KX(e,4)) NCorn=3
        Do 13 n=1,NCorn-2
          i=KX(e,1)
          j=KX(e,n+1)
          k=KX(e,n+2)
          List(1)=i
          List(2)=j
          List(3)=k
          vi=y(j)-y(k)
          vj=y(k)-y(i)
          vk=y(i)-y(j)
          wi=x(k)-x(j)
          wj=x(i)-x(k)
          wk=x(j)-x(i)
          Area=.5*(wk*vj-wj*vk)
          A=1./Area/2.
          Ai=CAxx*vi+CAxz*wi
          Aj=CAxx*vj+CAxz*wj
          Ak=CAxx*vk+CAxz*wk  
          Vxx=A*(Ai*hNew(i)+Aj*hNew(j)+Ak*hNew(k))+CAxz
          Ai=CAxz*vi+CAzz*wi
          Aj=CAxz*vj+CAzz*wj
          Ak=CAxz*vk+CAzz*wk
          Vzz=A*(Ai*hNew(i)+Aj*hNew(j)+Ak*hNew(k))+CAzz
          Do 12 m=1,3
            l=List(m)
            Vx(l)=Vx(l)-Con(l)*Vxx
            Vz(l)=Vz(l)-Con(l)*Vzz
12        Continue
13      Continue
14    Continue
      Do 15 i=1,NumNP
        Vx(i)=Vx(i)/ListNE(i)
        Vz(i)=Vz(i)/ListNE(i)
15    Continue
      Return
      End

