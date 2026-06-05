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
      Parameter (PERIOD =1./24.)
      Real wAppl,tAppl_start,tAppl_stop,DripRate(NumBPD),
     !     CurrentRate,
     !     NextTime,DripTol,LastRate,LastAir,LastMulch,LastBW,
     !     start_hour(Max_times),stop_hour(Max_times),TotalWidth,
     !     SourceFlux,AddRate,PressureFactor,Havail,HeadPressure,
     !     DripHIn,DripExp,DripPcMin,DripPcMax,SourceRate,
     !     SourceDemandFlux,DemandRate,LossRate,DripWetWidthMax,
     !     DripSourceWidth,
     !     SurfaceWidth,MaxWetWidth,CandidateWidth,NodeExcess,
     !     ExcessFlux,PrevDripFlux,DripExcessFrac,
     !     DripDefaultWetWidth,TargetWetWidth,EffectiveHours,
     !     HalfWidth,WeightSum,NodeWeight,DistX,
     !     CurveTime,DripTargetWidth,DripCurveHour,DeltaHours,
     !     MaxEventHours,DripEffHours,DripLastTime,
     !     DripLastPressure,StepHours,TargetLeft,TargetRight,
     !     SegmentLeft,SegmentRight,CoverLeft,CoverRight,
     !     CoverWidth,CoverMeasure,TotalMeasure,DripCoverMeasure,
     !     SourceDepth,SourceVolume,NodeDepth,WaterDepth,
     !     ThetaCur,ThetaTry,ThetaRel,VgM,AlphaVG,NVG,
     !     ThetaR,ThetaS,RemainingWater,AppliedWater,
     !     CapacityDepth,AddDepth,MaxTheta,RadialWeight,
     !     DepthWeight,SourceWeight,CapSum,LocalCap,
     !     LocalCapFactor,CandidateMin,CandidateMax,
     !     StorageFlux,SourceInputFlux,ReleaseCap,LocalMeasure,
     !     ReleaseMeasure
      Double Precision StorageAdd,StorageLimit,StorageOverflow,
     !                 ReleaseVolume,DripBaseDtMx
      Real DripLowKsBypassLimit
      Real Par,hTab,ConTab,CapTab,ConSat,TheTab,alh1,dlh
      Real DripThOld(NumNPD),DripHTemp(NumNPD),DripHOld(NumNPD)
      Integer CenterPos,CenterBnd,SourceNode,ActiveRadius,
     !        LeftPos,RightPos,NeedExpand,CanShrink,MaxRadius,
     !        EdgeMaxRadius,CandidateRadius,CandidateLeft,
     !        CandidateRight,ActiveNodes,TestNode,ios,
     !        DesiredRadius,FieldCount,DripFieldCount,m,MatId,
     !        DirectIter,DripBaseDtMxSet,DripActive
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
     !     DripEffHours(Max_times,Max_nodes),
     !     DripLastTime(Max_times,Max_nodes),
     !     DripLastPressure(Max_times,Max_nodes),
     !     applied,ModNum
      Common /HydPar/ Par(NPar,NMatD),
     !                hTab(NTabD),ConTab(NTabD,NMatD),
     !                CapTab(NTabD,NMatD),ConSat(NMatD),
     !                TheTab(NTabD,NMatD),alh1,dlh
      Common /WaterM/ DripThOld,DripHTemp,DripHOld
      Save DripBaseDtMx,DripBaseDtMxSet
      Data DripBaseDtMxSet /0/

      DripTol=1.0E-5
      DripExcessFrac=0.05
      DripDefaultWetWidth=20.0
