* This subroutine implements drip irrigation

* Note that the first day  for drip irrigation needs to be at least one
* day later than the initial time in the file in the time folder. This
* allows the program to initialize the soil properties and fluxes.

      Subroutine Drip()
      Include 'public.ins'
      Include 'PuSurface.ins'
      Integer Max_times,Drip_times,Num_nodes,nAppl,applied,found,
     ! Max_nodes
      Parameter (Max_times=75, Max_nodes=150)
      Parameter (PERIOD =1./24.)
      Real wAppl,tAppl_start,tAppl_stop,DripRate,CurrentRate,
     !     NextTime,DripTol,LastRate,LastAir,LastMulch,LastBW,
     !     start_hour(Max_times),stop_hour(Max_times)

      Character*10 Start_Date(Max_times),Stop_Date(Max_times)

      Common /DripC/ tAppl_start(Max_times), tAppl_stop(Max_times),
     !     wAppl(Max_times), Drip_times,
     !     Num_nodes(Max_times), nAppl(Max_times, Max_nodes),
     !     LastRate(NumBPD),LastAir(NumBPD),LastMulch(NumBPD),
     !     LastBW(NumBPD),applied,ModNum

      DripTol=1.0E-5
      If(lInput.eq.1) then
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
        EndDo
        if (Drip_times.eq.0)  then
          tNext(ModNum)=1e22
          Close(40)
          Return
        End if
        Read(40,*,Err=20)
        Do i=1,Drip_times
          Read(40,*,Err=20) Start_Date(i), Start_hour(i),
     !       Stop_Date(i), Stop_hour(i), wAppl(i), Num_nodes(i)
          If(Num_nodes(i).lt.1.or.Num_nodes(i).gt.Max_nodes) then
            Stop 'Invalid number of drip nodes'
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
            Do k=1,NumBP
              n=KXB(k)
              If(n.eq.nAppl(i,j)) then
                found=1
                If(abs(CodeW(n)).ne.4) then
                  Stop 'Drip node is not a surface water boundary'
                Endif
              Endif
            EndDo
            If(found.eq.0) Stop 'Drip node not found in boundary list'
          EndDo
          NextTime=amin1(NextTime,tAppl_start(i))
        EndDo
        tNext(ModNum)=NextTime
      Endif

      If(Drip_times.eq.0) Return

      Do i=1,NumBP
        n=KXB(i)
        CurrentRate=0.0
        If(abs(CodeW(n)).eq.4) then
          Do jj=1,Drip_times
            If(time.ge.tAppl_start(jj).and.time.lt.tAppl_stop(jj)) then
              Do in=1,Num_nodes(jj)
                If(n.eq.nAppl(jj,in)) then
                  CurrentRate=CurrentRate+wAppl(jj)/PERIOD
                Endif
              EndDo
            Endif
          EndDo
        Endif

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
      EndDo
      tNext(ModNum)=NextTime
      Return
20    Stop 'Drip data error'
      End
