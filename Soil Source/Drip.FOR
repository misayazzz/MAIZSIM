* This subroutine implements drip irrigation

* Note that the first day  for drip irrigation needs to be at least one
* day later than the initial time in the file in the time folder. This
* allows the program to initialize the soil properties and fluxes.

      Subroutine Drip()
      Include 'public.ins'
      Include 'PuSurface.ins'
      Integer Max_times,Drip_times,Num_nodes,nAppl,applied,found,
     ! Max_nodes,SourceBnd,SourceSurfPos,WetRadius,DripSurfNode,
     ! DripSurfBnd,DripSurfCount,DripMode,ShrinkCount,
     ! DripSpreadMode
      Parameter (Max_times=75, Max_nodes=150)
      Parameter (NTabD=100, NPar=13)
      Double precision PERIOD
      Parameter (PERIOD=1.0D0/24.0D0)
      Real wAppl,DripRate(NumBPD),
     !     CurrentRate,
     !     DripTol,LastRate,LastAir,LastMulch,LastBW,TotalWidth,
     !     SourceFlux,AddRate,PressureFactor,Havail,HeadPressure,
     !     DripHIn,DripExp,DripPcMin,DripPcMax,SourceRate,
     !     SourceDemandFlux,DemandRate,LossRate,DripWetWidthMax,
     !     DripSourceWidth,
     !     SurfaceWidth,MaxWetWidth,CandidateWidth,NodeExcess,
     !     ExcessFlux,PrevDripFlux,DripExcessFrac,
     !     DripDefaultWetWidth,TargetWetWidth,TargetLeft,TargetRight,
     !     SegmentLeft,SegmentRight,CoverLeft,CoverRight,
     !     CoverWidth,CoverMeasure,TotalMeasure,DripCoverMeasure,
     !     CapSum,LocalCap,LocalCapFactor,CandidateMin,CandidateMax,
     !     StorageFlux,SourceInputFlux,ReleaseCap,LocalMeasure,
     !     ReleaseMeasure
      Double Precision tAppl_start,tAppl_stop,NextTime,
     !                 start_hour(Max_times),
     !                 stop_hour(Max_times),
     !                 StorageAdd,StorageLimit,StorageOverflow,
     !                 ReleaseVolume,DripBaseDtMx,DripTimeTol
      Double Precision Par,hTab,ConTab,CapTab,ConSat,TheTab,alh1,dlh
      Double Precision DripThOld(NumNPD),DripHTemp(NumNPD),
     !                 DripHOld(NumNPD),DripConAxx(NumElD),
     !                 DripConAzz(NumElD),DripConAxz(NumElD),
     !                 DripDt,DripDtOld,DripTOld,
     !                 DripThR(NMatD),DripHSat(NMatD)
      Real DripTolTh,DripTolH
      Logical DripFreeD
      Integer CenterPos,CenterBnd,SourceNode,ActiveRadius,
     !        LeftPos,RightPos,NeedExpand,CanShrink,MaxRadius,
     !        EdgeMaxRadius,CandidateRadius,CandidateLeft,
     !        CandidateRight,ActiveNodes,TestNode,ios,
     !        DesiredRadius,FieldCount,DripFieldCount,m,
     !        DripBaseDtMxSet,DripActive,Mode6Source,
     !        Mode6Left,Mode6Right,Mode6EmitterNode
      Integer DripMaxIt,DripIsat(NumBPD)
      Character*256 EventLine

      Character*10 Start_Date(Max_times),Stop_Date(Max_times)

      Common /DripC/ tAppl_start(Max_times), tAppl_stop(Max_times),
     !     wAppl(Max_times), Drip_times,
     !     Num_nodes(Max_times), nAppl(Max_times, Max_nodes),
     !     LastRate(NumBPD),LastAir(NumBPD),LastMulch(NumBPD),
     !     LastBW(NumBPD),SourceBnd(Max_times,Max_nodes),
     !     SourceSurfPos(Max_times,Max_nodes),
     !     WetRadius(Max_times,Max_nodes),DripSurfNode(NumBPD),
     !     ShrinkCount(Max_times,Max_nodes),
     !     DripSurfBnd(NumBPD),DripSurfCount,DripMode(Max_times),
     !     DripHIn(Max_times),DripExp(Max_times),
     !     DripPcMin(Max_times),DripPcMax(Max_times),
     !     DripWetWidthMax(Max_times),DripSpreadMode(Max_times),
     !     DripSourceWidth(Max_times),
     !     applied,ModNum
      Common /HydPar/ Par(NPar,NMatD),
     !                hTab(NTabD),ConTab(NTabD,NMatD),
     !                CapTab(NTabD,NMatD),ConSat(NMatD),
     !                TheTab(NTabD,NMatD),alh1,dlh
      Common /WaterM/ DripThOld,DripHTemp,DripHOld,
     !                DripConAxx,DripConAzz,DripConAxz,
     !                DripMaxIt,DripTolTh,DripTolH,
     !                DripDt,DripDtOld,DripTOld,
     !                DripThR,DripHSat,DripIsat,DripFreeD
      Save DripBaseDtMx,DripBaseDtMxSet
      Data DripBaseDtMxSet /0/

      DripTol=1.0E-5
      DripExcessFrac=0.05
      DripDefaultWetWidth=20.0
      If(lInput.eq.1) then
        DripInput_Flux=0.0D0
        DripDemand_Flux=0.0D0
        DripPressureLoss_Flux=0.0D0
        DripHydraulicExcess_Flux=0.0D0
        DripActualInfil_Flux=0.0D0
        DripSourceInput_Flux=0.0D0
        DripSourceLoss_Flux=0.0D0
        DripStorageChange_Flux=0.0D0
        DripSurfaceRunoff_Flux=0.0D0
        DripWetNodes_Sum=0.0D0
        DripWetNodes_Max=0.0D0
        DripWetWidth_Sum=0.0D0
        DripWetWidth_Max=0.0D0
        DripPressureFactor_Sum=0.0D0
        DripPressureFactor_Min=1.0D30
        DripDiag_Time=0.0D0
        DripWetNodes_StepSum=0.0D0
        DripWetNodes_StepMax=0.0D0
        DripWetWidth_StepSum=0.0D0
        DripWetWidth_StepMax=0.0D0
        DripPressureFactor_StepSum=0.0D0
        DripPressureFactor_StepMin=1.0D30
        DripDiag_StepCount=0.0D0
        DripMode6Accepted_Flux=0.0D0
        DripMode6Remaining_Flux=0.0D0
        DripMode6HeadNodes_Sum=0.0D0
        DripMode6FluxNodes_Sum=0.0D0
        DripMode6Iterations_Sum=0.0D0
        DripMode6SolverLimit_Sum=0.0D0
        DripMode6BoundaryLimit_Sum=0.0D0
        DripMode6Diag_Time=0.0D0
        DripMode6StepCuts_Sum=0.0D0
        DripMode6NonlinearCuts_Sum=0.0D0
        DripMode6SupplyCuts_Sum=0.0D0
        DripMode6MassCuts_Sum=0.0D0
        DripMode6MinDt=1.0D30
        Open(40,file=DripFile,err=20)
        Read(40,*,Err=20)
        Read(40,*,Err=20)
        Read(40,*,Err=20) Drip_times
        If(Drip_times.lt.0.or.Drip_times.gt.Max_times) then
          Stop 'Invalid number of drip irrigations'
        Endif
        NumMod=NumMod+1
        ModNum=NumMod
        applied=1
        Do i=1,NumBPD
          LastRate(i)=0.0
          LastAir(i)=0.0
          LastMulch(i)=0.0
          LastBW(i)=0.0
          DripRate(i)=0.0
          DripInput_Rate(i)=0.0
          DripDemand_Rate(i)=0.0
          DripPressureLoss_Rate(i)=0.0
          DripStorageRelease_Rate(i)=0.0
          DripSurfaceStorage(i)=0.0D0
          DripCoveredMeasure(i)=0.0D0
          DripStorageActive(i)=0
          DripStorageBoundary(i)=0
          DripSurfNode(i)=0
          DripSurfBnd(i)=0
          DripMode6AssignedFlux(i)=0.0D0
          DripMode6FluxActive(i)=0
          DripMode6HeadActive(i)=0
          DripMode6AtmosHeadActive(i)=0
          DripMode6CandidateOwner(i)=0
          DripMode6BoundaryOwner(i)=0
        EndDo
        Do i=1,NumBP
          n=KXB(i)
          If(CodeW(n).eq.4) DripMode6AtmosHeadActive(i)=1
        EndDo
        DripMode6Active=0
        DripMode6Count=0
        DripMode6IterationCount=0
        DripMode6AdaptiveIter=0
        Do i=1,MaxDripMode6D
          DripMode6DemandFlux(i)=0.0D0
          DripMode6InputFlux(i)=0.0D0
          DripMode6RemainingFlux(i)=0.0D0
          DripMode6AcceptedFlux(i)=0.0D0
          DripMode6PressureLossFlux(i)=0.0D0
          DripMode6PressureFactor(i)=0.0D0
          DripMode6CenterPos(i)=0
          DripMode6CenterBnd(i)=0
          DripMode6MaxRadius(i)=0
          DripMode6CurrentRadius(i)=0
          DripMode6Closed(i)=1
        EndDo
        DripBypassRunoff=0
        Do i=1,Max_times
          DripMode(i)=0
          DripHIn(i)=0.0
          DripExp(i)=1.0
          DripPcMin(i)=0.0
          DripPcMax(i)=0.0
          DripWetWidthMax(i)=0.0
          DripSpreadMode(i)=0
          DripSourceWidth(i)=0.0
          Do j=1,Max_nodes
            SourceBnd(i,j)=0
            SourceSurfPos(i,j)=0
            WetRadius(i,j)=0
            ShrinkCount(i,j)=0
          EndDo
        EndDo
        DripSurfCount=0
        Do k=1,NumBP
          n=KXB(k)
          If(abs(CodeW(n)).eq.4) then
            DripSurfCount=DripSurfCount+1
            DripSurfNode(DripSurfCount)=n
            DripSurfBnd(DripSurfCount)=k
          Endif
        EndDo
        Do i=1,DripSurfCount-1
          Do j=i+1,DripSurfCount
            If(x(DripSurfNode(j)).lt.x(DripSurfNode(i))) then
              n=DripSurfNode(i)
              k=DripSurfBnd(i)
              DripSurfNode(i)=DripSurfNode(j)
              DripSurfBnd(i)=DripSurfBnd(j)
              DripSurfNode(j)=n
              DripSurfBnd(j)=k
            Endif
          EndDo
        EndDo
        if (Drip_times.eq.0)  then
          tNext(ModNum)=1e22
          Close(40)
          Return
        End if
        Read(40,*,Err=20)
        Mode6EmitterNode=0
        Do i=1,Drip_times
          Read(40,'(A)',Err=20) EventLine
          DripMode(i)=0
          DripHIn(i)=0.0
          DripExp(i)=1.0
          DripPcMin(i)=0.0
          DripPcMax(i)=0.0
          DripWetWidthMax(i)=0.0
          DripSpreadMode(i)=0
          DripSourceWidth(i)=0.0
          FieldCount=DripFieldCount(EventLine)
          If(FieldCount.eq.14) then
            Read(EventLine,*,IOSTAT=ios) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i),
     !       DripMode(i),DripHIn(i),DripExp(i),
     !       DripPcMin(i),DripPcMax(i),DripWetWidthMax(i),
     !       DripSpreadMode(i),DripSourceWidth(i)
          ElseIf(FieldCount.eq.13) then
            Read(EventLine,*,IOSTAT=ios) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i),
     !       DripMode(i),DripHIn(i),DripExp(i),
     !       DripPcMin(i),DripPcMax(i),DripWetWidthMax(i),
     !       DripSpreadMode(i)
          ElseIf(FieldCount.eq.12) then
            Read(EventLine,*,IOSTAT=ios) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i),
     !       DripMode(i),DripHIn(i),DripExp(i),
     !       DripPcMin(i),DripPcMax(i),DripWetWidthMax(i)
          ElseIf(FieldCount.eq.11) then
            DripWetWidthMax(i)=0.0
            Read(EventLine,*,IOSTAT=ios) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i),
     !       DripMode(i),DripHIn(i),DripExp(i),
     !       DripPcMin(i),DripPcMax(i)
          ElseIf(FieldCount.eq.6) then
            Read(EventLine,*,IOSTAT=ios) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i)
          Else
            Stop 'Invalid drip event field count'
          Endif
          If(ios.ne.0) then
            Stop 'Invalid drip event fields'
          Endif
          If(Num_nodes(i).lt.1.or.Num_nodes(i).gt.Max_nodes) then
            Stop 'Invalid number of drip nodes'
          Endif
          If(wAppl(i).lt.0.0) then
            Stop 'Invalid drip irrigation rate'
          Endif
          If(DripMode(i).lt.0.or.DripMode(i).gt.3) then
            Stop 'Invalid drip pressure mode'
          Endif
          If(DripMode(i).gt.0.and.DripMode(i).lt.3.and.
     !      DripHIn(i).le.0.0) then
            Stop 'Invalid drip inlet pressure'
          Endif
          If(DripExp(i).le.0.0) DripExp(i)=1.0
          If(DripWetWidthMax(i).lt.0.0) then
            Stop 'Invalid drip wetted width limit'
          Endif
          If(DripSpreadMode(i).ne.0.and.
     !      DripSpreadMode(i).ne.5.and.
     !      DripSpreadMode(i).ne.6) then
            Stop 'Invalid drip spread mode'
          Endif
          If(DripSourceWidth(i).lt.0.0) then
            Stop 'Invalid drip source width'
          Endif
          If(DripSpreadMode(i).ne.5.and.
     !      DripSpreadMode(i).ne.6.and.
     !      DripSourceWidth(i).gt.0.0) then
            Stop 'Drip source width requires mode 5 or 6'
          Endif
          If((DripSpreadMode(i).eq.5.or.
     !      DripSpreadMode(i).eq.6).and.
     !      DripSourceWidth(i).le.0.0) then
            Stop 'Mode 5/6 drip source width required'
          Endif
          If(DripSpreadMode(i).eq.6.and.Num_nodes(i).ne.1) then
            Stop 'Mode 6 requires exactly one drip emitter'
          Endif
          Read(40,*,Err=20)
          Read(40,*,Err=20) (nAppl(i,j),j=1,Num_nodes(i))
          If(DripSpreadMode(i).eq.6) then
            If(Mode6EmitterNode.eq.0) then
              Mode6EmitterNode=nAppl(i,1)
            ElseIf(nAppl(i,1).ne.Mode6EmitterNode) then
              Stop 'Mode 6 events must use the same drip emitter'
            Endif
          Endif
        EndDo
        Close(40)
        NextTime=1.0D32
        Do i=1,Drip_times
          tAppl_start(i)=dble(julday(Start_Date(i)))+
     !      Start_hour(i)/24.0D0
          tAppl_stop(i)=dble(julday(Stop_Date(i)))+
     !      Stop_hour(i)/24.0D0
          If(tAppl_stop(i).le.tAppl_start(i)) then
            Stop 'Invalid drip irrigation time window'
          Endif
          If(DripSpreadMode(i).eq.6) then
            Do m=1,i-1
              If(DripSpreadMode(m).eq.6.and.
     !          tAppl_start(i).lt.tAppl_stop(m).and.
     !          tAppl_start(m).lt.tAppl_stop(i)) then
                Stop 'Mode 6 drip events must not overlap'
              Endif
            EndDo
          Endif
          Do j=1,Num_nodes(i)
            found=0
            Do k=1,DripSurfCount
              n=DripSurfNode(k)
              If(n.eq.nAppl(i,j)) then
                found=1
                SourceSurfPos(i,j)=k
                SourceBnd(i,j)=DripSurfBnd(k)
              Endif
            EndDo
            If(found.eq.0) then
              Stop 'Drip node is not a surface water boundary'
            Endif
          EndDo
          NextTime=dmin1(NextTime,tAppl_start(i))
        EndDo
        tNext(ModNum)=NextTime
      Endif

      If(Drip_times.eq.0) Return