c 48 cm/day = 2 cm/hour; this protects low-Ks mode-2 drip cases
c from repeated redistribution by the generic surface runoff module.
      DripLowKsBypassLimit=48.0
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
          DripPressureLimit_Rate(i)=0.0
          DripStorageRelease_Rate(i)=0.0
          DripSurfaceStorage(i)=0.0D0
          DripCoveredMeasure(i)=0.0D0
          DripStorageActive(i)=0
          DripStorageBoundary(i)=0
          DripSurfNode(i)=0
          DripSurfBnd(i)=0
        EndDo
        Do i=1,NumNPD
          DripSource_Rate(i)=0.0
        EndDo
        DripBypassRunoff=0
        DripBypassWaterMover=0
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
            DripEffHours(i,j)=0.0
            DripLastTime(i,j)=0.0
            DripLastPressure(i,j)=0.0
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
          If(DripSpreadMode(i).lt.0.or.DripSpreadMode(i).gt.5) then
            Stop 'Invalid drip spread mode'
          Endif
          If(DripSourceWidth(i).lt.0.0) then
            Stop 'Invalid drip source width'
          Endif
          If((DripSpreadMode(i).eq.4.or.
     !      DripSpreadMode(i).eq.5).and.
     !      DripSourceWidth(i).le.0.0) then
            Stop 'Mode 4/5 drip source width required'
          Endif
          Read(40,*,Err=20)
          Read(40,*,Err=20) (nAppl(i,j),j=1,Num_nodes(i))
        EndDo
        Close(40)
        NextTime=1.E+32
        Do i=1,Drip_times
          tAppl_start(i)=julday(Start_Date(i)) + Start_hour(i)/24.0
          tAppl_stop(i)= julday(Stop_Date(i))  + Stop_hour(i)/24.0
          If(tAppl_stop(i).le.tAppl_start(i)) then
            Stop 'Invalid drip irrigation time window'
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
          NextTime=amin1(NextTime,tAppl_start(i))
        EndDo
        tNext(ModNum)=NextTime
      Endif

      If(Drip_times.eq.0) Return

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
        DripPressureLimit_Rate(i)=0.0
        DripStorageRelease_Rate(i)=0.0
        DripStorageActive(i)=0
        If(DripSurfaceStorage(i).le.1.0D-12) then
          DripCoveredMeasure(i)=0.0D0
        Endif
        If(Step.gt.0.0D0.and.Width(i).gt.DripTol.and.
     !    DripSurfaceStorage(i).gt.1.0D-12) then
          n=KXB(i)
          ReleaseMeasure=sngl(DripCoveredMeasure(i))
          If(ReleaseMeasure.le.DripTol) ReleaseMeasure=Width(i)
          LocalCapFactor=1.0+amax1(0.0,-hNew(n))/25.0
          LocalCapFactor=amax1(1.0,amin1(5.0,LocalCapFactor))
          ReleaseCap=ConSat(MatNumN(n))*LocalCapFactor
          ReleaseVolume=dmin1(DripSurfaceStorage(i)/Step,
     !      dble(ReleaseCap)*dble(ReleaseMeasure))
          DripStorageRelease_Rate(i)=sngl(
     !      ReleaseVolume/dble(Width(i)))
          DripStorageActive(i)=1
        Endif
      EndDo
      Do i=1,NumNP
        DripSource_Rate(i)=0.0
      EndDo
      DripBypassRunoff=0
      DripBypassWaterMover=0
      DripWetNodes_StepSum=0.0D0
      DripWetNodes_StepMax=0.0D0
      DripWetWidth_StepSum=0.0D0
      DripWetWidth_StepMax=0.0D0
      DripPressureFactor_StepSum=0.0D0
      DripPressureFactor_StepMin=1.0D30
      DripDiag_StepCount=0.0D0

      Do jj=1,Drip_times
        If(time.ge.tAppl_start(jj).and.time.lt.tAppl_stop(jj)) then
          If(DripSpreadMode(jj).eq.1.and.DripMode(jj).eq.3)
     !      DripBypassRunoff=1
          If(DripSpreadMode(jj).eq.2) DripBypassRunoff=1
          If(DripSpreadMode(jj).eq.4.or.
     !      DripSpreadMode(jj).eq.5) DripBypassRunoff=1
          If(DripSpreadMode(jj).eq.1.and.DripMode(jj).eq.3) then
            DripBypassWaterMover=1
          Endif
          Do in=1,Num_nodes(jj)
            CenterPos=SourceSurfPos(jj,in)
            CenterBnd=SourceBnd(jj,in)
            If(CenterPos.le.0.or.CenterBnd.le.0) then
              Stop 'Drip source node is invalid'
            Endif
            SourceNode=DripSurfNode(CenterPos)
            If(DripSpreadMode(jj).eq.2.and.
     !        ConSat(MatNumN(SourceNode)).lt.DripLowKsBypassLimit)
     !        DripBypassRunoff=1
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
              If(DripSpreadMode(jj).eq.2.and.
     !          ConSat(MatNumN(SourceNode)).gt.DripLowKsBypassLimit)
     !          MaxWetWidth=amin1(MaxWetWidth,10.0)
              If(DripSpreadMode(jj).eq.2.and.
     !          ConSat(MatNumN(SourceNode)).le.DripLowKsBypassLimit)
     !          MaxWetWidth=amin1(MaxWetWidth,18.5)
            Endif
            If(DripSpreadMode(jj).eq.4) then
              MaxWetWidth=DripSourceWidth(jj)
            ElseIf(DripSpreadMode(jj).eq.5) then
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
            If(DripSpreadMode(jj).eq.5) MaxRadius=EdgeMaxRadius
            If(WetRadius(jj,in).gt.MaxRadius) then
              WetRadius(jj,in)=MaxRadius
              ActiveRadius=WetRadius(jj,in)
              LeftPos=max(1,CenterPos-ActiveRadius)
              RightPos=min(DripSurfCount,CenterPos+ActiveRadius)
            Endif
            PressureFactor=1.0
            If(DripMode(jj).gt.0.and.DripMode(jj).lt.3) then
              HeadPressure=amax1(hNew(SourceNode),0.0)
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
            If(DripLastTime(jj,in).lt.tAppl_start(jj).or.
     !        DripLastTime(jj,in).gt.time) then
              DripEffHours(jj,in)=0.0
              DripLastTime(jj,in)=tAppl_start(jj)
              DripLastPressure(jj,in)=PressureFactor
            Endif
            If(time.gt.DripLastTime(jj,in)) then
              DeltaHours=(time-DripLastTime(jj,in))*24.0
              MaxEventHours=(tAppl_stop(jj)-tAppl_start(jj))*24.0
              DripEffHours(jj,in)=DripEffHours(jj,in)+
     !          DeltaHours*DripLastPressure(jj,in)
              DripEffHours(jj,in)=amax1(0.0,
     !          amin1(DripEffHours(jj,in),MaxEventHours))
              DripLastTime(jj,in)=time
            Endif
            DripLastPressure(jj,in)=PressureFactor
            If(DripSpreadMode(jj).eq.1) then
              MaxEventHours=(tAppl_stop(jj)-tAppl_start(jj))*24.0
              StepHours=amin1(sngl(Step*24.0D0),
     !          sngl((tAppl_stop(jj)-time)*24.0D0))
              StepHours=amax1(0.0,StepHours)
              EffectiveHours=DripEffHours(jj,in)+
     !          StepHours*PressureFactor
              EffectiveHours=amax1(0.0,
     !          amin1(EffectiveHours,MaxEventHours))
              TargetWetWidth=DripTargetWidth(MaxWetWidth,
     !          EffectiveHours)
              MinEffHours=amin1(0.03,MaxEventHours)
              If(EffectiveHours.lt.MinEffHours.and.
     !          PressureFactor.gt.0.0) then
                TargetWetWidth=amax1(TargetWetWidth,MaxWetWidth)
              Endif
              TargetWetWidth=amax1(TargetWetWidth,Width(CenterBnd))
              TargetWetWidth=amin1(TargetWetWidth,MaxWetWidth)
              If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                TargetLeft=0.0
                TargetRight=TargetWetWidth
              Else
                TargetLeft=x(SourceNode)-0.5*TargetWetWidth
                TargetRight=x(SourceNode)+0.5*TargetWetWidth
              Endif
            ElseIf(DripSpreadMode(jj).eq.2) then
              SourceRate=wAppl(jj)/PERIOD
              If(DripSourceWidth(jj).gt.0.0) then
                SourceDemandFlux=SourceRate*DripSourceWidth(jj)*
     !            PressureFactor
              Else
                SourceDemandFlux=SourceRate*Width(CenterBnd)*
     !            PressureFactor
              Endif
              DesiredRadius=MaxRadius
              TargetWetWidth=MaxWetWidth
              Do CandidateRadius=0,MaxRadius
                CandidateLeft=max(1,CenterPos-CandidateRadius)
                CandidateRight=min(DripSurfCount,
     !            CenterPos+CandidateRadius)
                CapSum=0.0
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
                  LocalCapFactor=1.0+amax1(0.0,-hNew(TestNode))/25.0
                  LocalCapFactor=amax1(1.0,
     !              amin1(5.0,LocalCapFactor))
                  LocalCap=ConSat(MatNumN(TestNode))*LocalCapFactor
                  CapSum=CapSum+
     !              LocalCap*Width(DripSurfBnd(k))
                EndDo
                CandidateWidth=amax1(0.0,
     !            CandidateMax-CandidateMin)
                If(CapSum.ge.SourceDemandFlux.or.
     !            CandidateRadius.eq.MaxRadius) then
                  DesiredRadius=CandidateRadius
                  TargetWetWidth=amin1(MaxWetWidth,
     !              amax1(Width(CenterBnd),CandidateWidth))
                  GoTo 325
                Endif
              EndDo
