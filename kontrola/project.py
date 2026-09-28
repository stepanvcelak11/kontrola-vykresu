"""Projekt: složka s výkresem, pravidly, nastavením, podklady a stavem chyb.

Struktura složky projektu::

    projekt.yaml          název, zdroj výkresu, poznámky k podkladům, stavy chyb
    pravidla.yaml         pravidla kontrol atributů
    nastaveni.yaml        nastavení kontrol (tolerance, závažnosti…)
    chyby.json            výsledek poslední kontroly
    vykres/               kopie kontrolovaného výkresu
    podklady/tabulky/     tabulky atributů od učitele (xlsx, csv, pdf)
    podklady/obrazky/     náčrty a fotky (jpg, png, pdf)
    podklady/vzor/        vzorový výkres

Celý projekt jde uložit do jednoho souboru ``*.kontrola`` (ZIP). Vše zůstává
na počítači uživatele, nic se nikam neodesílá.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .checks.base import Issue, Severity
from .config import Config
from .rules import RuleSet

KINDS = {
    "tabulky": "Tabulky atributů",
    "obrazky": "Náčrty a fotky",
    "vzor": "Vzorový výkres",
}
PROJECT_EXT = ".kontrola"


def default_projects_dir() -> Path:
    home = Path.home()
    for docs in (home / "Documents", home / "Dokumenty"):
        if docs.is_dir():
            return docs / "Kontrola výkresu"
    return home / "Kontrola výkresu"


def _safe_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return name or "projekt"


@dataclass
class Attachment:
    kind: str
    rel: str  # cesta relativně ke složce projektu
    path: Path
    size: int
    modified: dt.datetime

    @property
    def name(self) -> str:
        return self.path.name


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.meta: dict[str, Any] = {"nazev": self.root.name, "verze": 1}
        self.rules = RuleSet()
        self.config = Config()

    # ------------------------------------------------------------ vytvoření / otevření
    @classmethod
    def create(cls, root: str | Path, name: str | None = None) -> "Project":
        p = cls(Path(root))
        p.root.mkdir(parents=True, exist_ok=True)
        for k in KINDS:
            (p.root / "podklady" / k).mkdir(parents=True, exist_ok=True)
        (p.root / "vykres").mkdir(exist_ok=True)
        p.meta["nazev"] = name or p.root.name
        p.meta["vytvoreno"] = dt.datetime.now().isoformat(timespec="seconds")
        if (p.root / "projekt.yaml").exists():
            return cls.open(root)
        p.save()
        return p

    @classmethod
    def open(cls, root: str | Path) -> "Project":
        p = cls(Path(root))
        meta_file = p.root / "projekt.yaml"
        if not meta_file.exists():
            raise FileNotFoundError(f"Ve složce {root} není projekt (chybí projekt.yaml).")
        p.meta = yaml.safe_load(meta_file.read_text(encoding="utf-8")) or {}
        if (p.root / "pravidla.yaml").exists():
            p.rules = RuleSet.load(p.root / "pravidla.yaml")
        if (p.root / "nastaveni.yaml").exists():
            p.config = Config.load(p.root / "nastaveni.yaml")
        for k in KINDS:
            (p.root / "podklady" / k).mkdir(parents=True, exist_ok=True)
        return p

    @classmethod
    def new_in_default_location(cls, name: str) -> "Project":
        base = default_projects_dir()
        root = base / _safe_name(name)
        i = 2
        while (root / "projekt.yaml").exists():
            root = base / f"{_safe_name(name)} ({i})"
            i += 1
        return cls.create(root, name)

    @property
    def name(self) -> str:
        return self.meta.get("nazev") or self.root.name

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta["ulozeno"] = dt.datetime.now().isoformat(timespec="seconds")
        (self.root / "projekt.yaml").write_text(
            yaml.safe_dump(self.meta, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.rules.save(self.root / "pravidla.yaml",
                        header="Pravidla kontrol atributů – lze upravit v aplikaci (Zadání → Pravidla).")
        self.config.save(self.root / "nastaveni.yaml")

    # ------------------------------------------------------------ výkres
    @property
    def drawing_source(self) -> str | None:
        return self.meta.get("vykres_zdroj")

    @property
    def drawing_copy(self) -> Path | None:
        rel = self.meta.get("vykres")
        return (self.root / rel) if rel else None

    def drawing_path_for_loading(self) -> Path | None:
        """Přednostně původní soubor (uživatel ho mohl mezitím opravit), jinak kopie v projektu."""
        src = self.drawing_source
        if src and Path(src).is_file():
            return Path(src)
        cp = self.drawing_copy
        if cp and cp.is_file():
            return cp
        return None

    def set_drawing(self, src: str | Path) -> Path:
        src = Path(src)
        dest_dir = self.root / "vykres"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if src.resolve() != dest.resolve():
            for old in dest_dir.iterdir():
                if old.is_file():
                    old.unlink()
            shutil.copy2(src, dest)
            self.meta["vykres_zdroj"] = str(src.resolve())
        self.meta["vykres"] = dest.relative_to(self.root).as_posix()
        return dest

    def refresh_drawing_copy(self):
        src = self.drawing_source
        cp = self.drawing_copy
        if src and cp and Path(src).is_file() and Path(src).resolve() != cp.resolve():
            shutil.copy2(src, cp)

    # ------------------------------------------------------------ podklady
    def kind_dir(self, kind: str) -> Path:
        d = self.root / "podklady" / kind
        d.mkdir(parents=True, exist_ok=True)
        return d

    def add_attachment(self, kind: str, src: str | Path) -> str:
        src = Path(src)
        d = self.kind_dir(kind)
        dest = d / src.name
        i = 2
        while dest.exists() and dest.resolve() != src.resolve():
            dest = d / f"{src.stem} ({i}){src.suffix}"
            i += 1
        if dest.resolve() != src.resolve():
            shutil.copy2(src, dest)
        return dest.relative_to(self.root).as_posix()

    def replace_attachment(self, rel: str, src: str | Path) -> str:
        target = self.root / rel
        src = Path(src)
        if target.suffix.lower() == src.suffix.lower():
            shutil.copy2(src, target)
            return rel
        kind = Path(rel).parts[1]
        new_rel = self.add_attachment(kind, src)
        self._rename_meta(rel, new_rel)
        target.unlink(missing_ok=True)
        return new_rel

    def remove_attachment(self, rel: str):
        (self.root / rel).unlink(missing_ok=True)
        self.meta.get("obrazky", {}).pop(rel, None)
        self.meta.get("tabulky", {}).pop(rel, None)
        if self.meta.get("podklad", {}).get("obrazek") == rel:
            self.meta.pop("podklad", None)
        if self.meta.get("vzor") == rel:
            self.meta.pop("vzor", None)

    def remove_table(self, rel: str, with_rules: bool = True) -> int:
        """Odebere importovanou tabulku z projektu; volitelně i pravidla, která z ní vznikla."""
        removed = 0
        if with_rules:
            name = Path(rel).name
            keep = [r for r in self.rules.pravidla
                    if not (r.zdroj and (r.zdroj == name or r.zdroj.startswith(name + ",")))]
            removed = len(self.rules.pravidla) - len(keep)
            self.rules.pravidla[:] = keep
        self.remove_attachment(rel)
        return removed

    def _rename_meta(self, old: str, new: str):
        imgs = self.meta.get("obrazky", {})
        if old in imgs:
            imgs[new] = imgs.pop(old)
        if self.meta.get("podklad", {}).get("obrazek") == old:
            self.meta["podklad"]["obrazek"] = new
        if self.meta.get("vzor") == old:
            self.meta["vzor"] = new
        for r in self.rules.pravidla:
            if r.obrazek == old:
                r.obrazek = new

    def attachments(self, kind: str | None = None) -> list[Attachment]:
        out = []
        for k in ([kind] if kind else list(KINDS)):
            d = self.kind_dir(k)
            for f in sorted(d.iterdir(), key=lambda p: p.name.lower()):
                if f.is_file():
                    st = f.stat()
                    out.append(Attachment(k, f.relative_to(self.root).as_posix(), f, st.st_size,
                                          dt.datetime.fromtimestamp(st.st_mtime)))
        return out

    def image_note(self, rel: str) -> str:
        return self.meta.get("obrazky", {}).get(rel, {}).get("poznamka", "")

    def set_image_note(self, rel: str, note: str):
        self.meta.setdefault("obrazky", {}).setdefault(rel, {})["poznamka"] = note

    # ------------------------------------------------------------ chyby
    def issue_states(self) -> dict[str, dict]:
        return self.meta.get("stavy_chyb", {}) or {}

    def store_issues(self, issues: list[Issue]):
        states = {i.key: {"stav": i.state, "poznamka": i.note} for i in issues
                  if i.state != "nová" or i.note}
        old = self.issue_states()
        current = {i.key for i in issues}
        for k, v in old.items():  # zachovat „ignorovat“ i u chyb, které teď nejsou
            if k not in current and v.get("stav") == "ignorovat":
                states[k] = v
        self.meta["stavy_chyb"] = states
        data = [i.to_dict() | {"kontrola_nazev": i.check_name} for i in issues]
        (self.root / "chyby.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                               encoding="utf-8")

    def load_issues(self) -> list[Issue]:
        f = self.root / "chyby.json"
        if not f.exists():
            return []
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        out = []
        for d in data:
            out.append(Issue(check_id=d["kontrola"], check_name=d.get("typ") or d.get("kontrola_nazev", ""),
                             severity=Severity.parse(d["zavaznost"]), message=d["popis"],
                             x=float(d["x"]), y=float(d["y"]), layer=d.get("hladina", ""),
                             handles=[h for h in (d.get("handle") or "").split(",") if h],
                             number=int(d.get("cislo", 0)), state=d.get("stav", "nová"),
                             note=d.get("poznamka", "")))
        return out

    # ------------------------------------------------------------ ZIP (.kontrola)
    def export_zip(self, path: str | Path):
        self.refresh_drawing_copy()
        self.save()
        path = Path(path)
        if path.suffix.lower() != PROJECT_EXT:
            path = path.with_suffix(PROJECT_EXT)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            for f in self.root.rglob("*"):
                if f.is_file():
                    z.write(f, f.relative_to(self.root).as_posix())
        os.replace(tmp, path)
        return path

    @classmethod
    def import_zip(cls, path: str | Path, dest_parent: str | Path | None = None) -> "Project":
        path = Path(path)
        base = Path(dest_parent) if dest_parent else default_projects_dir()
        root = base / _safe_name(path.stem)
        i = 2
        while root.exists():
            root = base / f"{_safe_name(path.stem)} ({i})"
            i += 1
        root.mkdir(parents=True)
        with zipfile.ZipFile(path) as z:
            for member in z.namelist():
                target = (root / member).resolve()
                if not str(target).startswith(str(root.resolve())):
                    raise ValueError("Soubor projektu obsahuje neplatné cesty.")
            z.extractall(root)
        p = cls.open(root)
        # zdroj výkresu z jiného počítače neexistuje – použije se kopie v projektu
        src = p.drawing_source
        if src and not Path(src).is_file():
            p.meta.pop("vykres_zdroj", None)
        return p
