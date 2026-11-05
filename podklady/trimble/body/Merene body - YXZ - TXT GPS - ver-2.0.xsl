<?xml version='1.0' encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform" >

<!-- *** Export souradnic YXZ (XYZ) ve formatu TXT ****** -->
<!-- *** Soubor: *.txt ********************************** -->
<!-- *** Verze: 1.62 (02.01.2012) ************************ -->
<!-- *** Upraveno datum na 2011 a 20121231**************** -->
<!-- *** Verze: 1.61 (04.01.2011) ************************ -->
<!-- *** Upraveno datum na 2010 a 20111231**************** -->
<!-- *** Verze: 1.5 (13.11.2006) ************************ -->
<!-- *** Format YXZ: "12  6.2  7.2  4.2  20" ************ -->
<!-- *** Format XYZ: "12  7.2  6.2  4.2  20" ************ -->
<!-- *** Format YXZ: "12  6.3  7.3  4.3  20" ************ -->
<!-- *** Format XYZ: "12  7.3  6.3  4.3  20" ************ -->

<!-- (c) 2005, Trimble Navigation Limited. All rights reserved.                                -->
<!-- (c) 2005-2006, GEOTRONICS Praha, s.r.o. Vsechna prava vyhrazena.                          -->
<!-- Trimble Navigation Limited a jeho Autorizovany distributor GEOTRONICS Praha, s.r.o.,      -->
<!-- poskytuje tento vstupni/vystupni predpis (XSL Style Sheet) "TAK JAK JE" se vsemi moznymi  -->
<!-- chybami a zrika se jakykoliv, i samozrejmych zaruk. Dale se pak zrika zaruky, ze tento    -->
<!-- produkt bude neomezene funkcni a bez chyb. -->



<!--
- ver.: 2.00 (17.06.2025), LM, Uprava exportu bodů měřených horizontálním odsazením jako měřené body
-->




<!-- *************************************************** -->
<!-- *** Zaokrouhleni na centimetry nebo milimetry ***** -->
<!-- *************************************************** -->
  <xsl:variable name="UnitsOut" select="'mm'"/>  <!-- Mozne volby: 'cm' / 'mm'  -->

<!-- *************************************************** -->
<!-- *** Ano = vypis pouze merenych bodu *************** -->
<!-- *************************************************** -->
  <xsl:variable name="UsedPt" select="'Ne'"/>  <!-- Mozne volby: 'Ano' / 'Ne' -->

<!--
  K editaci tohoto souboru je mozne pouzit standardni editor ASCII.
  Doporucujeme program Notepad (Poznamkovy blok), ktery je soucasti OS MS-Windows.
  POZOR: pokud editujete tento soubor, je nutne pri jeho ukladani zvolit
         "Soubor" - "Ulozit jako" a ve volbe "Kodovani" vybrat hodnotu "UTF-8".
-->

<!-- *************************************************** -->
<!-- *** !!! Nize uvedene hodnoty needitujte !!! ******* -->
<!-- *************************************************** -->
<xsl:output method="text" omit-xml-declaration="yes" encoding="ISO-8859-2"/>
<xsl:variable name="fileExt" select="'txt'"/>

<xsl:variable name="userField1" select="'UsedPt|Pouze merene body|stringMenu|2|Ano|Ne'"/>
<xsl:variable name="userField2" select="'UnitsOut|Zaokrouhleni|stringMenu|2|cm|mm'"/>
<!--<xsl:variable name="userField3" select="'DateFrom|Pouzit body od RRRRMMDD|string'"/>
<xsl:variable name="userField4" select="'DateTo|Pouzit body do RRRRMMDD|string'"/>-->

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="string('.')"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="string(',')"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN=" "
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="string('#0')"/>
<xsl:variable name="DecPl1" select="string(concat('#0', $DecPt, '0'))"/>
<xsl:variable name="DecPl2" select="string(concat('#0', $DecPt, '00'))"/>
<xsl:variable name="DecPl3" select="string(concat('#0', $DecPt, '000'))"/>
<xsl:variable name="DecPl4" select="string(concat('#0', $DecPt, '0000'))"/>
<xsl:variable name="DecPl5" select="string(concat('#0', $DecPt, '00000'))"/>
<xsl:variable name="DecPl6" select="string(concat('#0', $DecPt, '000000'))"/>
<xsl:variable name="DecPl8" select="string(concat('#0', $DecPt, '00000000'))"/>


