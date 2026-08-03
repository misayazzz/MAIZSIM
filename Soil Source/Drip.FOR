* Fixed-contact finite-supply equivalent drip-line source for a Cartesian
* half-domain.  The drip tape is located at x=0.  Emitter discharge is
* converted to the water supply represented by one half-domain and is
* distributed conservatively over one physical contact interval.

      Subroutine Drip()
      Include 'public.ins'
      Include 'PuSurface.ins'
      Parameter (Max_times=75)
      Integer Drip_times,Num_nodes(Max_times),
     !        nAppl(Max_times),SourceBnd(Max_times),
     !        SourceSurfPos(Max_times),DripSurfNode(NumBPD),
     !        DripSurfBnd(NumBPD),DripSurfCount,
     !        FieldCount,DripFieldCount,found,ios,m,DripActive,
     !        Mode6EmitterNode,DripBaseDtMxSet
      Double precision PERIOD,LITRE_TO_CM3,HALF_LINE_FACTOR
      Parameter (PERIOD=1.0D0/24.0D0,LITRE_TO_CM3=1000.0D0)
      Parameter (HALF_LINE_FACTOR=0.5D0*24.0D0*LITRE_TO_CM3)
      Real EmitterFlowLph(Max_times),EmitterSpacingCm(Max_times),
     !     ContactWidthCm(Max_times),SegmentLeft,SegmentRight,
     !     CoverLeft,CoverRight,CoverWidth,SegmentWidth,LocalMeasure,
     !     DripTol,SurfaceMin,SurfaceMax
      Double Precision tAppl_start(Max_times),tAppl_stop(Max_times),
     !                 start_hour(Max_times),stop_hour(Max_times),
     !                 NextTime,DripBaseDtMx,DripTimeTol,
     !                 ExternalFlux,StoredVolume,SolverSupply
      Character*10 Start_Date(Max_times),Stop_Date(Max_times)
      Character*256 EventLine

      Common /DripC/ tAppl_start,tAppl_stop,EmitterFlowLph,
     !     EmitterSpacingCm,ContactWidthCm,Drip_times,Num_nodes,
     !     nAppl,SourceBnd,SourceSurfPos,DripSurfNode,DripSurfBnd,
     !     DripSurfCount,applied,ModNum
      Save DripBaseDtMx,DripBaseDtMxSet
      Data DripBaseDtMxSet /0/

      DripTol=1.0E-5
      If(lInput.eq.1) then
        DripInput_Flux=0.0D0
        DripActualInfil_Flux=0.0D0
        DripStorageChange_Flux=0.0D0
        DripOverflow_Flux=0.0D0
        DripMode6Available_Flux=0.0D0
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
        DripMode6Active=0
        DripMode6Count=0
        DripMode6IterationCount=0
        DripMode6AdaptiveIter=0
        DripMode6ContactTotal=0.0D0
        DripMode6ContactWidth=0.0D0
        DripBypassRunoff=0
        Do k=1,NumBPD
          DripSurfaceStorage(k)=0.0D0
          DripMode6AssignedFlux(k)=0.0D0
          DripMode6ContactMeasure(k)=0.0D0
          DripMode6FluxActive(k)=0
          DripMode6HeadActive(k)=0
          DripMode6AtmosHeadActive(k)=0
          DripMode6CandidateOwner(k)=0
          DripMode6BoundaryOwner(k)=0
          DripSurfNode(k)=0
          DripSurfBnd(k)=0
        EndDo
        Do k=1,NumBP
          n=KXB(k)
          If(CodeW(n).eq.4) DripMode6AtmosHeadActive(k)=1
        EndDo
        DripMode6DemandFlux(1)=0.0D0
        DripMode6InputFlux(1)=0.0D0
        DripMode6ExternalFlux(1)=0.0D0
        DripMode6StorageStart(1)=0.0D0
        DripMode6RemainingFlux(1)=0.0D0
        DripMode6AcceptedFlux(1)=0.0D0
        DripMode6CenterBnd(1)=0
        DripMode6Closed(1)=1
        Do i=1,Max_times
          EmitterFlowLph(i)=0.0
          EmitterSpacingCm(i)=0.0
          ContactWidthCm(i)=0.0
          Num_nodes(i)=0
          nAppl(i)=0
          SourceBnd(i)=0
          SourceSurfPos(i)=0
        EndDo

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

        If(Drip_times.eq.0) then
          tNext(ModNum)=1.0D22
          Close(40)
          Return
        Endif
        If(KAT.ne.2) Stop 'Drip line source requires Cartesian KAT=2'
        If(DripSurfCount.lt.2) Stop 'Drip needs a surface grid'
        SurfaceMin=x(DripSurfNode(1))
        SurfaceMax=x(DripSurfNode(DripSurfCount))
        If(abs(SurfaceMin).gt.DripTol) then
          Stop 'Drip half-domain surface must start at x=0'
        Endif

        Read(40,*,Err=20)
        Mode6EmitterNode=0
        Do i=1,Drip_times
          Read(40,'(A)',Err=20) EventLine
          FieldCount=DripFieldCount(EventLine)
          If(FieldCount.ne.8) then
            Stop 'Drip event requires exactly 8 fields'
          Endif
          Read(EventLine,*,IOSTAT=ios) Start_Date(i),start_hour(i),
     !      Stop_Date(i),stop_hour(i),EmitterFlowLph(i),
     !      EmitterSpacingCm(i),ContactWidthCm(i),Num_nodes(i)
          If(ios.ne.0) Stop 'Invalid fixed-contact drip event fields'
          If(EmitterFlowLph(i).le.0.0) then
            Stop 'EmitterFlowLph must be positive'
          Endif
          If(EmitterSpacingCm(i).le.0.0) then
            Stop 'EmitterSpacingCm must be positive'
          Endif
          If(ContactWidthCm(i).le.0.0.or.
     !      ContactWidthCm(i).gt.SurfaceMax+DripTol) then
            Stop 'ContactWidthCm is outside the half-domain surface'
          Endif
          If(Num_nodes(i).ne.1) then
            Stop 'Fixed-contact drip requires exactly one x=0 node'
          Endif
          Read(40,*,Err=20)
          Read(40,*,Err=20) nAppl(i)
          If(Mode6EmitterNode.eq.0) then
            Mode6EmitterNode=nAppl(i)
          ElseIf(nAppl(i).ne.Mode6EmitterNode) then
            Stop 'All drip events must use the same x=0 node'
          Endif
          If(i.gt.1) then
            If(abs(EmitterSpacingCm(i)-EmitterSpacingCm(1)).gt.
     !        DripTol) Stop 'Emitter spacing must remain fixed'
            If(abs(ContactWidthCm(i)-ContactWidthCm(1)).gt.
     !        DripTol) Stop 'Contact width must remain fixed'
          Endif
        EndDo
        Close(40)

        NextTime=1.0D32
        Do i=1,Drip_times
          tAppl_start(i)=dble(julday(Start_Date(i)))+
     !      start_hour(i)/24.0D0
          tAppl_stop(i)=dble(julday(Stop_Date(i)))+
     !      stop_hour(i)/24.0D0
          If(tAppl_stop(i).le.tAppl_start(i)) then
            Stop 'Invalid drip irrigation time window'
          Endif
          Do m=1,i-1
            If(tAppl_start(i).lt.tAppl_stop(m).and.
     !        tAppl_start(m).lt.tAppl_stop(i)) then
              Stop 'Drip irrigation events must not overlap'
            Endif
          EndDo
          found=0
          Do k=1,DripSurfCount
            If(DripSurfNode(k).eq.nAppl(i)) then
              found=1
              SourceSurfPos(i)=k
              SourceBnd(i)=DripSurfBnd(k)
            Endif
          EndDo
          If(found.eq.0) Stop 'Drip node is not a surface boundary'
          If(abs(x(nAppl(i))).gt.DripTol) then
            Stop 'Equivalent drip line must be located at x=0'
          Endif
          NextTime=dmin1(NextTime,tAppl_start(i))
        EndDo
        DripMode6CenterBnd(1)=SourceBnd(1)
        DripMode6ContactWidth=dble(ContactWidthCm(1))

