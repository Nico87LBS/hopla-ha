#!/usr/bin/env python3
"""Copie les icônes du catalogue Hopla utilisées par la carte (tâches,
récompenses, projets, routines, défis) depuis un dépôt hopla-web.

Usage : python3 scripts/sync-icons.py /chemin/vers/hopla-web
"""
import json
import shutil
import sys
from pathlib import Path

web = Path(sys.argv[1])
catalogue = json.loads((web / "internal/icons/catalogue.json").read_text(encoding="utf-8"))
target = Path(__file__).resolve().parents[1] / "custom_components/hopla/frontend/icons"
USED = {"task", "reward", "project", "routine"}

shutil.rmtree(target, ignore_errors=True)
target.mkdir(parents=True)
ids, emoji = [], {}
for icon in catalogue["icons"]:
    if icon.get("retired") or not (USED & set(icon.get("usages", [])) or icon["id"] == "trophy"):
        continue
    shutil.copyfile(web / "web/public/icones/hopla" / f"{icon['id']}.svg", target / f"{icon['id']}.svg")
    ids.append(icon["id"])
    for alias in icon.get("aliases", []):
        emoji[alias] = icon["id"]
    if icon.get("emoji"):
        emoji[icon["emoji"].replace("️", "").strip()] = icon["id"]
(target / "catalogue.json").write_text(
    json.dumps({"ids": ids, "emoji": emoji}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"{len(ids)} icônes copiées")
