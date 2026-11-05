<?xml version='1.0' encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:math="urn:schemas-microsoft-com:JavaScript"
    xmlns:file="urn:schemas-microsoft-com:JavaScript"
    xmlns:str="urn:schemas-microsoft-com:JavaScript"
    xmlns:w="http://schemas.microsoft.com/office/word/2003/wordml"
    xmlns:v="urn:schemas-microsoft-com:vml"
    xmlns:w10="urn:schemas-microsoft-com:office:word"
    xmlns:sl="http://schemas.microsoft.com/schemaLibrary/2003/core"
    xmlns:aml="http://schemas.microsoft.com/aml/2001/core"
    xmlns:wx="http://schemas.microsoft.com/office/word/2003/auxHint"
    xmlns:o="urn:schemas-microsoft-com:office:office"
    xmlns:dt="uuid:C2F41010-65B3-11d1-A29F-00AA00C14882">

<!-- *** Prokol mereni GPS ****************************** -->
<!-- *** Soubor: *.txt ********************************** -->
<!-- *** Verze: 4.85 (30.12.2010) *********************** -->
<!-- *** Vystup: kalibraci GPS a pro ni pouzite body **** -->
<!-- *** Vystup: vytycovane body a pouzite bodu ********* -->
<!-- *** Pozn.: ke spravne fukncnosti jsou potreba ****** -->
<!-- ***        pomocne soubory "Protokol-Head.xdt" ***** -->
<!-- ***        a "Protokol-mereni-GPS.xdt" ! *********** -->

<!-- (c) 2005, Trimble Navigation Limited. All rights reserved.                                -->
<!-- (c) 2005-2006, GEOTRONICS Praha, s.r.o. Vsechna prava vyhrazena.                          -->
<!-- Trimble Navigation Limited a jeho Autorizovany distributor GEOTRONICS Praha, s.r.o.,      -->
<!-- poskytuje tento vstupni/vystupni predpis (XSL Style Sheet) "TAK JAK JE" se vsemi moznymi  -->
<!-- chybami a zrika se jakykoliv, i samozrejmych zaruk. Dale se pak zrika zaruky, ze tento    -->
<!-- produkt bude neomezene funkcni a bez chyb.
                                             -->
<!-- HLAVICKU PROTOKOLU MUZETE NASTAVIT V SOUBORU "Protokol-Head.xdt" -->

<!-- *************************************************** -->
<!-- *** Mnozstvi uvadenych hodnot u pouzitych bodu **** -->
<!-- *************************************************** -->
  <xsl:variable name="FS" select="'Rozsireny'"/>  <!-- Mozne volby: 'Zkraceny' / 'Rozsireny'  -->
  
<!-- *************************************************** -->
<!-- *** Zaokrouhleni na centimetry nebo milimetry ***** -->
<!-- *************************************************** -->
  <xsl:variable name="UnitsOut" select="'cm'"/>  <!-- Mozne volby: 'cm' / 'mm'  -->
  
<!-- *************************************************** -->
<!-- *** Ano = vypis pouze (ne vsech) pouzitych bodu *** -->
<!-- *************************************************** -->
  <xsl:variable name="UsedPt" select="'Ne'"/>  <!-- Mozne volby: 'Ano' / 'Ne' -->
  
<!-- *************************************************** -->
<!-- *** Ano = zprumerovat body *** -->
<!-- *************************************************** -->
<!--  <xsl:variable name="MeanPt" select="'Ano'"/>-->  <!-- Mozne volby: 'Ano' / 'Ne' -->

<!-- *************************************************** -->
<!-- *** Ano = vypis poznamek bodu v rozsirenem modu *** -->
<!-- *************************************************** -->
<!--  <xsl:variable name="PtNts" select="'Ano'"/>-->  <!-- Mozne volby: 'Ano' / 'Ne' -->

<!-- *************************************************** -->
<!-- *** Volba souradnicoveho systemu u pouzitych bodu * -->
<!-- *************************************************** -->
<!--  <xsl:variable name="WXS" select="'YXZ'"/>-->  <!-- Mozne volby: 'YXZ' / 'WGS' -->
  
<!-- *************************************************** -->
<!-- *** Implicitni odchylky pro kontrolu PDOP ********* -->
<!-- *************************************************** -->
  <xsl:variable name="PDOPTol" select="7"/>
  
<!-- *************************************************** -->
<!-- *** Implicitni odchylky pro vytycovaci protokol *** -->
<!-- *************************************************** -->
  <xsl:variable name="HzSOTol" select="0.03"/>
  <xsl:variable name="VtSOTol" select="0.05"/>
  <xsl:variable name="TolCheckType" select="'Oboji'"/>  <!-- Mozne volby: 'Horizontalni' / 'Vertikalni' / 'Oboji' -->

<!-- *************************************************** -->
<!-- *** Ano = Oznacovani NeFixovanych bodu ************ -->
<!-- *************************************************** -->
  <xsl:variable name="PtFix" select="'Ano'"/>  <!-- Mozne volby: 'Ano' / 'Ne' -->

