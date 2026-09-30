Attribute VB_Name = "KontrolaVykresu"
' =====================================================================================
'  Kontrola výkresu – propojení s MicroStationem (V8i i CONNECT)
'
'  Makro jen ČTE seznam chyb, který aplikace Kontrola výkresu uloží vedle výkresu
'  (<název výkresu>_chyby.txt), a ukáže chyby jako DOČASNÉ kroužky. Kroužky se do DGN
'  neukládají a výkres nijak nemění – opravujete sami.
'
'  Makra (Nástroje → Makro → Makra, nebo key-in  vba run KV_Dalsi ):
'    KV_Nacist     načte chyby a zobrazí kroužky
'    KV_Dalsi      přiblíží další chybu a napíše ji do stavového řádku
'    KV_Predchozi  přiblíží předchozí chybu
'    KV_Znovu      znovu ukáže aktuální chybu (i s textem v okně)
'    KV_Skryt      schová kroužky
'  Doporučení: přiřaďte KV_Dalsi a KV_Predchozi funkčním klávesám (např. F8 a F7):
'    Pracovní prostředí → Funkční klávesy → F8 → key-in:  vba run KV_Dalsi
' =====================================================================================
Option Explicit

Private kvX() As Double
Private kvY() As Double
Private kvText() As String
Private kvSev() As String
Private kvCount As Long
Private kvIndex As Long
Private kvMarks As TransientElementContainer
Private kvFile As String

Private Function KV_Soubor() As String
    ' <složka výkresu>\<název výkresu bez přípony>_chyby.txt
    Dim f As String, p As Long
    f = ActiveDesignFile.FullName
    p = InStrRev(f, ".")
    If p > 0 Then f = Left$(f, p - 1)
    KV_Soubor = f & "_chyby.txt"
End Function

Private Function KV_Cislo(ByVal s As String) As Double
    ' Val() čte vždy desetinnou tečku, nezávisle na nastavení Windows
    KV_Cislo = Val(Replace(Trim$(s), ",", "."))
End Function

Public Sub KV_Nacist()
    Dim f As Integer, radek As String, casti() As String, n As Long
    kvFile = KV_Soubor()
    If Dir$(kvFile) = "" Then
        MsgBox "Seznam chyb nenalezen:" & vbCrLf & kvFile & vbCrLf & vbCrLf & _
               "V aplikaci Kontrola výkresu zapněte Kontrola → Posílat chyby do MicroStationu " & _
               "a výkres (DXF uložený vedle DGN se stejným názvem) zkontrolujte.", vbExclamation, "Kontrola výkresu"
        Exit Sub
    End If
    kvCount = 0
    ReDim kvX(0 To 999): ReDim kvY(0 To 999): ReDim kvText(0 To 999): ReDim kvSev(0 To 999)
    f = FreeFile
    Open kvFile For Input As #f
    Do While Not EOF(f)
        Line Input #f, radek
        If Len(radek) > 0 And Left$(radek, 1) <> "#" Then
            casti = Split(radek, vbTab)
            If UBound(casti) >= 4 Then
                If kvCount > UBound(kvX) Then
                    n = UBound(kvX) * 2 + 1
                    ReDim Preserve kvX(0 To n): ReDim Preserve kvY(0 To n)
                    ReDim Preserve kvText(0 To n): ReDim Preserve kvSev(0 To n)
                End If
                kvX(kvCount) = KV_Cislo(casti(1))
                kvY(kvCount) = KV_Cislo(casti(2))
                kvSev(kvCount) = casti(3)
                kvText(kvCount) = "#" & casti(0) & " " & casti(4)
                kvCount = kvCount + 1
            End If
        End If
    Loop
    Close #f
    kvIndex = -1
    KV_Kresli
    ShowStatus "Kontrola výkresu: " & kvCount & " míst k opravě. Další: vba run KV_Dalsi"
    If kvCount = 0 Then MsgBox "Ve výkresu nejsou žádné chyby k opravě.", vbInformation, "Kontrola výkresu"
End Sub

Private Sub KV_Kresli()
    Dim i As Long, el As EllipseElement, stred As Point3d, r As Double, barva As Long
    KV_Skryt
    If kvCount = 0 Then Exit Sub
    r = KV_Polomer()
    Set kvMarks = CreateTransientElementContainer1(Nothing, msdTransientFlagsOverlay, msdViewAllNormal, _
                                                   msdDrawingModeNormal)
    For i = 0 To kvCount - 1
        stred = Point3dFromXYZ(kvX(i), kvY(i), 0)
        Set el = CreateEllipseElement2(Nothing, stred, r, r, Matrix3dIdentity)
        barva = 3  ' červená = chyba
        If InStr(1, kvSev(i), "var", vbTextCompare) > 0 Then barva = 4  ' žlutá = varování
        el.Color = barva
        el.LineWeight = 3
        kvMarks.AppendCopyOfElement el
    Next i
End Sub

Private Function KV_Polomer() As Double
    ' kroužek asi 1/60 šířky pohledu, nejméně 0,3 m
    Dim ext As Point3d
    On Error Resume Next
    ext = ActiveDesignFile.Views(1).Extents
    On Error GoTo 0
    KV_Polomer = ext.X / 60
    If KV_Polomer < 0.3 Then KV_Polomer = 0.3
End Function

Public Sub KV_Skryt()
    If Not kvMarks Is Nothing Then
        kvMarks.Reset
        Set kvMarks = Nothing
    End If
End Sub

Private Sub KV_Ukaz(ByVal i As Long, ByVal okno As Boolean)
    Dim v As View, ext As Point3d
    If kvCount = 0 Then KV_Nacist
    If kvCount = 0 Then Exit Sub
    If i < 0 Then i = kvCount - 1
    If i >= kvCount Then i = 0
    kvIndex = i
    Set v = CommandState.LastView
    If v Is Nothing Then Set v = ActiveDesignFile.Views(1)
    ext = Point3dFromXYZ(12, 9, 0)  ' výřez asi 12 × 9 m kolem chyby
    v.Extents = ext
    v.Center = Point3dFromXYZ(kvX(i), kvY(i), 0)
    v.Redraw
    ShowStatus (i + 1) & "/" & kvCount & "  " & kvText(i)
    If okno Then MsgBox (i + 1) & " z " & kvCount & vbCrLf & vbCrLf & kvText(i), vbInformation, "Kontrola výkresu"
End Sub

Public Sub KV_Dalsi()
    KV_Ukaz kvIndex + 1, False
End Sub

Public Sub KV_Predchozi()
    KV_Ukaz kvIndex - 1, False
End Sub

Public Sub KV_Znovu()
    If kvIndex < 0 Then kvIndex = 0
    KV_Ukaz kvIndex, True
End Sub