<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />

<!-- **************************************************************** -->
<!-- *** Set global variables for FieldBook data searching ********** -->
<!-- **************************************************************** -->
<xsl:key name="obsID-search" match="/JOBFile/FieldBook/PointRecord" use="@ID"/>

<!-- **************************************************************** -->
<!-- *** Nastaveni Variable pro vypis pouze merenych bodu *********** -->
<!-- **************************************************************** -->
<!-- PRESUNUTO JAKO POMOCNY SOUBOR -->
<!--
  <xsl:variable name="UsedPt" select="'Ano'"/>
  <xsl:variable name="UnitsOut" select="'cm'"/>

  <xsl:variable name="userField1" select="'UsedPt|Pouze merene body|stringMenu|2|Ano|Ne'"/>
  <xsl:variable name="userField2" select="'UnitsOut|Zaokrohleni|stringMenu|2|cm|mm'"/>
-->

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">
      <xsl:value-of select="'True'"/>
    </xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">
      <xsl:value-of select="'True'"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="'False'"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for coordinate and distance values -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">
      1.0
    </xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">
      3.280839895
    </xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">
      3.2808333333357
    </xsl:when>
    <xsl:otherwise>
      1.0
    </xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >
  <xsl:apply-templates select="JOBFile/Reductions" />
</xsl:template>

<!-- **************************************************************** -->
<!-- ***************** Reductions Node Processing ******************* -->
<!-- **************************************************************** -->
<xsl:template match="Reductions">
  <xsl:apply-templates select="Point"/>
</xsl:template>

<!-- **************************************************************** -->
<!-- ****************** Reductions Point Output ********************* -->
<!-- **************************************************************** -->
<xsl:template match="Point">
  <xsl:call-template name="GridPoint"/>
</xsl:template>

<!-- **************************************************************** -->
<!-- **************** Grid Point Details Output ********************* -->
<!-- **************************************************************** -->
<xsl:template name="GridPoint">

<!-- *** Test vypisu: Pouze pouzite body *** -->
  <xsl:variable name="PtPDOPYorN">
    <xsl:for-each select="key('obsID-search', ID)">
      <xsl:value-of select="QualityControl1/PDOP"/>
    </xsl:for-each>
  </xsl:variable>

  <!-- *** Test vypisu: Pouze pouzite body *** -->
  <xsl:variable name="HorizontalneOdsazeneBody">
    <xsl:for-each select="key('obsID-search', ID)">
      <xsl:value-of select="Method"/>
    </xsl:for-each>
  </xsl:variable>
 
  
  <xsl:if test="not(contains(Name,'HTO'))">
	  <xsl:choose>
		<xsl:when test="$UsedPt = 'Ano'">
		<xsl:if test="($PtPDOPYorN &gt;= 0) or ($HorizontalneOdsazeneBody='BearingDistancePointIntersection')">
		  <xsl:call-template name="GridPointOutput"/>
		</xsl:if>
		</xsl:when>
		<xsl:otherwise>
		  <xsl:call-template name="GridPointOutput"/>
		</xsl:otherwise>
	  </xsl:choose>
	</xsl:if>
  
</xsl:template>