<!-- *************************************************** -->
<!-- *** Volba poradi vypisu Vytycovane / Merene body ** -->
<!-- *************************************************** -->
<!--  <xsl:variable name="OutOrder" select="'SOPT'"/>-->  <!-- Mozne volby: 'SOPT' / 'MEPT' -->
  
  
<!-- *************************************************** -->
<!-- *** Volba vypisu bodu dle data ** -->
<!-- *************************************************** -->
<!--<xsl:variable name="DateFrom" select="'20150101'"/>  This is default value - subject to be changed -->
<!--<xsl:variable name="DateTo" select="'20251231'"/>  Datum DO -->
<!-- *** Jak pouzivat tento dokument ******************* -->
<!--
  Tento XSL soubor obsahuje varialbilni hodnoty editovatelne uzivatelem:
    - implicitni nastaveni obsahu protokolu
    - implicitni nastaveni vystupu souradnic
    - implicitni hodnotu pro kontrolu PDOP
    - implicitni hodnoty pro kontrolu odchylek vytycovanych bodu
    
 ******************************************************

  Pro spravnou funkci protokolu je nutne splnit nekolik podminek.
  
  Pro vytvareni ASCII vystupu v PC:
  1. cesta a nazev tohoto souboru:    \vas_adresar_s_xsl_stylesheety\Protokol mereni GPS.xsl
  2. cesta a nazev pomocneho souboru: \vas_adresar_s_xsl_stylesheety\Protokol-mereni-GPS.xdt
  3. cesta a nazev pomocneho souboru: \vas_adresar_s_xsl_stylesheety\Protokol-Head.xdt
     "vas_adresar_s_xsl_stylesheety" je vetsine pripadu "\Trimble ASCII XSL\"

  Pro vytvareni ASCII vystupu v Trimble ACU nebo TCU:
  1. cesta a nazev tohoto souboru:    \Trimble Data\Protokol mereni GPS.xsl
  2. cesta a nazev pomocneho souboru: \Trimble Data\Protokol-mereni-GPS.xdt
  3. cesta a nazev pomocneho souboru: \Trimble Data\Protokol-Head.xdt
  4. hodnoty uvede mezi apostrofy ' ' musi byt bez ceske diakritiky
  
  Pro vytvareni ASCII vystupu v Trimble TSC2:
  1. cesta a nazev tohoto souboru:    \Built-in Storage\Trimble Data\Protokol mereni GPS.xsl
  2. cesta a nazev pomocneho souboru: \Temp\Protokol-mereni-GPS.xdt
  3. cesta a nazev pomocneho souboru: \Temp\Protokol-Head.xdt
  4. hodnoty uvede mezi apostrofy ' ' musi byt bez ceske diakritiky

  
  K editaci tohoto souboru je mozne pouzit standardni editor ASCII.
  Doporucujeme program Notepad (Poznamkovy blok), ktery je soucasti OS MS-Windows.
  POZOR: pokud editujete tento soubor, je nutne pri jeho ukladani zvolit
         "Soubor" - "Ulozit jako" a ve volbe "Kodovani" vybrat hodnotu "UTF-8".
-->

<!-- *************************************************** -->
<!-- *** !!! Nize uvedene hodnoty needitujte !!! ******* -->
<!-- *************************************************** -->
  <xsl:output method="text" encoding="ISO-8859-2"/>

  <xsl:include href="Kompletni-protokol-mereni-GPS-2021.xdt"/>
  <xsl:variable name="fileExt" select="'txt'"/>

  <xsl:variable name="userField1" select="'FS|Vypis pouzitych bodu|stringMenu|2|Zkraceny|Rozsireny'"/>
  <xsl:variable name="userField2" select="'UnitsOut|Zaokrouhleni|stringMenu|2|cm|mm'"/>
  <xsl:variable name="userField3" select="'UsedPt|Pouze GPS merene body|stringMenu|2|Ano|Ne'"/>
  <!--<xsl:variable name="userField4" select="'MeanPt|Prumerovane body|stringMenu|2|Ano|Ne'"/>
   <xsl:variable name="userField5" select="'PtNts|Vypis poznamek bodu|stringMenu|2|Ano|Ne'"/>
  <xsl:variable name="userField6" select="'WXS|System souradnic bodu|stringMenu|2|YXZ|WGS'"/>
  <xsl:variable name="userField7" select="'PDOPTol|Kontrola PDOP|double|0.0|99.0'"/>
  <xsl:variable name="userField8" select="'TolCheckType|Vytycovaci tolerance|stringMenu|3|Horizontalni|Vertikalni|Oboji'"/>
  <xsl:variable name="userField9" select="'HzSOTol|Vytycovaci tolerance horizontalni|double|0.0|1.0'"/>
  <xsl:variable name="userField10" select="'VtSOTol|Vytycovaci tolerance vertikalni|double|0.0|2.0'"/>-->

  <xsl:variable name="NoFixMark" select="'! NoFix ! '"/>
  
</xsl:stylesheet>