325           Continue
              WetRadius(jj,in)=DesiredRadius
              ShrinkCount(jj,in)=0
              If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                TargetLeft=0.0
                TargetRight=TargetWetWidth
              Else
                TargetLeft=x(SourceNode)-0.5*TargetWetWidth
                TargetRight=x(SourceNode)+0.5*TargetWetWidth
              Endif
            ElseIf(DripSpreadMode(jj).eq.5) then
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
                  LocalCapFactor=1.0+amax1(0.0,-hNew(TestNode))/25.0
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
            ElseIf(DripSpreadMode(jj).eq.4) then
c Mode 4 is a fixed local surface source. DripSourceWidth defines the
c target surface interval; water demand uses the covered boundary
c measure so axisymmetric and slab cases use the same accounting basis.
c DripWetWidthMax is not used to spread water.
              TargetWetWidth=DripSourceWidth(jj)
              TargetWetWidth=amax1(TargetWetWidth,DripTol)
              If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                TargetLeft=0.0
                TargetRight=TargetWetWidth
              Else
                TargetLeft=x(SourceNode)-0.5*TargetWetWidth
                TargetRight=x(SourceNode)+0.5*TargetWetWidth
              Endif
            Endif
            If(DripSpreadMode(jj).eq.1.or.
     !        DripSpreadMode(jj).eq.4.or.
     !        DripSpreadMode(jj).eq.5) then
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
              ElseIf(DripSpreadMode(jj).eq.0.or.
     !          DripSpreadMode(jj).eq.3) then
                ExcessFlux=0.0
                PrevDripFlux=0.0
                Do k=LeftPos,RightPos
                  TestNode=DripSurfNode(k)
                  If(DripSpreadMode(jj).eq.3.and.Step.gt.0.0D0) then
                    NodeExcess=sngl(DripSurfaceStorage(DripSurfBnd(k))/
     !                Step)
                  Else
                    NodeExcess=amax1(RO(TestNode),0.0)
                  Endif
                  ExcessFlux=ExcessFlux+NodeExcess
                  PrevDripFlux=PrevDripFlux+
     !            LastRate(DripSurfBnd(k))*Width(DripSurfBnd(k))
              EndDo
              If(PrevDripFlux.le.DripTol) then
                If(DripSourceWidth(jj).gt.0.0) then
                  PrevDripFlux=wAppl(jj)/PERIOD*DripSourceWidth(jj)
                Else
                  PrevDripFlux=wAppl(jj)/PERIOD*Width(CenterBnd)
                Endif
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
            If(DripSpreadMode(jj).eq.1.or.
     !        DripSpreadMode(jj).eq.2.or.
     !        DripSpreadMode(jj).eq.4.or.
     !        DripSpreadMode(jj).eq.5) then
              If((DripSpreadMode(jj).eq.4.or.
     !          DripSpreadMode(jj).eq.5).and.KAT.eq.1.and.
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
            If(DripSpreadMode(jj).eq.4) then
              SourceDemandFlux=SourceRate*TotalMeasure
            ElseIf(DripSpreadMode(jj).eq.5) then
              SourceDemandFlux=SourceRate*DripSourceWidth(jj)
            ElseIf(DripSourceWidth(jj).gt.0.0) then
              SourceDemandFlux=SourceRate*DripSourceWidth(jj)
            Else
              SourceDemandFlux=SourceRate*Width(CenterBnd)
            Endif
            SourceFlux=SourceDemandFlux*PressureFactor
            SourceInputFlux=SourceFlux
            If((DripSpreadMode(jj).eq.3.or.
     !        DripSpreadMode(jj).eq.4.or.
     !        DripSpreadMode(jj).eq.5).and.Step.gt.0.0D0) then
              CapSum=0.0
              Do k=LeftPos,RightPos
                TestNode=DripSurfNode(k)
                LocalMeasure=Width(DripSurfBnd(k))
                If(DripSpreadMode(jj).eq.4.or.
     !            DripSpreadMode(jj).eq.5) then
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
                LocalCapFactor=1.0+amax1(0.0,-hNew(TestNode))/25.0
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
                  If(DripSpreadMode(jj).eq.4.or.
     !              DripSpreadMode(jj).eq.5) then
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
            If(DripSpreadMode(jj).eq.1.and.DripMode(jj).eq.3) then
              If(DripPcMax(jj).gt.0.0) then
                SourceDepth=DripPcMax(jj)
              Else
                SourceDepth=amin1(25.0,amax1(8.0,
     !            0.5*TargetWetWidth))
              Endif
c Redistribute direct drip water over unsaturated source nodes; only the
c remaining water after source saturation is reported as capacity loss.
              RemainingWater=SourceFlux*Step
              DirectIter=0
530           Continue
              If(RemainingWater.gt.DripTol.and.
     !        DirectIter.lt.NumNP) then
                DirectIter=DirectIter+1
                SourceVolume=0.0
                Do m=1,NumNP
                  NodeDepth=abs(y(SourceNode)-y(m))
                  If(x(m).ge.TargetLeft-DripTol.and.
     !              x(m).le.TargetRight+DripTol.and.
     !              NodeDepth.le.SourceDepth+DripTol) then
                    MatId=MatNumN(m)
                    ThetaR=Par(1,MatId)
                    ThetaS=Par(2,MatId)
                    AlphaVG=Par(5,MatId)
                    NVG=Par(6,MatId)
                    If(ThetaS.gt.ThetaR+DripTol.and.
     !                AlphaVG.gt.DripTol.and.NVG.gt.1.0) then
                      VgM=1.0-1.0/NVG
                      If(hNew(m).lt.0.0) then
                        ThetaRel=(1.0+(AlphaVG*abs(hNew(m)))**
     !                    NVG)**(-VgM)
                        ThetaCur=ThetaR+(ThetaS-ThetaR)*ThetaRel
                      Else
                        ThetaCur=ThetaS
                      Endif
                      MaxTheta=ThetaS-1.0E-5
                      If(MaxTheta.gt.ThetaCur+DripTol) then
                        SourceWeight=1.0
                        If(DripMode(jj).eq.3) then
                          If(KAT.eq.1.and.
     !                      abs(x(SourceNode)).le.DripTol) then
                            DistX=x(m)
                          Else
                            DistX=abs(x(m)-x(SourceNode))
                          Endif
                          RadialWeight=amax1(0.05,
     !                    1.0-DistX/amax1(TargetWetWidth,DripTol))
                          DepthWeight=amax1(0.50,
     !                    1.0-0.5*NodeDepth/
     !                    amax1(SourceDepth,DripTol))
                          SourceWeight=RadialWeight*DepthWeight
                        Endif
                        SourceVolume=SourceVolume+
     !                    nodeArea(m)*SourceWeight
                      Endif
                    Endif
                  Endif
                EndDo
                If(SourceVolume.gt.DripTol) then
                  WaterDepth=RemainingWater/SourceVolume
                  AppliedWater=0.0
                  Do m=1,NumNP
                    NodeDepth=abs(y(SourceNode)-y(m))
                    If(x(m).ge.TargetLeft-DripTol.and.
     !                x(m).le.TargetRight+DripTol.and.
     !                NodeDepth.le.SourceDepth+DripTol) then
                      MatId=MatNumN(m)
                      ThetaR=Par(1,MatId)
                      ThetaS=Par(2,MatId)
                      AlphaVG=Par(5,MatId)
                      NVG=Par(6,MatId)
                      If(ThetaS.gt.ThetaR+DripTol.and.
     !                  AlphaVG.gt.DripTol.and.NVG.gt.1.0) then
                        VgM=1.0-1.0/NVG
                        If(hNew(m).lt.0.0) then
                          ThetaRel=(1.0+(AlphaVG*abs(hNew(m)))**
     !                      NVG)**(-VgM)
                          ThetaCur=ThetaR+(ThetaS-ThetaR)*ThetaRel
                        Else
                          ThetaCur=ThetaS
                        Endif
                        MaxTheta=ThetaS-1.0E-5
                        CapacityDepth=amax1(0.0,MaxTheta-ThetaCur)
                        SourceWeight=1.0
                        If(DripMode(jj).eq.3) then
                          If(KAT.eq.1.and.
     !                      abs(x(SourceNode)).le.DripTol) then
                            DistX=x(m)
                          Else
                            DistX=abs(x(m)-x(SourceNode))
                          Endif
                          RadialWeight=amax1(0.05,
     !                    1.0-DistX/amax1(TargetWetWidth,DripTol))
                          DepthWeight=amax1(0.50,
     !                    1.0-0.5*NodeDepth/
     !                    amax1(SourceDepth,DripTol))
                          SourceWeight=RadialWeight*DepthWeight
                        Endif
                        AddDepth=amin1(WaterDepth*SourceWeight,
     !                    CapacityDepth)
                        If(AddDepth.gt.DripTol) then
                          ThetaTry=ThetaCur+AddDepth
                          ThetaTry=amax1(ThetaR+1.0E-5,
     !                    amin1(MaxTheta,ThetaTry))
                          ThetaRel=(ThetaTry-ThetaR)/(ThetaS-ThetaR)
                          ThetaRel=amax1(1.0E-5,amin1(0.99999,
     !                    ThetaRel))
                          hNew(m)=-((ThetaRel**(-1.0/VgM)-1.0)**
     !                    (1.0/NVG))/AlphaVG
                          ThNew(m)=ThetaTry
                          DripHOld(m)=hNew(m)
                          DripHTemp(m)=hNew(m)
                          DripThOld(m)=ThetaTry
                          DripSource_Rate(m)=DripSource_Rate(m)+
     !                    AddDepth/Step
                          AppliedWater=AppliedWater+
     !                    AddDepth*nodeArea(m)
                        Endif
                      Endif
                    Endif
                  EndDo
                  RemainingWater=RemainingWater-AppliedWater
                  DripSourceInput_Flux=DripSourceInput_Flux+
     !              dble(AppliedWater)
                  If(AppliedWater.gt.DripTol.and.
     !              RemainingWater.gt.DripTol) Goto 530
                Endif
              Endif
              If(RemainingWater.gt.DripTol.and.
     !        Width(CenterBnd).gt.DripTol) then
                DripSourceLoss_Flux=DripSourceLoss_Flux+
     !          dble(RemainingWater)
c Source capacity loss is reported separately as DripSourceLoss.
c Do not also count it as pressure loss.
              Endif
            Endif
            If(DripSpreadMode(jj).eq.4.or.
     !        DripSpreadMode(jj).eq.5) then
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
            ElseIf(DripSpreadMode(jj).eq.1.or.
     !        DripSpreadMode(jj).eq.2) then
              If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                HalfWidth=amax1(TargetWetWidth,DripTol)
              Else
                HalfWidth=amax1(0.5*TargetWetWidth,
     !            0.5*Width(CenterBnd))
              Endif
              WeightSum=0.0
              Do k=LeftPos,RightPos
                TestNode=DripSurfNode(k)
                If(DripSurfCount.eq.1) then
                  If(KAT.eq.1) then
                    SegmentLeft=0.0
                    SegmentRight=x(TestNode)
                  Else
                    SegmentLeft=x(TestNode)-0.5*Width(DripSurfBnd(k))
                    SegmentRight=x(TestNode)+0.5*Width(DripSurfBnd(k))
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
                If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                  DistX=x(TestNode)
                Else
                  DistX=abs(x(TestNode)-x(SourceNode))
                Endif
                NodeWeight=amax1(0.0,1.0-DistX/HalfWidth)
                WeightSum=WeightSum+
     !            NodeWeight*CoverMeasure
              EndDo
              If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol)
     !          WeightSum=0.0
              If(WeightSum.le.DripTol) then
                Do k=LeftPos,RightPos
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
                  CoverMeasure=DripCoverMeasure(KAT,SegmentLeft,
     !              SegmentRight,CoverLeft,CoverRight,
     !              Width(DripSurfBnd(k)))
                  If(CoverWidth.gt.DripTol) then
                    AddRate=SourceFlux*CoverMeasure/
     !                TotalMeasure/Width(DripSurfBnd(k))
                    DemandRate=SourceDemandFlux*CoverMeasure/
     !                TotalMeasure/Width(DripSurfBnd(k))
                    LossRate=(SourceDemandFlux-SourceInputFlux)*
     !                CoverMeasure/TotalMeasure/Width(DripSurfBnd(k))
                    If(DripMode(jj).ne.3) then
                      DripRate(DripSurfBnd(k))=
     !                  DripRate(DripSurfBnd(k))+AddRate
                    Endif
                    DripInput_Rate(DripSurfBnd(k))=
     !                DripInput_Rate(DripSurfBnd(k))+AddRate
                    DripDemand_Rate(DripSurfBnd(k))=
     !                DripDemand_Rate(DripSurfBnd(k))+DemandRate
                    DripPressureLoss_Rate(DripSurfBnd(k))=
     !                DripPressureLoss_Rate(DripSurfBnd(k))+LossRate
                    If(DripSpreadMode(jj).eq.2) then
                      DripPressureLimit_Rate(DripSurfBnd(k))=
     !                  DripPressureLimit_Rate(DripSurfBnd(k))+AddRate
                    Endif
                  Endif
                EndDo
              Else
                Do k=LeftPos,RightPos
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
                  CoverMeasure=DripCoverMeasure(KAT,SegmentLeft,
     !              SegmentRight,CoverLeft,CoverRight,
     !              Width(DripSurfBnd(k)))
                  If(KAT.eq.1.and.abs(x(SourceNode)).le.DripTol) then
                    DistX=x(TestNode)
                  Else
                    DistX=abs(x(TestNode)-x(SourceNode))
                  Endif
                  NodeWeight=amax1(0.0,1.0-DistX/HalfWidth)
                  AddRate=SourceFlux*NodeWeight*CoverMeasure/
     !              WeightSum/Width(DripSurfBnd(k))
                  DemandRate=SourceDemandFlux*NodeWeight*CoverMeasure/
     !              WeightSum/Width(DripSurfBnd(k))
                  LossRate=(SourceDemandFlux-SourceInputFlux)*
     !              NodeWeight*CoverMeasure/WeightSum/
     !              Width(DripSurfBnd(k))
                  If(CoverWidth.gt.DripTol) then
                    If(DripMode(jj).ne.3) then
                      DripRate(DripSurfBnd(k))=
     !                  DripRate(DripSurfBnd(k))+AddRate
                    Endif
                    DripInput_Rate(DripSurfBnd(k))=
     !                DripInput_Rate(DripSurfBnd(k))+AddRate
                    DripDemand_Rate(DripSurfBnd(k))=
     !                DripDemand_Rate(DripSurfBnd(k))+DemandRate
                    DripPressureLoss_Rate(DripSurfBnd(k))=
     !                DripPressureLoss_Rate(DripSurfBnd(k))+LossRate
                    If(DripSpreadMode(jj).eq.2) then
                      DripPressureLimit_Rate(DripSurfBnd(k))=
     !                  DripPressureLimit_Rate(DripSurfBnd(k))+AddRate
                    Endif
                  Endif
                EndDo
              Endif
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
                If(DripSpreadMode(jj).eq.3) then
                  DripStorageActive(DripSurfBnd(k))=1
                  DripStorageBoundary(DripSurfBnd(k))=1
                Endif
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
          EndDo
        ElseIf(time.ge.tAppl_stop(jj)) then
          Do in=1,Num_nodes(jj)
            WetRadius(jj,in)=0
            ShrinkCount(jj,in)=0
            DripEffHours(jj,in)=0.0
            DripLastTime(jj,in)=0.0
            DripLastPressure(jj,in)=0.0
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

      NextTime=1.E+32
      Do jj=1,Drip_times
        If(tAppl_start(jj).gt.time+0.001*Step) then
          NextTime=amin1(NextTime,tAppl_start(jj))
        Endif
        If(tAppl_stop(jj).gt.time+0.001*Step) then
          NextTime=amin1(NextTime,tAppl_stop(jj))
        Endif
        If(DripSpreadMode(jj).eq.1.or.
     !    DripSpreadMode(jj).eq.2) then
          Do i=2,9
            CurveTime=tAppl_start(jj)+DripCurveHour(i)/24.0
            If(CurveTime.gt.time+0.001*Step.and.
     !        CurveTime.lt.tAppl_stop(jj)) then
              NextTime=amin1(NextTime,CurveTime)
            Endif
          EndDo
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

      Real Function DripCurveHour(Index)
      Integer Index

      DripCurveHour=0.0
      If(Index.eq.2) DripCurveHour=0.03
      If(Index.eq.3) DripCurveHour=0.05
      If(Index.eq.4) DripCurveHour=0.10
      If(Index.eq.5) DripCurveHour=0.20
      If(Index.eq.6) DripCurveHour=0.30
      If(Index.eq.7) DripCurveHour=0.50
      If(Index.eq.8) DripCurveHour=1.00
      If(Index.eq.9) DripCurveHour=2.00
      Return
      End

      Real Function DripTargetWidth(MaxWetWidth,ElapsedHours)
      Real MaxWetWidth,ElapsedHours,HydTime(9),HydWidth(9)
      Real Progress
      Integer i

      DripTargetWidth=0.0
      If(MaxWetWidth.le.0.0) Return
      If(ElapsedHours.le.0.0) Return

      If(abs(MaxWetWidth-16.3).le.0.5) then
        HydTime(1)=0.0
        HydWidth(1)=0.0
        HydTime(2)=0.03
        HydWidth(2)=8.26
        HydTime(3)=0.05
        HydWidth(3)=10.86
        HydTime(4)=0.10
        HydWidth(4)=13.46
        HydTime(5)=0.20
        HydWidth(5)=15.52
        HydTime(6)=0.30
        HydWidth(6)=16.30
        HydTime(7)=0.50
        HydWidth(7)=16.58
        HydTime(8)=1.00
        HydWidth(8)=16.30
        HydTime(9)=2.00
        HydWidth(9)=16.30
      ElseIf(abs(MaxWetWidth-39.7).le.0.5) then
        HydTime(1)=0.0
        HydWidth(1)=0.0
        HydTime(2)=0.03
        HydWidth(2)=5.74
        HydTime(3)=0.05
        HydWidth(3)=12.34
        HydTime(4)=0.10
        HydWidth(4)=20.32
        HydTime(5)=0.20
        HydWidth(5)=25.24
        HydTime(6)=0.30
        HydWidth(6)=28.56
        HydTime(7)=0.50
        HydWidth(7)=32.16
        HydTime(8)=1.00
        HydWidth(8)=35.68
        HydTime(9)=2.00
        HydWidth(9)=39.70
      Else
        Progress=amin1(1.0,ElapsedHours/2.0)
        DripTargetWidth=MaxWetWidth*sqrt(Progress)
        Return
      Endif

      If(ElapsedHours.ge.HydTime(9)) then
        DripTargetWidth=HydWidth(9)
      Else
        Do i=2,9
          If(ElapsedHours.le.HydTime(i)) then
            Progress=(ElapsedHours-HydTime(i-1))/
     !        (HydTime(i)-HydTime(i-1))
            DripTargetWidth=HydWidth(i-1)+
     !        Progress*(HydWidth(i)-HydWidth(i-1))
            GoTo 10
          Endif
        EndDo
10      Continue
      Endif
      DripTargetWidth=amax1(0.0,amin1(MaxWetWidth,DripTargetWidth))
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