c Synchronizer advances Time to the end of the current integration step before
c boundary modules are evaluated.  Scheduled irrigation must consequently use
c the backward-Euler endpoint interval (start, stop].  Using [start, stop)
c shifts one adaptive step of water ahead of the event and omits the final
c event step, so the integrated volume depends on the two edge step sizes.
      DripTimeTol=1.0D-10

c Keep the small water step only while drip water is active.
c The original water dtMx is read by WaterMover after the first input pass,
c so capture it on the first routine pass and restore it outside events.
      If(DripBaseDtMxSet.eq.0.and.lInput.eq.0) then
        DripBaseDtMx=dtMx(1)
        DripBaseDtMxSet=1
      Endif
      If(DripBaseDtMxSet.eq.1) dtMx(1)=DripBaseDtMx
      DripActive=0
      Do jj=1,Drip_times
c This look-ahead flag controls the next Synchronizer step, so it is enabled
c at the event start and released at its stop.  The actual source below uses
c the distinct backward-Euler endpoint interval (start, stop].
        If(time.ge.tAppl_start(jj).and.time.lt.tAppl_stop(jj)) then
          DripActive=1
        Endif
      EndDo
      Do i=1,NumBP
        If(DripSurfaceStorage(i).gt.1.0D-12) DripActive=1
      EndDo
      If(DripActive.eq.1) then
        dtMx(1)=dmin1(dtMx(1),0.005D0)
        dtOpt=dmin1(dtOpt,0.005D0)
      Endif

      Do i=1,NumBP
        DripRate(i)=0.0
        DripInput_Rate(i)=0.0
        DripDemand_Rate(i)=0.0
        DripPressureLoss_Rate(i)=0.0
        DripStorageRelease_Rate(i)=0.0
        DripStorageActive(i)=0
