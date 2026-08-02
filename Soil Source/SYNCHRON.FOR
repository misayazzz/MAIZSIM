*|||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||*
       
      Subroutine Synchronizer()
      Include 'public.ins'
      Include 'PuSurface.ins'

      character line*40
      Character*10 SDate,FDate
      double precision tFix,tRigid,dt,t,dtmax,TimeGap
      real*4 progress, Prev_progress,Clock_start
      integer*4 ProgressFlag,RunToEnd,AdaptiveIter,
     !          PartitionCount,PartitionMinimum,PartitionMaximum
      Common /Sychron/ProgressFlag, Prev_progress, 
     !  Clock_start,RunToEnd
*
      If (lInput.eq.1) then
        If (NumMod.eq.-1) then
          Open(42,file=TimeFile,status='old',err=10)
          im=1
          Read(42,*,ERR=10)
          im=im+1
          Read(42,*,ERR=10)
          im=im+1
          Read(42,*,ERR=10) SDate,Step,dtMin,dMul1,dMul2,Fdate
          Read(42,*,ERR=10)
          Read(42,*,ERR=10) DailyOutput,HourlyOutput
          Read(42,*,ERR=10)
          Read(42,*,ERR=10) DailyWeather,HourlyWeather
          Read(42,*,ERR=10)
          Read(42,*,ERR=10) RunToEnd
          Close(42)
          Time=Julday(Sdate)
          TFin=Julday(Fdate)
          dtOpt=Step
          Tinit=Time
          NumMod=0
          RunFlag=1
          Prev_progress=0.0 ! write progress the first time
          Progress=0.0
          Call CPU_TIME(ClockStart)
C Beginday is when the plant model starts. If the model time start is greater
C than the sowing day then this will be an error condition.
          if (time.GT.SowingDay) goto 110
          if (beginDay.le.0) then 
            BeginDay=max(int(time),SowingDay-3)
          endif
          Return
10        Call errmes(im,im-1)
        Else
          lInput=0
        Endif
      Else
        t=Time
        tRigid=1.E+30
        Do j=1,NumMod
          if(tNext(j).lt.tRigid) tRigid = tNext(j)
        Enddo
cccz remove this debugging trick
cccz        if (time.gt.51.27) then
cccz          hhh=1
cccz          endif
        dtMax=dmin1(dtMx(1),dtMx(2),dtMx(3),dtMx(4))
        tFix=dmin1(tRigid,tTDB(1),tTDB(2),tTDB(3),tTDB(4),tFin)
        AdaptiveIter=Iter
        If(DripMode6Active.eq.1.and.DripMode6AdaptiveIter.gt.0)
     !    AdaptiveIter=DripMode6AdaptiveIter
        If(AdaptiveIter.le.3.and.(tFix-t).ge.dMul1*dtOpt)
     !  dtOpt=dmin1(dtMax,dMul1*dtOpt)
        If(AdaptiveIter.ge.7)
     !  dtOpt=dmax1(dtMin,dMul2*dtOpt)
c Keep dtOpt as an admissible suggestion.  A rigid endpoint can still make
c the actual dt smaller through min(dtOpt,tFix-t), but that endpoint remainder
c must not become the proposal for the following non-rigid interval.
        dtOpt=dmax1(dtOpt,dtMin)
        TimeGap=tFix-t
        dt=dmin1(dtOpt,TimeGap)
cdt  RunFlag is set by the crop model when the crop reaches maturity
cdt can be overridden for a full year sim of RunToEnd>0
        If ((abs(dt/t).lt.1.E-20).or.
     !           ((RunFlag.eq.0).and.(RunToEnd.eq.0))) then
	    write(*,*) 'Finished at',time
          Stop
        Endif
c Partition the complete interval to the next rigid endpoint.  When a
c feasible integer count exists, every public step respects both dtMax and
c dtMin.  A genuinely closer rigid endpoint remains one exact small step.
        If(TimeGap.lt.dtMin) then
          PartitionCount=1
        Else
          PartitionMinimum=max(1,ceiling(TimeGap/dtMax))
          PartitionMaximum=max(1,idint(TimeGap/dtMin))
          PartitionCount=max(1,nint(TimeGap/dt))
          If(PartitionMinimum.le.PartitionMaximum) then
            PartitionCount=max(PartitionMinimum,
     !        min(PartitionCount,PartitionMaximum))
          Else
c Exact endpoint alignment and the nonlinear lower bound take precedence
c when no integer partition can also satisfy the requested maximum step.
            PartitionCount=PartitionMaximum
          Endif
        Endif
        dt=TimeGap/dble(PartitionCount)
        Step = dt
      Endif
       WRITE(LINE,100) TIME
*       CALL COUP@(LINE,5,1,24)
*      write(*,*) Time
      Time = Time + Step
      
      progress=(Time-Tinit)/(Tfin-Tinit)*100.0
      progress=int(progress)
      temp=Mod(progress,4.0)
      if ((Mod(progress,4.0).eq.0).and.progress.gt.0) then 
         if(abs(progress-Prev_progress).ge.4) then
           write(*,105) 'Progress=',Int(progress)
           Prev_progress=progress
          endif
      endif
            
100    FORMAT(1x,G12.5)
105    FORMAT(A10,I4)
      Return
110   Stop 'Sowing date cannot be earlier than the start of the 
     & soil model'
      End