c Discretize the fixed physical interval [0,ContactWidthCm] once.  The
c boundary quadrature measure, including a partially covered edge node, is
c retained and later used for every conservative flux/storage distribution.
        Do k=1,DripSurfCount
          If(k.eq.1) then
            SegmentLeft=0.0
            SegmentRight=0.5*(x(DripSurfNode(k))+
     !        x(DripSurfNode(k+1)))
          ElseIf(k.eq.DripSurfCount) then
            SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !        x(DripSurfNode(k)))
            SegmentRight=SurfaceMax
          Else
            SegmentLeft=0.5*(x(DripSurfNode(k-1))+
     !        x(DripSurfNode(k)))
            SegmentRight=0.5*(x(DripSurfNode(k))+
     !        x(DripSurfNode(k+1)))
          Endif
          CoverLeft=amax1(SegmentLeft,0.0)
          CoverRight=amin1(SegmentRight,ContactWidthCm(1))
          CoverWidth=amax1(0.0,CoverRight-CoverLeft)
          SegmentWidth=amax1(0.0,SegmentRight-SegmentLeft)
          LocalMeasure=0.0
          If(CoverWidth.gt.DripTol.and.SegmentWidth.gt.DripTol) then
            LocalMeasure=Width(DripSurfBnd(k))*CoverWidth/SegmentWidth
          Endif
          DripMode6ContactMeasure(DripSurfBnd(k))=
     !      dble(LocalMeasure)
          DripMode6ContactTotal=DripMode6ContactTotal+
     !      dble(LocalMeasure)
        EndDo
        If(DripMode6ContactTotal.le.dble(DripTol)) then
          Stop 'Fixed drip contact has zero boundary measure'
        Endif
        tNext(ModNum)=NextTime
      Endif

      If(Drip_times.eq.0) Return
      DripTimeTol=1.0D-10