c Restore the independent atmospheric complementarity state beneath every
c surface node used by the preceding Mode 6 water step before clearing drip
c ownership.  A drip head/flux boundary has priority only while it is active;
c after the event the accepted atmospheric flux/hCritA state must reappear.
        If(DripMode6CandidateOwner(i).gt.0.or.
     !    DripMode6BoundaryOwner(i).gt.0) then
          n=KXB(i)
          If(DripMode6AtmosHeadActive(i).eq.1) then
            Q(n)=0.0
            CodeW(n)=4
          Else
            Q(n)=-VarBW(i,3)*Width(i)
            CodeW(n)=-4
          Endif
        Endif
        DripMode6AssignedFlux(i)=0.0D0
        DripMode6FluxActive(i)=0
        DripMode6HeadActive(i)=0
        DripMode6CandidateOwner(i)=0
        DripMode6BoundaryOwner(i)=0
        If(DripSurfaceStorage(i).le.1.0D-12) then
          DripCoveredMeasure(i)=0.0D0
        Endif
        If(Step.gt.0.0D0.and.Width(i).gt.DripTol.and.
     !    DripSurfaceStorage(i).gt.1.0D-12) then
          n=KXB(i)
          ReleaseMeasure=sngl(DripCoveredMeasure(i))
          If(ReleaseMeasure.le.DripTol) ReleaseMeasure=Width(i)
          LocalCapFactor=1.0+dmax1(0.0D0,-hNew(n))/25.0D0
          LocalCapFactor=amax1(1.0,amin1(5.0,LocalCapFactor))
          ReleaseCap=ConSat(MatNumN(n))*LocalCapFactor
          ReleaseVolume=dmin1(DripSurfaceStorage(i)/Step,
     !      dble(ReleaseCap)*dble(ReleaseMeasure))
          DripStorageRelease_Rate(i)=sngl(
     !      ReleaseVolume/dble(Width(i)))
          DripStorageActive(i)=1
        Endif
      EndDo
      DripBypassRunoff=0
      DripWetNodes_StepSum=0.0D0
      DripWetNodes_StepMax=0.0D0
      DripWetWidth_StepSum=0.0D0
      DripWetWidth_StepMax=0.0D0
      DripPressureFactor_StepSum=0.0D0
      DripPressureFactor_StepMin=1.0D30
      DripDiag_StepCount=0.0D0
      DripMode6Active=0
      DripMode6Count=0
      DripMode6IterationCount=0
      DripMode6AdaptiveIter=0
      Do i=1,MaxDripMode6D
        DripMode6DemandFlux(i)=0.0D0
        DripMode6InputFlux(i)=0.0D0
        DripMode6RemainingFlux(i)=0.0D0
        DripMode6AcceptedFlux(i)=0.0D0
        DripMode6PressureLossFlux(i)=0.0D0
        DripMode6PressureFactor(i)=0.0D0
        DripMode6CenterPos(i)=0
        DripMode6CenterBnd(i)=0
        DripMode6MaxRadius(i)=0
        DripMode6CurrentRadius(i)=0
        DripMode6Closed(i)=1
      EndDo

      Do jj=1,Drip_times
        If(time.gt.tAppl_start(jj)+DripTimeTol.and.
     !     time.le.tAppl_stop(jj)+DripTimeTol) then
          If(DripSpreadMode(jj).eq.5.or.
     !      DripSpreadMode(jj).eq.6) DripBypassRunoff=1
          Do in=1,Num_nodes(jj)
            CenterPos=SourceSurfPos(jj,in)
            CenterBnd=SourceBnd(jj,in)
            If(CenterPos.le.0.or.CenterBnd.le.0) then
              Stop 'Drip source node is invalid'
            Endif
            SourceNode=DripSurfNode(CenterPos)
            NeedExpand=0
            CanShrink=1
            ActiveRadius=WetRadius(jj,in)
            LeftPos=max(1,CenterPos-ActiveRadius)
            RightPos=min(DripSurfCount,CenterPos+ActiveRadius)
            SurfaceWidth=0.0
            Do k=1,DripSurfCount
              SurfaceWidth=SurfaceWidth+Width(DripSurfBnd(k))
            EndDo
            If(DripWetWidthMax(jj).gt.0.0) then
              MaxWetWidth=DripWetWidthMax(jj)
            Else
              MaxWetWidth=amin1(DripDefaultWetWidth,
     !          0.5*SurfaceWidth)
            Endif
            If(DripSpreadMode(jj).eq.5.or.
     !        DripSpreadMode(jj).eq.6) then
              MaxWetWidth=amax1(MaxWetWidth,DripSourceWidth(jj))
              If(SurfaceWidth.gt.DripTol) then
                MaxWetWidth=amin1(MaxWetWidth,SurfaceWidth)
              Endif
            Else
              MaxWetWidth=amax1(MaxWetWidth,Width(CenterBnd))
            Endif
            EdgeMaxRadius=max(CenterPos-1,DripSurfCount-CenterPos)
            MaxRadius=0
            Do CandidateRadius=1,EdgeMaxRadius
              CandidateLeft=max(1,CenterPos-CandidateRadius)
              CandidateRight=min(DripSurfCount,
     !          CenterPos+CandidateRadius)
              CandidateMin=1.0E30
              CandidateMax=-1.0E30
              Do k=CandidateLeft,CandidateRight
                TestNode=DripSurfNode(k)
                If(DripSurfCount.eq.1) then
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                    SegmentRight=x(TestNode)
                  Else
                    SegmentLeft=x(TestNode)-
     !                0.5*Width(DripSurfBnd(k))
                    SegmentRight=x(TestNode)+
     !                0.5*Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.1) then
                  SegmentRight=0.5*(x(TestNode)+
     !              x(DripSurfNode(k+1)))
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                  Else
                    SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.DripSurfCount) then
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(TestNode))
                  If(KAT.eq.1) then
                    SegmentRight=x(TestNode)
                  Else
                    SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                  Endif
                Else
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(TestNode))
                  SegmentRight=0.5*(x(TestNode)+
     !              x(DripSurfNode(k+1)))
                Endif
                CandidateMin=amin1(CandidateMin,SegmentLeft)
                CandidateMax=amax1(CandidateMax,SegmentRight)
              EndDo
              CandidateWidth=CandidateMax-CandidateMin
              If(CandidateWidth.le.MaxWetWidth+DripTol) then
                MaxRadius=CandidateRadius
              Endif
            EndDo
            If(DripSpreadMode(jj).eq.6) then
