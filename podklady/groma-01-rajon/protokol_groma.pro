IMPORT SOUØADNIC
================
Název vstupního souboru : T:\Studenti\Geodeti\Vèelák\geodezie\01_Groma\01_SezSour.txt 
Název výstupního souboru: T:\Studenti\Geodeti\Vèelák\geodezie\01_Groma\01_SezSour.crds


STATISTIKA:
-----------
Poèet položek vstupního souboru: 3                        
Poèet chybných položek         : 0                        
Poèet bodù s výškou / bez výšky: 3 / 0                    
Poèet bodù s kódem / bez kódu  : 0 / 3                    
Èíslo min / Èíslo max          : 4001 / 4003              
X min / X max                  : 1062156.480 / 1062174.590
Y min / Y max                  :  591346.000 /  591391.040
Z min / Z max                  :  527.600 /  529.870      

KONTROLA ÈÍSLOVÁNÍ BODÙ
=======================
Kontrolovaný soubor: T:\Studenti\Geodeti\Vèelák\geodezie\01_Groma\01_SezSour.crds

Poèet duplicitních položek: 0


IMPORT MÌØENÍ
=============
Název vstupního souboru : T:\Studenti\Geodeti\Vèelák\geodezie\01_Groma\01_zap.zap 
Název výstupního souboru: T:\Studenti\Geodeti\Vèelák\geodezie\01_Groma\01_zap.mess
Mìøítkový koeficient    : 0.9999021514 (-9.8 mm/100m)                             

Øádek   15: Stanovisko            4001, bod               2: Podezøelá výška signálu  :    0.000 m
Øádek   22: Stanovisko            4003, bod               4: Podezøelá výška signálu  :    0.000 m

STATISTIKA:
-----------
Poèet položek                 :     11               
Poèet stanovisek              :      2               
Poèet bodù se šikmou délkou   :      9               
Poèet bodù s vodorovnou délkou:      0               
Poèet bodù se zenitovým úhlem :      9               
Poèet bodù s pøevýšením       :      0               
Poèet bodù s kódem / bez kódu :      5 / 6           
Poèet mìøení v I/II poloze    :     11 / 0           
Èíslo min / Èíslo max         : 1 / 4003             
Z min / Z max                 :  96.3185 / 102.8550  
Délka min / Délka max         :     9.626 /    48.541
Signál min / Signál max       :    0.000 /    1.550  


POLÁRNÍ METODA
==============
Orientace osnovy na bodì 4001
-----------------------------
            Bod            Y            X  Kv.  Popis               
--------------------------------------------------------------------
           4001   591346.000  1062174.590                           
--------------------------------------------------------------------
Orientace:
----------
            Bod            Y            X  Kv.  Popis               
--------------------------------------------------------------------
           4002   591381.460  1062157.230                           
           4003   591391.040  1062156.480                           
--------------------------------------------------------------------
            Bod        Hz     Váha   Smìrník     V or.      Délka    V délky   m0 Red.   
-----------------------------------------------------------------------------------------
           4002    0.0000        0  128.9831   -0.0111     39.467      0.014             
           4003  395.3351        0  124.3382    0.0090     48.541      0.004             
-----------------------------------------------------------------------------------------
Orientaèní posun      [g]: 128.9942  (Smìrník nulového smìru)
m0 = SQRT([vv]/(n-1)) [g]:   0.0143  (Støední chyba jednoho orientaèního smìru)
SQRT([vv]/(n*(n-1)))  [g]:   0.0101  (Støední chyba orientaèního posunu)

Test polární metody:
--------------------
Oprava orientaèní délky na bod            4002 [m]: Skuteèná hodnota:     0.014, Mezní hodnota:     0.175
Oprava orientaèní délky na bod            4003 [m]: Skuteèná hodnota:     0.004, Mezní hodnota:     0.184
Oprava orientace                               [g]: Skuteèná hodnota:  -0.0111, Mezní hodnota:   0.0800  
Mezní odchylky stanovené pro práci v katastru nemovitostí byly dodrženy.

            Bod        Hz      Délka            Y            X  Popis               
------------------------------------------------------------------------------------
              1    7.6287     24.040   591366.171  1062161.511  roh budovy          

              2   10.8843     16.581   591359.433  1062164.870  roh budovy         

              3   47.1017     22.014   591354.073  1062154.110  roh budovy          




POLÁRNÍ METODA
==============
Orientace osnovy na bodì 4003
-----------------------------
            Bod            Y            X  Kv.  Popis               
--------------------------------------------------------------------
           4003   591391.040  1062156.480                           
--------------------------------------------------------------------
Orientace:
----------
            Bod            Y            X  Kv.  Popis               
--------------------------------------------------------------------
           4001   591346.000  1062174.590                           
           4002   591381.460  1062157.230                           
--------------------------------------------------------------------
            Bod        Hz     Váha   Smìrník     V or.      Délka    V délky   m0 Red.   
-----------------------------------------------------------------------------------------
           4001   81.3181        0  324.3382   -0.0100     48.536      0.009             
           4002   61.8931        0  304.9738    0.0506      9.626     -0.017             
-----------------------------------------------------------------------------------------
Orientaèní posun      [g]: 243.0302  (Smìrník nulového smìru)
m0 = SQRT([vv]/(n-1)) [g]:   0.0516  (Støední chyba jednoho orientaèního smìru)
SQRT([vv]/(n*(n-1)))  [g]:   0.0365  (Støední chyba orientaèního posunu)

Test polární metody:
--------------------
Oprava orientaèní délky na bod            4001 [m]: Skuteèná hodnota:     0.009, Mezní hodnota:     0.184
Oprava orientaèní délky na bod            4002 [m]: Skuteèná hodnota:    -0.017, Mezní hodnota:     0.137
Oprava orientace                               [g]: Skuteèná hodnota:   0.0506, Mezní hodnota:   0.0800  
Mezní odchylky stanovené pro práci v katastru nemovitostí byly dodrženy.


Pøekroèena tolerance: Mapování, Max. oprava orientace
-----------------------------------------------------
Stanovisko:            4003 Orientace:            4002 
Oprava orientace [g]:   0.0506
Mezní oprava     [g]:   0.0400

            Bod        Hz      Délka            Y            X  Popis               
------------------------------------------------------------------------------------
              4   45.0590     30.773   591360.804  1062150.756  roh budovy          
              2   73.4885     32.647   591359.486  1062164.856  roh budovy          

Kontrolní urèení bodu èíslo 2
-----------------------------
Bod                 Y            X  Kv.  Popis               
-------------------------------------------------------------
Starý      591359.433  1062164.870       roh budovy          
Nový       591359.486  1062164.856       roh budovy          
Rozdíl         -0.053        0.013       Polohová odchylka: 0.055, Stø. souø. chyba: 0.039
-------------------------------------------------------------
Uložený    591359.459  1062164.863       roh budovy          
             (Prùmìr)     (Prùmìr)                           


