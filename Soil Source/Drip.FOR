* This subroutine implements drip irrigation

* Note that the first day  for drip irrigation needs to be at least one
* day later than the initial time in the file in the time folder. This
* allows the program to initialize the soil properties and fluxes.

      Subroutine Drip()
      Include 'public.ins'
      Include 'PuSurface.ins'
      Integer Max_times,Drip_times,Num_nodes,nAppl,applied,found,
     ! Max_nodes,SourceBnd,SourceSurfPos,WetRadius,DripSurfNode,
     ! DripSurfBnd,DripSurfCount,DripMode,ShrinkCount
      Parameter (Max_times=75, Max_nodes=150)
      Parameter (PERIOD =1./24.)
      Real wAppl,tAppl_start,tAppl_stop,DripRate(NumBPD),
     !     CurrentRate,
     !     NextTime,DripTol,LastRate,LastAir,LastMulch,LastBW,
     !     start_hour(Max_times),stop_hour(Max_times),TotalWidth,
     !     SourceFlux,AddRate,PressureFactor,Havail,HeadPressure,
     !     DripHIn,DripExp,DripPcMin,DripPcMax,SourceRate,
     !     SourceDemandFlux,DemandRate,LossRate,DripWetWidthMax,
     !     SurfaceWidth,MaxWetWidth,CandidateWidth,NodeExcess,
     !     ExcessFlux,PrevDripFlux,DripExcessFrac,
     !     DripDefaultWetWidth
      Integer CenterPos,CenterBnd,SourceNode,ActiveRadius,
     !        LeftPos,RightPos,NeedExpand,CanShrink,MaxRadius,
     !        EdgeMaxRadius,CandidateRadius,CandidateLeft,
     !        CandidateRight,ActiveNodes,TestNode,ios
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
     !     DripWetWidthMax(Max_times),applied,ModNum

      DripTol=1.0E-5
      DripExcessFrac=0.05
      DripDefaultWetWidth=20.0
      If(lInput.eq.1) then
        DripInput_Flux=0.0D0
        DripDemand_Flux=0.0D0
        DripPressureLoss_Flux=0.0D0
        DripHydraulicExcess_Flux=0.0D0
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
          DripSurfNode(i)=0
          DripSurfBnd(i)=0
        EndDo
        Do i=1,Max_times
          DripMode(i)=0
          DripHIn(i)=0.0
          DripExp(i)=1.0
          DripPcMin(i)=0.0
          DripPcMax(i)=0.0
          DripWetWidthMax(i)=0.0
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
        Do i=1,Drip_times
          Read(40,'(A)',Err=20) EventLine
          Read(EventLine,*,Err=20) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i)
          DripMode(i)=0
          DripHIn(i)=0.0
          DripExp(i)=1.0
          DripPcMin(i)=0.0
          DripPcMax(i)=0.0
          DripWetWidthMax(i)=0.0
          Read(EventLine,*,IOSTAT=ios) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i),
     !       DripMode(i),DripHIn(i),DripExp(i),
     !       DripPcMin(i),DripPcMax(i),DripWetWidthMax(i)
          If(ios.ne.0) then
            DripWetWidthMax(i)=0.0
            Read(EventLine,*,IOSTAT=ios) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i),
     !       DripMode(i),DripHIn(i),DripExp(i),
     !       DripPcMin(i),DripPcMax(i)
            If(ios.ne.0) then
              DripMode(i)=0
              DripHIn(i)=0.0
              DripExp(i)=1.0
              DripPcMin(i)=0.0
              DripPcMax(i)=0.0
              DripWetWidthMax(i)=0.0
            Endif
          Endif
          If(Num_nodes(i).lt.1.or.Num_nodes(i).gt.Max_nodes) then
            Stop 'Invalid number of drip nodes'
          Endif
          If(wAppl(i).lt.0.0) then
            Stop 'Invalid drip irrigation rate'
          Endif
          If(DripMode(i).lt.0.or.DripMode(i).gt.2) then
            Stop 'Invalid drip pressure mode'
          Endif
          If(DripMode(i).gt.0.and.DripHIn(i).le.0.0) then
            Stop 'Invalid drip inlet pressure'
          Endif
          If(DripExp(i).le.0.0) DripExp(i)=1.0
          If(DripWetWidthMax(i).lt.0.0) then
            Stop 'Invalid drip wetted width limit'
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

      Do i=1,NumBP
        DripRate(i)=0.0
        DripDemand_Rate(i)=0.0
        DripPressureLoss_Rate(i)=0.0
      EndDo
      DripWetNodes_StepSum=0.0D0
      DripWetNodes_StepMax=0.0D0
      DripWetWidth_StepSum=0.0D0
      DripWetWidth_StepMax=0.0D0
      DripPressureFactor_StepSum=0.0D0
      DripPressureFactor_StepMin=1.0D30
      DripDiag_StepCount=0.0D0

      Do jj=1,Drip_times
        If(time.ge.tAppl_start(jj).and.time.lt.tAppl_stop(jj)) then
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
            MaxWetWidth=amax1(MaxWetWidth,Width(CenterBnd))
            EdgeMaxRadius=max(CenterPos-1,DripSurfCount-CenterPos)
            MaxRadius=0
            Do CandidateRadius=1,EdgeMaxRadius
              CandidateLeft=max(1,CenterPos-CandidateRadius)
              CandidateRight=min(DripSurfCount,
     !          CenterPos+CandidateRadius)
              CandidateWidth=0.0
              Do k=CandidateLeft,CandidateRight
                CandidateWidth=CandidateWidth+Width(DripSurfBnd(k))
              EndDo
              If(CandidateWidth.le.MaxWetWidth+DripTol) then
                MaxRadius=CandidateRadius
              Endif
            EndDo
            If(WetRadius(jj,in).gt.MaxRadius) then
              WetRadius(jj,in)=MaxRadius
              ActiveRadius=WetRadius(jj,in)
              LeftPos=max(1,CenterPos-ActiveRadius)
              RightPos=min(DripSurfCount,CenterPos+ActiveRadius)
            Endif
            ExcessFlux=0.0
            PrevDripFlux=0.0
            Do k=LeftPos,RightPos
              TestNode=DripSurfNode(k)
              NodeExcess=amax1(RO(TestNode),0.0)
              ExcessFlux=ExcessFlux+NodeExcess
              PrevDripFlux=PrevDripFlux+
     !          LastRate(DripSurfBnd(k))*Width(DripSurfBnd(k))
            EndDo
            If(PrevDripFlux.le.DripTol) then
              PrevDripFlux=wAppl(jj)/PERIOD*Width(CenterBnd)
            Endif
            If(ExcessFlux.gt.amax1(DripTol,
     !        DripExcessFrac*PrevDripFlux)) NeedExpand=1
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
            ActiveRadius=WetRadius(jj,in)
            LeftPos=max(1,CenterPos-ActiveRadius)
            RightPos=min(DripSurfCount,CenterPos+ActiveRadius)
            ActiveNodes=RightPos-LeftPos+1
            TotalWidth=0.0
            Do k=LeftPos,RightPos
              TotalWidth=TotalWidth+Width(DripSurfBnd(k))
            EndDo
            If(TotalWidth.le.0.0) Stop 'Invalid drip wetted width'
            PressureFactor=1.0
            If(DripMode(jj).gt.0) then
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
            SourceRate=wAppl(jj)/PERIOD
            SourceDemandFlux=SourceRate*Width(CenterBnd)
            SourceFlux=SourceDemandFlux*PressureFactor
            AddRate=SourceFlux/TotalWidth
            DemandRate=SourceDemandFlux/TotalWidth
            LossRate=(SourceDemandFlux-SourceFlux)/TotalWidth
            Do k=LeftPos,RightPos
              DripRate(DripSurfBnd(k))=DripRate(DripSurfBnd(k))+AddRate
              DripDemand_Rate(DripSurfBnd(k))=
     !          DripDemand_Rate(DripSurfBnd(k))+DemandRate
              DripPressureLoss_Rate(DripSurfBnd(k))=
     !          DripPressureLoss_Rate(DripSurfBnd(k))+LossRate
            EndDo
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
          EndDo
        Endif
      EndDo

      Do i=1,NumBP
        n=KXB(i)
        CurrentRate=DripRate(i)

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
        DripInput_Rate(i)=CurrentRate
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
      EndDo
      tNext(ModNum)=NextTime
      Return
20    Stop 'Drip data error'
      End