c HYDRUS SurfaceDrip advances over the connected surface until the
c emitter flow is accepted.  Mode 6 therefore uses the full half-domain;
c DripWetWidthMax remains a Mode 5 calibration/control parameter only.
              MaxRadius=EdgeMaxRadius
            Endif
            If(DripSpreadMode(jj).eq.5) MaxRadius=EdgeMaxRadius
            If(WetRadius(jj,in).gt.MaxRadius) then
              WetRadius(jj,in)=MaxRadius
              ActiveRadius=WetRadius(jj,in)
              LeftPos=max(1,CenterPos-ActiveRadius)
              RightPos=min(DripSurfCount,CenterPos+ActiveRadius)
            Endif
            PressureFactor=1.0
            If(DripMode(jj).gt.0.and.DripMode(jj).lt.3) then
              HeadPressure=dmax1(hNew(SourceNode),0.0D0)
              Havail=DripHIn(jj)-HeadPressure
              If(Havail.le.0.0) then
                PressureFactor=0.0
              ElseIf(DripMode(jj).eq.1) then
                PressureFactor=(Havail/DripHIn(jj))**DripExp(jj)
              Else
                If(DripPcMin(jj).gt.0.0.and.
     !             Havail.lt.DripPcMin(jj)) then
                  PressureFactor=(Havail/DripPcMin(jj))**DripExp(jj)
                Else
                  PressureFactor=1.0
                Endif
              Endif
              PressureFactor=amax1(0.0,amin1(1.0,PressureFactor))
            Endif
            If(DripSpreadMode(jj).eq.6) then
c Mode 6 registers a HYDRUS-style surface active boundary source.
c WaterMover assigns the active flux/head boundaries from this state.
              If(DripMode6Count.ge.1) then
                Stop 'Only one active Mode 6 drip emitter is supported'
              Endif
              SourceRate=wAppl(jj)/PERIOD
              SourceDemandFlux=SourceRate*DripSourceWidth(jj)
              SourceFlux=SourceDemandFlux*PressureFactor
              Mode6Left=max(1,CenterPos-MaxRadius)
              Mode6Right=min(DripSurfCount,CenterPos+MaxRadius)
              If(DripMode6Count.ge.MaxDripMode6D) then
                Stop 'Too many active Mode 6 drip sources'
              Endif
              Do k=Mode6Left,Mode6Right
                If(DripMode6CandidateOwner(DripSurfBnd(k)).ne.0) then
                  Stop 'Overlapping Mode 6 drip sources'
                Endif
              EndDo
              DripMode6Count=DripMode6Count+1
              Mode6Source=DripMode6Count
              DripMode6Active=1
              DripMode6DemandFlux(Mode6Source)=dble(SourceDemandFlux)
              DripMode6InputFlux(Mode6Source)=dble(SourceFlux)
              DripMode6RemainingFlux(Mode6Source)=dble(SourceFlux)
              DripMode6AcceptedFlux(Mode6Source)=0.0D0
              DripMode6PressureLossFlux(Mode6Source)=
     !          dble(SourceDemandFlux-SourceFlux)
              DripMode6PressureFactor(Mode6Source)=
     !          dble(PressureFactor)
              DripMode6CenterPos(Mode6Source)=CenterPos
              DripMode6CenterBnd(Mode6Source)=CenterBnd
              DripMode6MaxRadius(Mode6Source)=MaxRadius
              Do k=Mode6Left,Mode6Right
                DripMode6CandidateOwner(DripSurfBnd(k))=Mode6Source
              EndDo
