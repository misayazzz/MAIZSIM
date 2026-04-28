Attribute VB_Name = "RunConfiguredIdsM"
Option Explicit

Public Sub RunConfiguredIds()
    Dim configSheet As Excel.Worksheet
    Dim rowIndex As Long
    Dim idStr As String

    Set configSheet = ThisWorkbook.Worksheets("_PythonConfig")
    rowIndex = 2

    If Trim(CStr(configSheet.Cells(rowIndex, 1).Value)) = "" Then
        Err.Raise vbObjectError + 513, "RunConfiguredIds", "No selected IDs were provided in _PythonConfig."
    End If

    Do While Trim(CStr(configSheet.Cells(rowIndex, 1).Value)) <> ""
        idStr = Trim(CStr(configSheet.Cells(rowIndex, 1).Value))

        MakeFolders idStr
        WriteBio idStr
        WriteIni idStr
        WriteSol idStr
        WriteGas idStr
        WriteMan idStr
        WriteIrrig idStr
        WriteMulch idStr
        WriteLayer idStr
        WriteTime idStr
        WriteVar idStr
        WriteClim idStr
        WriteNit idStr
        WriteRun idStr
        WriteDrip idStr
        WriteWatMoveP idStr
        WriteWea idStr

        rowIndex = rowIndex + 1
    Loop
End Sub