<xsl:template name="GridPointOutput">

  <xsl:variable name="PointDate">
   <xsl:for-each select="key('obsID-search', ID)">
      <xsl:value-of select="concat(substring(@TimeStamp, 1, 4),
                                   substring(@TimeStamp, 6, 2),
                                   substring(@TimeStamp, 9, 2))"/>
    </xsl:for-each>
  </xsl:variable>


  <xsl:variable name="PtName">
      <xsl:call-template name="PadLeft">
        <xsl:with-param name="StringWidth" select="17"/>
        <xsl:with-param name="TheString">
          <xsl:value-of select="Name"/>
        </xsl:with-param>
      </xsl:call-template>
  </xsl:variable>

  <xsl:variable name="PtCode">
      <xsl:value-of select="Code"/>
  </xsl:variable>

  <xsl:choose>
    <xsl:when test="$UnitsOut = 'cm'">

    <xsl:variable name="GridN">
      <xsl:call-template name="PadLeft">
        <xsl:with-param name="StringWidth" select="12"/>
        <xsl:with-param name="TheString">
          <xsl:value-of select="format-number(Grid/North * $DistConvFactor, $DecPl2, 'Standard')"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>

    <xsl:variable name="GridE">
      <xsl:call-template name="PadLeft">
        <xsl:with-param name="StringWidth" select="11"/>
        <xsl:with-param name="TheString">
          <xsl:value-of select="format-number(Grid/East * $DistConvFactor, $DecPl2, 'Standard')"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>

    <xsl:variable name="GridH">
      <xsl:call-template name="PadLeft">
        <xsl:with-param name="StringWidth" select="9"/>
        <xsl:with-param name="TheString">
          <xsl:value-of select="format-number(Grid/Elevation * $DistConvFactor, $DecPl2, 'Standard')"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>

  <xsl:choose>
    <xsl:when test="$NECoords = 'True'">
      <xsl:value-of select="concat($PtName, $GridN, $GridE, $GridH, ' ', $PtCode)"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="concat($PtName, $GridE, $GridN, $GridH, ' ', $PtCode)"/>
    </xsl:otherwise>
  </xsl:choose>

    </xsl:when>
    <xsl:otherwise>

    <xsl:variable name="GridN">
      <xsl:call-template name="PadLeft">
        <xsl:with-param name="StringWidth" select="13"/>
        <xsl:with-param name="TheString">
          <xsl:value-of select="format-number(Grid/North * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>

    <xsl:variable name="GridE">
      <xsl:call-template name="PadLeft">
        <xsl:with-param name="StringWidth" select="12"/>
        <xsl:with-param name="TheString">
          <xsl:value-of select="format-number(Grid/East * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>

    <xsl:variable name="GridH">
      <xsl:call-template name="PadLeft">
        <xsl:with-param name="StringWidth" select="10"/>
        <xsl:with-param name="TheString">
          <xsl:value-of select="format-number(Grid/Elevation * $DistConvFactor, $DecPl3, 'Standard')"/>
        </xsl:with-param>
      </xsl:call-template>
    </xsl:variable>

    <xsl:choose>
    <xsl:when test="$NECoords = 'True'">
      <xsl:value-of select="concat($PtName, $GridN, $GridE, $GridH,' ', $PtCode)"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:value-of select="concat($PtName, $GridE, $GridN, $GridH, ' ', $PtCode)"/>
    </xsl:otherwise>
  </xsl:choose>

    </xsl:otherwise>
  </xsl:choose>
  
  <xsl:call-template name="NewLine"/>
</xsl:template>

<!-- **************************************************************** -->
<!-- ********************** New Line Output ************************* -->
<!-- **************************************************************** -->
<xsl:template name="NewLine">
  <xsl:text>&#xa;</xsl:text>
</xsl:template>

<!-- **************************************************************** -->
<!-- *********** Pad a string to the left with spaces *************** -->
<!-- **************************************************************** -->
<xsl:template name="PadLeft">
  <xsl:param name="StringWidth"/>
  <xsl:param name="TheString"/>
  <xsl:choose>
    <xsl:when test="$StringWidth = '0'">
      <xsl:value-of select="normalize-space($TheString)"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:variable name="PaddedStr" select="concat('                                       ', $TheString)"/>
      <xsl:value-of select="substring($PaddedStr, string-length($PaddedStr) - $StringWidth + 1)"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>

<!-- **************************************************************** -->
<!-- *********** Pad a string to the right with spaces ************** -->
<!-- **************************************************************** -->
<xsl:template name="PadRight">
  <xsl:param name="StringWidth"/>
  <xsl:param name="TheString"/>
  <xsl:choose>
    <xsl:when test="$StringWidth = '0'">
      <xsl:value-of select="normalize-space($TheString)"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:variable name="PaddedStr" select="concat($TheString, '                                       ')"/>
      <xsl:value-of select="substring($PaddedStr, 1, $StringWidth)"/>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>

</xsl:stylesheet>