c Continue the HYDRUS-style active surface boundary from the wetted
c radius accepted in the preceding water step.  Rebuilding every step
c from the emitter-only Neumann condition repeatedly forces the same
c flux-to-head transitions and can trap the global integrator at dtMin.
c Nodes inside the saved radius are the connected zero-pressure set;
c nodes on its edge carry the finite residual flux.
              DesiredRadius=min(WetRadius(jj,in),MaxRadius)
              DripMode6CurrentRadius(Mode6Source)=DesiredRadius
              If(SourceFlux.le.DripTol) then
                DripMode6Closed(Mode6Source)=1
              Else
                DripMode6Closed(Mode6Source)=0
                TotalMeasure=0.0
                Do k=Mode6Left,Mode6Right
                  CandidateRadius=iabs(k-CenterPos)
                  If(CandidateRadius.lt.DesiredRadius) then
                    DripMode6HeadActive(DripSurfBnd(k))=1
                    DripMode6BoundaryOwner(DripSurfBnd(k))=Mode6Source
                  ElseIf(CandidateRadius.eq.DesiredRadius) then
                    DripMode6FluxActive(DripSurfBnd(k))=1
                    DripMode6BoundaryOwner(DripSurfBnd(k))=Mode6Source
                    TotalMeasure=TotalMeasure+Width(DripSurfBnd(k))
                  Endif
                EndDo
                If(TotalMeasure.le.DripTol) then
                  Stop 'Mode 6 frontier has zero boundary measure'
                Endif
                Do k=Mode6Left,Mode6Right
                  If(DripMode6FluxActive(DripSurfBnd(k)).eq.1) then
                    DripMode6AssignedFlux(DripSurfBnd(k))=
     !                dble(SourceFlux)*dble(Width(DripSurfBnd(k)))/
     !                dble(TotalMeasure)
                  Endif
                EndDo
              Endif
              GoTo 520
            Endif
            If(DripSpreadMode(jj).eq.5) then
c Mode 5 is a dynamic local surface source. DripSourceWidth defines
c emitter discharge, while DripWetWidthMax limits the effective
c surface wetting interval selected from local hydraulic acceptance.
              SourceRate=wAppl(jj)/PERIOD
              SourceDemandFlux=SourceRate*DripSourceWidth(jj)*
     !          PressureFactor
              DesiredRadius=0
              TargetWetWidth=DripSourceWidth(jj)
              Do CandidateRadius=0,MaxRadius
                CandidateLeft=max(1,CenterPos-CandidateRadius)
                CandidateRight=min(DripSurfCount,
     !            CenterPos+CandidateRadius)
                CandidateMin=1.0E30
                CandidateMax=-1.0E30
                Do k=CandidateLeft,CandidateRight
                  TestNode=DripSurfNode(k)
                  If(DripSurfCount.eq.1) then
                    If(KAT.eq.1) then
                      SegmentLeft=0.0
                      SegmentRight=x(TestNode)
                    Else
                      SegmentLeft=x(TestNode)-
     !                  0.5*Width(DripSurfBnd(k))
                      SegmentRight=x(TestNode)+
     !                  0.5*Width(DripSurfBnd(k))
                    Endif
                  ElseIf(k.eq.1) then
                    SegmentRight=0.5*(x(TestNode)+
     !                x(DripSurfNode(k+1)))
                    If(KAT.eq.1) then
                      SegmentLeft=0.0
                    Else
                      SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                    Endif
                  ElseIf(k.eq.DripSurfCount) then
                    SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                x(TestNode))
                    If(KAT.eq.1) then
                      SegmentRight=x(TestNode)
                    Else
                      SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                    Endif
                  Else
                    SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                x(TestNode))
                    SegmentRight=0.5*(x(TestNode)+
     !                x(DripSurfNode(k+1)))
                  Endif
                  CandidateMin=amin1(CandidateMin,SegmentLeft)
                  CandidateMax=amax1(CandidateMax,SegmentRight)
                EndDo
                CandidateWidth=amax1(0.0,
     !            CandidateMax-CandidateMin)
                TargetWetWidth=amin1(MaxWetWidth,
     !            amax1(DripSourceWidth(jj),CandidateWidth))
                If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                  TargetLeft=0.0
                  TargetRight=TargetWetWidth
                Else
                  TargetLeft=x(SourceNode)-0.5*TargetWetWidth
                  TargetRight=x(SourceNode)+0.5*TargetWetWidth
                Endif
                CapSum=0.0
                Do k=CandidateLeft,CandidateRight
                  TestNode=DripSurfNode(k)
                  If(DripSurfCount.eq.1) then
                    If(KAT.eq.1) then
                      SegmentLeft=0.0
                      SegmentRight=x(TestNode)
                    Else
                      SegmentLeft=x(TestNode)-
     !                  0.5*Width(DripSurfBnd(k))
                      SegmentRight=x(TestNode)+
     !                  0.5*Width(DripSurfBnd(k))
                    Endif
                  ElseIf(k.eq.1) then
                    SegmentRight=0.5*(x(TestNode)+
     !                x(DripSurfNode(k+1)))
                    If(KAT.eq.1) then
                      SegmentLeft=0.0
                    Else
                      SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                    Endif
                  ElseIf(k.eq.DripSurfCount) then
                    SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                x(TestNode))
                    If(KAT.eq.1) then
                      SegmentRight=x(TestNode)
                    Else
                      SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                    Endif
                  Else
                    SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                x(TestNode))
                    SegmentRight=0.5*(x(TestNode)+
     !                x(DripSurfNode(k+1)))
                  Endif
                  CoverLeft=amax1(SegmentLeft,TargetLeft)
                  CoverRight=amin1(SegmentRight,TargetRight)
                  CoverWidth=amax1(0.0,CoverRight-CoverLeft)
                  LocalMeasure=DripCoverMeasure(KAT,SegmentLeft,
     !              SegmentRight,CoverLeft,CoverRight,
     !              Width(DripSurfBnd(k)))
                  If(CoverWidth.le.DripTol.or.
     !              LocalMeasure.le.DripTol) GoTo 330
                  LocalCapFactor=1.0+
     !              dmax1(0.0D0,-hNew(TestNode))/25.0D0
                  LocalCapFactor=amax1(1.0,
     !              amin1(5.0,LocalCapFactor))
                  LocalCap=ConSat(MatNumN(TestNode))*LocalCapFactor
                  CapSum=CapSum+LocalCap*LocalMeasure
                  CapSum=CapSum-
     !              DripStorageRelease_Rate(DripSurfBnd(k))*
     !              Width(DripSurfBnd(k))
330               Continue
                EndDo
                CapSum=amax1(0.0,CapSum)
                If(CapSum.ge.SourceDemandFlux.or.
     !            CandidateRadius.eq.MaxRadius) then
                  DesiredRadius=CandidateRadius
                  GoTo 335
                Endif
              EndDo
