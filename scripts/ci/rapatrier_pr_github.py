#!/usr/bin/env python3
"""Rapatrie les pull requests GitHub ouvertes dans GitLab.

Lancé par un pipeline planifié de GitLab. Pour chaque PR ouverte sur le
dépôt GitHub miroir, la branche de la PR est poussée sur GitLab sous le nom
github/pr-N, puis une merge request est ouverte (ou mise à jour) vers la
branche cible. La CI GitLab tourne dessus comme sur toute merge request.

Variables (à définir dans les variables CI/CD du groupe ou du projet) :
  GITHUB_DEPOT      dépôt GitHub, par exemple Nico87LBS/hopla
  GITHUB_TOKEN_PR   jeton GitHub en lecture (Contents et Pull requests)
  GITLAB_TOKEN_PR   jeton d'accès GitLab (api, write_repository)
Fournies par GitLab : CI_SERVER_URL, CI_API_V4_URL, CI_PROJECT_ID, CI_PROJECT_PATH.
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

PREFIXE = "github/pr-"


def env(nom):
    valeur = os.environ.get(nom, "").strip()
    if not valeur:
        sys.exit(f"Variable {nom} manquante.")
    return valeur


DEPOT = env("GITHUB_DEPOT")
JETON_GH = env("GITHUB_TOKEN_PR")
JETON_GL = env("GITLAB_TOKEN_PR")
API_GL = env("CI_API_V4_URL")
PROJET = env("CI_PROJECT_ID")
URL_GL = env("CI_SERVER_URL").rstrip("/") + "/" + env("CI_PROJECT_PATH") + ".git"
URL_GH = f"https://github.com/{DEPOT}.git"


def appel(url, jeton_entete, methode="GET", donnees=None):
    corps = json.dumps(donnees).encode() if donnees is not None else None
    req = urllib.request.Request(url, data=corps, method=methode)
    for cle, valeur in jeton_entete.items():
        req.add_header(cle, valeur)
    if corps is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as rep:
        texte = rep.read().decode()
        return json.loads(texte) if texte else None


def github(chemin):
    return appel(f"https://api.github.com/{chemin}", {
        "Authorization": f"Bearer {JETON_GH}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "hopla-rapatriement-pr",
    })


def gitlab(chemin, methode="GET", donnees=None):
    return appel(f"{API_GL}/projects/{PROJET}/{chemin}", {"PRIVATE-TOKEN": JETON_GL}, methode, donnees)


def git(*args, jeton=None, utilisateur="x-access-token"):
    cmd = ["git"]
    if jeton:
        auth = base64.b64encode(f"{utilisateur}:{jeton}".encode()).decode()
        cmd += ["-c", f"http.extraHeader=Authorization: Basic {auth}"]
    cmd += list(args)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        # Les jetons ne sont jamais dans la sortie de git : ils passent par l'en-tête.
        raise RuntimeError(f"git {args[0]} a échoué : {res.stderr.strip()[-500:]}")
    return res.stdout.strip()


def sha_gitlab(branche):
    try:
        return gitlab(f"repository/branches/{urllib.parse.quote(branche, safe='')}")["commit"]["id"]
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise


def description(pr):
    corps = (pr.get("body") or "").strip()
    entete = (
        f"Importée automatiquement de la PR GitHub [#{pr['number']}]({pr['html_url']}) "
        f"de @{pr['user']['login']} (branche `{pr['head']['ref']}`).\n\n"
        "Les nouveaux commits poussés sur la PR GitHub arrivent ici au prochain passage.\n\n---\n\n"
    )
    return entete + (corps or "_Pas de description._")


def traiter(pr):
    n = pr["number"]
    branche = f"{PREFIXE}{n}"
    tete = pr["head"]["sha"]
    cible = pr["base"]["ref"]
    existantes = gitlab(f"merge_requests?source_branch={urllib.parse.quote(branche, safe='')}&state=all&per_page=100")
    ouverte = next((m for m in existantes if m["state"] == "opened"), None)
    if not ouverte and any(m["sha"] == tete and m["state"] in ("merged", "closed") for m in existantes):
        print(f"PR #{n} : déjà fusionnée ou fermée dans GitLab à ce commit, rien à faire.")
        return
    if sha_gitlab(branche) == tete and ouverte:
        print(f"PR #{n} : à jour (!{ouverte['iid']}).")
        return
    git("fetch", "--quiet", URL_GH, f"+refs/pull/{n}/head:refs/rapatriement/pr-{n}", jeton=JETON_GH)
    # Seules les branches github/pr-* sont réécrites : elles appartiennent au rapatriement.
    git("push", "--quiet", "--force", URL_GL, f"refs/rapatriement/pr-{n}:refs/heads/{branche}",
        jeton=JETON_GL, utilisateur="oauth2")
    if ouverte:
        print(f"PR #{n} : nouveaux commits poussés sur !{ouverte['iid']}.")
        return
    mr = gitlab("merge_requests", "POST", {
        "source_branch": branche,
        "target_branch": cible,
        "title": pr["title"],
        "description": description(pr),
        "labels": "github",
        "remove_source_branch": True,
    })
    # La branche existait avant la MR : on lance son premier pipeline à la main.
    gitlab(f"merge_requests/{mr['iid']}/pipelines", "POST")
    print(f"PR #{n} : merge request !{mr['iid']} ouverte ({mr['web_url']}).")


def main():
    git("init", "--quiet", "/tmp/rapatriement")
    os.chdir("/tmp/rapatriement")
    prs = github(f"repos/{DEPOT}/pulls?state=open&per_page=100")
    print(f"{len(prs)} PR ouverte(s) sur {DEPOT}.")
    erreurs = 0
    for pr in prs:
        try:
            traiter(pr)
        except Exception as err:  # une PR en échec ne bloque pas les autres
            erreurs += 1
            print(f"PR #{pr['number']} : échec : {err}")
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
