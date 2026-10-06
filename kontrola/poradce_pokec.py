"""Poradce – obecné a „lidské“ otázky: pozdravy, díky, co teď, kdo jsi… a vtipné odpovědi na nesmysly.

Bez Qt (použije ho okno Poradce i web). ``pokec(text)`` vrací (nadpis, html) nebo None, když jde
o odbornou otázku, na kterou se má hledat v návodech.
"""

from __future__ import annotations

import datetime as _dt
import random
import re
import unicodedata


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


CO_TED = ("Co teď",
          "Postup, který se vyplatí: <br>1) <b>Výpočty</b> – načtěte zápisník a spočítejte seznam souřadnic "
          "(porovnejte ho s učitelovým: Výpočty → Porovnat seznamy). <br>2) <b>CAD</b> – Body ze seznamu, kresba "
          "z kódů, doplňte kresbu podle náčrtu. <br>3) Uložte DXF a stiskněte <b>Zkontrolovat</b> (F5). "
          "<br>4) Opravujte chyby od nejzávažnějších (F8 = další chyba). <br>5) <b>Připraveno k odevzdání?</b> "
          "– a pak už jen odevzdat a jít na kafe. ☕")

# (vzor v ASCII bez diakritiky, nadpis, odpovědi – vybere se náhodně jedna)
_VZORY: list[tuple[str, str, tuple[str, ...]]] = [
    (r"^(ahoj|cau|cus|nazdar|zdravim|dobr[yeyy] (den|rano|vecer)|hello|hi|cauky|zdar)\b", "Ahoj",
     ("Ahoj! 👋 Ptejte se na cokoli kolem výkresu, Gromy nebo CAD – třeba <i>co teď?</i>",
      "Zdravím! Výkres je připravený ke kontrole, já taky. Co potřebujete?",
      "Nazdar! Jsem tu, abych hlídal vrstvy, barvy a nedotahy – a vy nemuseli. 😉")),
    (r"\b(dik|diky|dekuji|dekuju|dekujeme|thanks|thx|super|paradni|skvel|bomba)\b", "Rádo se stalo",
     ("Rádo se stalo! Kdyby něco, jsem tady. 🙂",
      "Není zač. Ať vám výkres projde napoprvé!",
      "Díky za díky. Uzly by poděkovaly taky, kdyby uměly.")),
    (r"\b(co (ted|dal|mam delat|delat|ted delat)|nevim co dal|kde zacit|jak zacit|s cim zacit|co mam)\b",
     CO_TED[0], (CO_TED[1],)),
    (r"\b(kdo jsi|co jsi|jak se jmenujes|kdo te (udelal|naprogramoval|vytvoril)|jsi (robot|ai|umela))\b",
     "Kdo jsem",
     ("Jsem Poradce aplikace Kontrola výkresu – znám návody, chyby, Směrnici z vašeho projektu a pár vtipů. "
      "Funguju i bez internetu.",
      "Jsem malý pomocník uvnitř aplikace. Neumím uvařit kafe, ale umím najít nedotaženou linii.")),
    (r"\b(co umis|co dokazes|co vsechno umis|s cim (mi )?pomuzes|napoveda|help|pomoc)\b", "Co umím",
     ("Poradím s: <b>kontrolou výkresu</b> (co znamená chyba a jak ji opravit), <b>Výpočty</b> (zápisník, "
      "polární metoda, porovnání s učitelem), <b>CAD</b> (kreslení, úchyty, body ze seznamu), <b>Směrnicí</b> "
      "(jaká barva / vrstva / styl patří prvku). Zkuste třeba <i>jaká barva má plot</i>, <i>jak opravit tuhle "
      "chybu</i>, <i>kolik mi zbývá</i>.",)),
    (r"\b(jak se mas|jak je|jak se vede|jsi v pohode)\b", "Mám se dobře",
     ("Výborně – zatím mě nikdo nenutil kontrolovat výkres v měřítku 1:1 000 000. A vy?",
      "Skvěle, právě jsem si spočítal pár rajonů pro radost.",
      "Mám se jako dobře uzavřený polygon – bez mezer.")),
    (r"\b(vtip|zasmat|pobav|neco vtipneho|joke)\b", "Vtip",
     ("Víte, proč geodet nikdy nezabloudí? Protože má vždycky aspoň dva dané body. 📍",
      "Potkají se dva body. První: „Nějak ses mi přiblížil.“ Druhý: „To jen MGEO hlásí blízké prvky.“",
      "Jak poznáte zkušeného geodeta? Na rande přinese výtyčku, „kdyby bylo potřeba zaměřit vztah“.",
      "Proč linie nechodí na večírky? Bojí se, že se nedotáhne. 🥲",
      "Učitel: „Proč máte ve výkresu vrstvu 58?“ Student: „Protože 57 už byla obsazená.“")),
    (r"\b(pocasi|bude prset|prsi|snezi|teplo|zima venku)\b", "Počasí",
     ("Počasí neměřím, ale pro tachymetrii doporučuju zataženo, bezvětří a teplotu, při které nemrznou prsty "
      "na ovladači stanice. 🌤️",
      "Podle mých údajů je v modelovém prostoru vždycky jasno. Za okno neručím.")),
    (r"\b(kolik je hodin|kolik je cas|jaky je cas|kolikateho je|jake je datum)\b", "Čas", ("{cas}",)),
    (r"\b(smysl zivota|odpoved na vse)\b|^42$", "Smysl života",
     ("42. A výkres bez topologických chyb. 🙂",)),
    (r"\b(miluju te|mas me rad|libis se mi|vezmes si me|chodis s)\b", "Ehm…",
     ("Já mám rád hlavně správně uzavřené polygony. Ale díky, potěšilo mě to. 💙",
      "To je od vás milé. Můj vztah je ale vážný – s tabulkou barev color.tbl.")),
    (r"\b(dej mi (jednicku|jednicka|znamku|1)|jakou dostanu znamku|projde (mi )?to|uzna to ucitel)\b",
     "Známka",
     ("Známky dává učitel, já dávám jen skóre připravenosti. 😉 Opravte chyby a jednička je blíž.",
      "Kdybych mohl, dal bych vám jedničku hned. Bohužel mám jen tlačítko <b>Zkontrolovat</b>.")),
    (r"\b(nudim se|nebavi me|to je nuda|uz nemuzu|mam toho dost|unaven)\b", "Pauza",
     ("Dejte si pět minut pauzu, protáhněte se – výkres počká. Pak stačí <i>co teď?</i> a jedeme dál. ☕",
      "Chápu. Zkuste opravit jen tři chyby a pak odměna. Funguje to i na geodety.")),
    (r"\b(jsi (blbej|blby|hloupy|k nicemu|debil|pitomy)|ty jsi (blbej|hloupy)|nefungujes|jsi na nic)\b",
     "Omlouvám se",
     ("Mrzí mě to – zkuste mi otázku napsat jinak, nebo mrkněte do <b>Nápověda → Rychlé tipy</b>. "
      "A když něco opravdu nefunguje, <b>Nápověda → Nahlásit problém</b>.",
      "Au. 🥲 Ale nevzdávám se – napište, s čím přesně potřebujete pomoct.")),
    (r"\b(umis varit|uvar|pizza|jidlo|mam hlad|obed|kafe|kava|pivo)\b", "Jídlo",
     ("Vařit neumím, ale umím spočítat výměru talíře. 🍕 Na oběd doporučuju pauzu od výkresu.",
      "Kafe neuvařím, ale zkontroluju, jestli máte v hrnku uzavřený polygon. ☕")),
    (r"\b(fotbal|hokej|sport|film|serial|hra|hry|minecraft)\b", "Mimo obor",
     ("Na tohle jsem úplně vedle – znám jen čáry, body a texty. Ale v Minecraftu by se mi líbil terén "
      "z vrstevnic. ⛏️",)),
]


def pokec(text: str, ted: _dt.datetime | None = None) -> tuple[str, str] | None:
    """Odpověď na obecnou otázku nebo nesmysl, jinak None."""
    t = _ascii(text).strip()
    t = re.sub(r"[?!.,;:]+", " ", t).strip()
    if not t:
        return None
    for vzor, nadpis, odpovedi in _VZORY:
        if re.search(vzor, t):
            o = random.choice(odpovedi)
            if "{cas}" in o:
                ted = ted or _dt.datetime.now()
                o = f"Je {ted:%H:%M}, {ted.day}. {ted.month}. {ted.year}. Ideální čas na opravu jedné chyby. ⏰"
            return nadpis, o
    return None


def nevim() -> str:
    return random.choice((
        "Na tohle odpověď v návodech nemám. Zkuste jiná slova, nebo <b>Nápověda → Rychlé tipy</b> a <b>Co znamenají "
        "chyby</b>. Pomůže i otázka <i>co umíš?</i>",
        "Hmm, tohle neznám. Jsem odborník na výkresy, ne na všechno. 🙂 Zkuste to napsat jinak – třeba <i>jak "
        "opravit nedotah</i> nebo <i>co teď?</i>",
    ))