335           Continue
              WetRadius(jj,in)=DesiredRadius
              ShrinkCount(jj,in)=0
              If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                TargetLeft=0.0
                TargetRight=TargetWetWidth
              Else
                TargetLeft=x(SourceNode)-0.5*TargetWetWidth
                TargetRight=x(SourceNode)+0.5*TargetWetWidth
              Endif
            Endif
            If(DripSpreadMode(jj).eq.5) then
              DesiredRadius=0
              Do k=1,DripSurfCount
                If(DripSurfCount.eq.1) then
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                    SegmentRight=x(DripSurfNode(k))
                  Else
                    SegmentLeft=x(DripSurfNode(k))-
     !                0.5*Width(DripSurfBnd(k))
                    SegmentRight=x(DripSurfNode(k))+
     !                0.5*Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.1) then
                  SegmentRight=0.5*(x(DripSurfNode(k))+
     !              x(DripSurfNode(k+1)))
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                  Else
                    SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.DripSurfCount) then
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(DripSurfNode(k)))
                  If(KAT.eq.1) then
                    SegmentRight=x(DripSurfNode(k))
                  Else
                    SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                  Endif
                Else
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(DripSurfNode(k)))
                  SegmentRight=0.5*(x(DripSurfNode(k))+
     !              x(DripSurfNode(k+1)))
                Endif
                CoverLeft=amax1(SegmentLeft,TargetLeft)
                CoverRight=amin1(SegmentRight,TargetRight)
                CoverWidth=amin1(Width(DripSurfBnd(k)),
     !            amax1(0.0,CoverRight-CoverLeft))
                If(CoverWidth.gt.DripTol) then
                  DesiredRadius=max(DesiredRadius,abs(k-CenterPos))
                Endif
              EndDo
              WetRadius(jj,in)=DesiredRadius
              ShrinkCount(jj,in)=0
              ElseIf(DripSpreadMode(jj).eq.0) then
                ExcessFlux=0.0
                PrevDripFlux=0.0
                Do k=LeftPos,RightPos
                  TestNode=DripSurfNode(k)
                  NodeExcess=amax1(RO(TestNode),0.0)
                  ExcessFlux=ExcessFlux+NodeExcess
                  PrevDripFlux=PrevDripFlux+
     !            LastRate(DripSurfBnd(k))*Width(DripSurfBnd(k))
              EndDo
              If(PrevDripFlux.le.DripTol) then
                PrevDripFlux=wAppl(jj)/PERIOD*Width(CenterBnd)
              Endif
              If(ExcessFlux.gt.amax1(DripTol,
     !          DripExcessFrac*PrevDripFlux)) NeedExpand=1
              If(NeedExpand.eq.1) CanShrink=0
              If(NeedExpand.eq.1.and.WetRadius(jj,in).lt.MaxRadius) then
                WetRadius(jj,in)=WetRadius(jj,in)+1
                ShrinkCount(jj,in)=0
              ElseIf(CanShrink.eq.1.and.WetRadius(jj,in).gt.0) then
                ShrinkCount(jj,in)=ShrinkCount(jj,in)+1
                If(ShrinkCount(jj,in).ge.2) then
                  WetRadius(jj,in)=WetRadius(jj,in)-1
                  ShrinkCount(jj,in)=0
                Endif
              Else
                ShrinkCount(jj,in)=0
              Endif
            Endif
            ActiveRadius=WetRadius(jj,in)
            LeftPos=max(1,CenterPos-ActiveRadius)
            RightPos=min(DripSurfCount,CenterPos+ActiveRadius)
            TotalWidth=0.0
            TotalMeasure=0.0
            ActiveNodes=0
            If(DripSpreadMode(jj).eq.5) then
              If(DripSpreadMode(jj).eq.5.and.KAT.eq.1.and.
     !          abs(x(SourceNode)).le.DripTol) then
                TargetLeft=0.0
                TargetRight=TargetWetWidth
              ElseIf(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                TargetLeft=0.0
                TargetRight=TargetWetWidth
              Else
                TargetLeft=x(SourceNode)-0.5*TargetWetWidth
                TargetRight=x(SourceNode)+0.5*TargetWetWidth
              Endif
              Do k=LeftPos,RightPos
                If(DripSurfCount.eq.1) then
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                    SegmentRight=x(DripSurfNode(k))
                  Else
                    SegmentLeft=x(DripSurfNode(k))-
     !                0.5*Width(DripSurfBnd(k))
                    SegmentRight=x(DripSurfNode(k))+
     !                0.5*Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.1) then
                  SegmentRight=0.5*(x(DripSurfNode(k))+
     !              x(DripSurfNode(k+1)))
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                  Else
                    SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.DripSurfCount) then
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(DripSurfNode(k)))
                  If(KAT.eq.1) then
                    SegmentRight=x(DripSurfNode(k))
                  Else
                    SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                  Endif
                Else
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(DripSurfNode(k)))
                  SegmentRight=0.5*(x(DripSurfNode(k))+
     !              x(DripSurfNode(k+1)))
                Endif
                CoverLeft=amax1(SegmentLeft,TargetLeft)
                CoverRight=amin1(SegmentRight,TargetRight)
                CoverWidth=amax1(0.0,CoverRight-CoverLeft)
                CoverMeasure=DripCoverMeasure(KAT,SegmentLeft,
     !            SegmentRight,CoverLeft,CoverRight,
     !            Width(DripSurfBnd(k)))
                If(CoverWidth.gt.DripTol) then
                  TotalWidth=TotalWidth+CoverWidth
                  TotalMeasure=TotalMeasure+CoverMeasure
                  ActiveNodes=ActiveNodes+1
                Endif
              EndDo
            Else
              ActiveNodes=RightPos-LeftPos+1
              Do k=LeftPos,RightPos
                TotalWidth=TotalWidth+Width(DripSurfBnd(k))
                TotalMeasure=TotalMeasure+Width(DripSurfBnd(k))
              EndDo
            Endif
            If(TotalWidth.le.0.0.or.TotalMeasure.le.0.0)
     !        Stop 'Invalid drip wetted width'
            SourceRate=wAppl(jj)/PERIOD
            If(DripSpreadMode(jj).eq.5) then
              SourceDemandFlux=SourceRate*DripSourceWidth(jj)
            Else
              SourceDemandFlux=SourceRate*Width(CenterBnd)
            Endif
            SourceFlux=SourceDemandFlux*PressureFactor
            SourceInputFlux=SourceFlux
            If(DripSpreadMode(jj).eq.5.and.Step.gt.0.0D0) then
              CapSum=0.0
              Do k=LeftPos,RightPos
                TestNode=DripSurfNode(k)
                LocalMeasure=Width(DripSurfBnd(k))
                If(DripSpreadMode(jj).eq.5) then
                  If(DripSurfCount.eq.1) then
                    If(KAT.eq.1) then
                      SegmentLeft=0.0
                      SegmentRight=x(TestNode)
                    Else
                      SegmentLeft=x(TestNode)-
     !                  0.5*Width(DripSurfBnd(k))
                      SegmentRight=x(TestNode)+
     !                  0.5*Width(DripSurfBnd(k))
                    Endif
                  ElseIf(k.eq.1) then
                    SegmentRight=0.5*(x(TestNode)+
     !                x(DripSurfNode(k+1)))
                    If(KAT.eq.1) then
                      SegmentLeft=0.0
                    Else
                      SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                    Endif
                  ElseIf(k.eq.DripSurfCount) then
                    SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                x(TestNode))
                    If(KAT.eq.1) then
                      SegmentRight=x(TestNode)
                    Else
                      SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                    Endif
                  Else
                    SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                x(TestNode))
                    SegmentRight=0.5*(x(TestNode)+
     !                x(DripSurfNode(k+1)))
                  Endif
                  CoverLeft=amax1(SegmentLeft,TargetLeft)
                  CoverRight=amin1(SegmentRight,TargetRight)
                  CoverWidth=amax1(0.0,CoverRight-CoverLeft)
                  LocalMeasure=DripCoverMeasure(KAT,SegmentLeft,
     !              SegmentRight,CoverLeft,CoverRight,
     !              Width(DripSurfBnd(k)))
                Endif
                If(LocalMeasure.le.DripTol) GoTo 410
                LocalCapFactor=1.0+
     !            dmax1(0.0D0,-hNew(TestNode))/25.0D0
                LocalCapFactor=amax1(1.0,
     !            amin1(5.0,LocalCapFactor))
                LocalCap=ConSat(MatNumN(TestNode))*LocalCapFactor
                CapSum=CapSum+LocalCap*LocalMeasure
                CapSum=CapSum-DripStorageRelease_Rate(DripSurfBnd(k))*
     !            Width(DripSurfBnd(k))