c Preserve the public outer-step contract while limiting only the Richards
c substep target during active supply or drainage of local ponding storage.
      If(DripBaseDtMxSet.eq.0.and.lInput.eq.0) then
        DripBaseDtMx=dtMx(1)
        DripBaseDtMxSet=1
      Endif
      If(DripBaseDtMxSet.eq.1) dtMx(1)=DripBaseDtMx
      DripActive=0
      Do i=1,Drip_times
        If(time.ge.tAppl_start(i).and.time.lt.tAppl_stop(i)) then
          DripActive=1
        Endif
      EndDo
      StoredVolume=0.0D0
      Do k=1,NumBP
        StoredVolume=StoredVolume+DripSurfaceStorage(k)
      EndDo
      If(StoredVolume.gt.1.0D-12) DripActive=1
      If(DripActive.eq.1) then
        dtMx(1)=dmin1(dtMx(1),0.005D0)
        dtOpt=dmin1(dtOpt,0.005D0)
      Endif

c Remove the preceding drip overlay and restore the independently accepted
c atmospheric complementarity state before defining this outer step.
      Do k=1,NumBP
        If(DripMode6CandidateOwner(k).gt.0.or.
     !    DripMode6BoundaryOwner(k).gt.0) then
          n=KXB(k)
          If(DripMode6AtmosHeadActive(k).eq.1) then
            Q(n)=0.0
            CodeW(n)=4
          Else
            Q(n)=-VarBW(k,3)*Width(k)
            CodeW(n)=-4
          Endif
        Endif
        DripMode6AssignedFlux(k)=0.0D0
        DripMode6FluxActive(k)=0
        DripMode6HeadActive(k)=0
        DripMode6CandidateOwner(k)=0
        DripMode6BoundaryOwner(k)=0
      EndDo
      DripMode6Active=0
      DripMode6Count=0
      DripMode6IterationCount=0
      DripMode6AdaptiveIter=0
      DripMode6DemandFlux(1)=0.0D0
      DripMode6InputFlux(1)=0.0D0
      DripMode6ExternalFlux(1)=0.0D0
      DripMode6StorageStart(1)=StoredVolume
      DripMode6RemainingFlux(1)=0.0D0
      DripMode6AcceptedFlux(1)=0.0D0
      DripMode6Closed(1)=1

      ExternalFlux=0.0D0
      Do i=1,Drip_times
c Synchronizer evaluates boundary modules at the backward-Euler endpoint,
c hence the physical event interval is (start,stop].
        If(time.gt.tAppl_start(i)+DripTimeTol.and.
     !    time.le.tAppl_stop(i)+DripTimeTol) then
          ExternalFlux=dble(EmitterFlowLph(i))*HALF_LINE_FACTOR/
     !      dble(EmitterSpacingCm(i))
        Endif
      EndDo

      If(ExternalFlux.gt.1.0D-12.or.StoredVolume.gt.1.0D-12) then
        DripMode6Active=1
        DripMode6Count=1
        DripMode6DemandFlux(1)=ExternalFlux
        DripMode6ExternalFlux(1)=ExternalFlux
        If(Step.gt.0.0D0) then
          SolverSupply=ExternalFlux+StoredVolume/Step
        Else
          SolverSupply=ExternalFlux
        Endif
        DripMode6InputFlux(1)=SolverSupply
        DripMode6RemainingFlux(1)=SolverSupply
        DripMode6Closed(1)=0
        Do k=1,NumBP
          If(DripMode6ContactMeasure(k).gt.1.0D-12) then
            DripMode6CandidateOwner(k)=1
            DripMode6BoundaryOwner(k)=1
            DripMode6FluxActive(k)=1
            DripMode6AssignedFlux(k)=SolverSupply*
     !        DripMode6ContactMeasure(k)/DripMode6ContactTotal
          Endif
        EndDo
      Endif
      DripBypassRunoff=DripMode6Active

      NextTime=1.0D32
      Do i=1,Drip_times
        If(tAppl_start(i).gt.time+0.001D0*Step) then
          NextTime=dmin1(NextTime,tAppl_start(i))
        Endif
        If(tAppl_stop(i).gt.time+0.001D0*Step) then
          NextTime=dmin1(NextTime,tAppl_stop(i))
        Endif
      EndDo
      tNext(ModNum)=NextTime
      Return
 20   Stop 'Drip data error'
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