410             Continue
              EndDo
              CapSum=amax1(0.0,CapSum)
              If(SourceFlux.gt.CapSum+DripTol) then
                StorageFlux=SourceFlux-CapSum
                SourceFlux=CapSum
                DripInput_Flux=DripInput_Flux+dble(StorageFlux)*Step
                DripStorageChange_Flux=DripStorageChange_Flux+
     !            dble(StorageFlux)*Step
                Do k=LeftPos,RightPos
                  LocalMeasure=Width(DripSurfBnd(k))
                  If(DripSpreadMode(jj).eq.5) then
                    TestNode=DripSurfNode(k)
                    If(DripSurfCount.eq.1) then
                      If(KAT.eq.1) then
                        SegmentLeft=0.0
                        SegmentRight=x(TestNode)
                      Else
                        SegmentLeft=x(TestNode)-
     !                    0.5*Width(DripSurfBnd(k))
                        SegmentRight=x(TestNode)+
     !                    0.5*Width(DripSurfBnd(k))
                      Endif
                    ElseIf(k.eq.1) then
                      SegmentRight=0.5*(x(TestNode)+
     !                  x(DripSurfNode(k+1)))
                      If(KAT.eq.1) then
                        SegmentLeft=0.0
                      Else
                        SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                      Endif
                    ElseIf(k.eq.DripSurfCount) then
                      SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                  x(TestNode))
                      If(KAT.eq.1) then
                        SegmentRight=x(TestNode)
                      Else
                        SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                      Endif
                    Else
                      SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !                  x(TestNode))
                      SegmentRight=0.5*(x(TestNode)+
     !                  x(DripSurfNode(k+1)))
                    Endif
                    CoverLeft=amax1(SegmentLeft,TargetLeft)
                    CoverRight=amin1(SegmentRight,TargetRight)
                    LocalMeasure=DripCoverMeasure(KAT,SegmentLeft,
     !                SegmentRight,CoverLeft,CoverRight,
     !                Width(DripSurfBnd(k)))
                  Endif
                  If(LocalMeasure.le.DripTol) GoTo 420
                  DripCoveredMeasure(DripSurfBnd(k))=
     !              dble(amin1(Width(DripSurfBnd(k)),
     !              amax1(sngl(DripCoveredMeasure(DripSurfBnd(k))),
     !              LocalMeasure)))
                  StorageAdd=dble(StorageFlux)*dble(LocalMeasure)/
     !              dble(TotalMeasure)*Step
                  DripSurfaceStorage(DripSurfBnd(k))=
     !              DripSurfaceStorage(DripSurfBnd(k))+StorageAdd
                  DripStorageActive(DripSurfBnd(k))=1
                  DripStorageBoundary(DripSurfBnd(k))=1
                  StorageLimit=dble(LocalMeasure)*
     !              dble(CriticalH)
                  If(StorageLimit.gt.0.0D0.and.
     !              DripSurfaceStorage(DripSurfBnd(k)).gt.
     !              StorageLimit) then
                    StorageOverflow=DripSurfaceStorage(DripSurfBnd(k))-
     !                StorageLimit
                    DripSurfaceStorage(DripSurfBnd(k))=StorageLimit
                    DripStorageChange_Flux=DripStorageChange_Flux-
     !                StorageOverflow
                    DripSurfaceRunoff_Flux=DripSurfaceRunoff_Flux+
     !                StorageOverflow
                  Endif
420               Continue
                EndDo
              Endif
            Endif
            If(DripSpreadMode(jj).eq.5) then
              Do k=LeftPos,RightPos
                TestNode=DripSurfNode(k)
                If(DripSurfCount.eq.1) then
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                    SegmentRight=x(TestNode)
                  Else
                    SegmentLeft=x(TestNode)-
     !                0.5*Width(DripSurfBnd(k))
                    SegmentRight=x(TestNode)+
     !                0.5*Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.1) then
                  SegmentRight=0.5*(x(TestNode)+
     !              x(DripSurfNode(k+1)))
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                  Else
                    SegmentLeft=SegmentRight-Width(DripSurfBnd(k))
                  Endif
                ElseIf(k.eq.DripSurfCount) then
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(TestNode))
                  If(KAT.eq.1) then
                    SegmentRight=x(TestNode)
                  Else
                    SegmentRight=SegmentLeft+Width(DripSurfBnd(k))
                  Endif
                Else
                  SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !              x(TestNode))
                  SegmentRight=0.5*(x(TestNode)+
     !              x(DripSurfNode(k+1)))
                Endif
                CoverLeft=amax1(SegmentLeft,TargetLeft)
                CoverRight=amin1(SegmentRight,TargetRight)
                CoverWidth=amax1(0.0,CoverRight-CoverLeft)
                CoverMeasure=DripCoverMeasure(KAT,SegmentLeft,
     !            SegmentRight,CoverLeft,CoverRight,
     !            Width(DripSurfBnd(k)))
                If(CoverWidth.gt.DripTol.and.
     !            CoverMeasure.gt.DripTol) then
                  DripCoveredMeasure(DripSurfBnd(k))=
     !              dble(amin1(Width(DripSurfBnd(k)),
     !              amax1(sngl(DripCoveredMeasure(DripSurfBnd(k))),
     !              CoverMeasure)))
                  AddRate=SourceFlux*CoverMeasure/
     !              TotalMeasure/Width(DripSurfBnd(k))
                  DemandRate=SourceDemandFlux*CoverMeasure/
     !              TotalMeasure/Width(DripSurfBnd(k))
                  LossRate=(SourceDemandFlux-SourceInputFlux)*
     !              CoverMeasure/TotalMeasure/Width(DripSurfBnd(k))
                  DripRate(DripSurfBnd(k))=
     !              DripRate(DripSurfBnd(k))+AddRate
                  DripInput_Rate(DripSurfBnd(k))=
     !              DripInput_Rate(DripSurfBnd(k))+AddRate
                  DripDemand_Rate(DripSurfBnd(k))=
     !              DripDemand_Rate(DripSurfBnd(k))+DemandRate
                  DripPressureLoss_Rate(DripSurfBnd(k))=
     !              DripPressureLoss_Rate(DripSurfBnd(k))+LossRate
                  DripStorageActive(DripSurfBnd(k))=1
                  DripStorageBoundary(DripSurfBnd(k))=1
                Endif
              EndDo
            Else
              AddRate=SourceFlux/TotalMeasure
              DemandRate=SourceDemandFlux/TotalMeasure
              LossRate=(SourceDemandFlux-SourceInputFlux)/TotalMeasure
              Do k=LeftPos,RightPos
                DripRate(DripSurfBnd(k))=
     !            DripRate(DripSurfBnd(k))+AddRate
                DripInput_Rate(DripSurfBnd(k))=
     !            DripInput_Rate(DripSurfBnd(k))+AddRate
                DripDemand_Rate(DripSurfBnd(k))=
     !            DripDemand_Rate(DripSurfBnd(k))+DemandRate
                DripPressureLoss_Rate(DripSurfBnd(k))=
     !            DripPressureLoss_Rate(DripSurfBnd(k))+LossRate
              EndDo
            Endif
            DripWetNodes_StepSum=DripWetNodes_StepSum+
     !        dble(ActiveNodes)
            DripWetNodes_StepMax=dmax1(DripWetNodes_StepMax,
     !        dble(ActiveNodes))
            DripWetWidth_StepSum=DripWetWidth_StepSum+dble(TotalWidth)
            DripWetWidth_StepMax=dmax1(DripWetWidth_StepMax,
     !        dble(TotalWidth))
            DripPressureFactor_StepSum=DripPressureFactor_StepSum+
     !        dble(PressureFactor)
            DripPressureFactor_StepMin=dmin1(DripPressureFactor_StepMin,
     !        dble(PressureFactor))
            DripDiag_StepCount=DripDiag_StepCount+1.0D0
 520        Continue
          EndDo
        ElseIf(time.gt.tAppl_stop(jj)+DripTimeTol) then
          Do in=1,Num_nodes(jj)
            WetRadius(jj,in)=0
            ShrinkCount(jj,in)=0
          EndDo
        Endif
      EndDo

      Do i=1,NumBP
        n=KXB(i)
        CurrentRate=DripRate(i)+DripStorageRelease_Rate(i)

        If(LastRate(i).ne.0.0) then
          If(abs(Varbw_Air(i,1)-LastAir(i)).lt.DripTol) then
            Varbw_Air(i,1)=Varbw_Air(i,1)-LastRate(i)
          Endif
          If(abs(Varbw_Mulch(i,1)-LastMulch(i)).lt.DripTol) then
            Varbw_Mulch(i,1)=Varbw_Mulch(i,1)-LastRate(i)
          Endif
          If(abs(VarBW(i,1)-LastBW(i)).lt.DripTol) then
            VarBW(i,1)=VarBW(i,1)-LastRate(i)
          Endif
        Endif

        If(CurrentRate.ne.0.0) then
          Varbw_Air(i,1)=Varbw_Air(i,1)+CurrentRate
          Varbw_Mulch(i,1)=Varbw_Mulch(i,1)+CurrentRate
          VarBW(i,1)=VarBW(i,1)+CurrentRate
        Endif

        If(LastRate(i).ne.0.0.or.CurrentRate.ne.0.0) then
          VarBW_Air(i,3)=VarBW_Air(i,2)-VarBW_Air(i,1)
          VarBW_Mulch(i,3)=VarBW_Mulch(i,2)-VarBW_Mulch(i,1)
          VarBW(i,3)=VarBW(i,2)-VarBW(i,1)
          Q(n)=-Width(i)*VarBW(i,3)
          If(Q(n).gt.0.0) CodeW(n)=-4
        Endif

        LastRate(i)=CurrentRate
        LastAir(i)=Varbw_Air(i,1)
        LastMulch(i)=Varbw_Mulch(i,1)
        LastBW(i)=VarBW(i,1)
      EndDo

      NextTime=1.0D32
      Do jj=1,Drip_times
        If(tAppl_start(jj).gt.time+0.001D0*Step) then
          NextTime=dmin1(NextTime,tAppl_start(jj))
        Endif
        If(tAppl_stop(jj).gt.time+0.001D0*Step) then
          NextTime=dmin1(NextTime,tAppl_stop(jj))
        Endif
      EndDo
      tNext(ModNum)=NextTime
      Return
20    Stop 'Drip data error'
      End

      Integer Function DripFieldCount(Line)
      Character*(*) Line
      Integer i,LineLen
      Logical InField

      DripFieldCount=0
      InField=.False.
      LineLen=Len(Line)
      Do i=1,LineLen
        If(Line(i:i).ne.' '.and.Line(i:i).ne.Char(9)) then
          If(.not.InField) then
            DripFieldCount=DripFieldCount+1
            InField=.True.
          Endif
        Else
          InField=.False.
        Endif
      EndDo
      Return
      End

      Real Function DripCoverMeasure(Kat,SegmentLeft,SegmentRight,
     ! CoverLeft,CoverRight,FullMeasure)
      Integer Kat
      Real SegmentLeft,SegmentRight,CoverLeft,CoverRight,FullMeasure
      Real CoverLength,SegmentLength,Denom,Numer,Frac

      DripCoverMeasure=0.0
      CoverLength=amax1(0.0,CoverRight-CoverLeft)
      If(CoverLength.le.0.0.or.FullMeasure.le.0.0) Return
      SegmentLength=amax1(0.0,SegmentRight-SegmentLeft)
      If(SegmentLength.le.0.0) Return

      If(Kat.eq.1) then
        Denom=SegmentRight*SegmentRight-SegmentLeft*SegmentLeft
        Numer=CoverRight*CoverRight-CoverLeft*CoverLeft
        If(Denom.gt.1.0E-6) then
          Frac=Numer/Denom
        Else
          Frac=CoverLength/SegmentLength
        Endif
      Else
        Frac=CoverLength/SegmentLength
      Endif
      Frac=amax1(0.0,amin1(1.0,Frac))
      DripCoverMeasure=FullMeasure*Frac
      Return
      End
