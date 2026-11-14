#!/usr/bin/env python3
"""Rapatrie les pull requests GitHub ouvertes dans GitLab.

Lancé par un pipeline planifié de GitLab. Pour chaque PR ouverte sur le
dépôt GitHub miroir, la branche de la PR est poussée sur GitLab sous le nom
github/pr-N, puis une merge request est ouverte (ou mise à jour) vers la
branche cible. La CI GitLab tourne dessus comme sur toute merge request.

Le résultat du pipeline GitLab de chaque merge request est ensuite écrit en
commentaire sur la PR GitHub (un seul commentaire, mis à jour), avec la fin
du journal des jobs en échec, pour que l'auteur de la PR puisse corriger.

Variables (à définir dans les variables CI/CD du groupe ou du projet) :
  GITHUB_DEPOT      dépôt GitHub, par exemple Nico87LBS/hopla
  GITHUB_TOKEN_PR   jeton GitHub : Contents en lecture, Pull requests en écriture
  GITLAB_TOKEN_PR   jeton d'accès GitLab (api, write_repository)
Fournies par GitLab : CI_SERVER_URL, CI_API_V4_URL, CI_PROJECT_ID, CI_PROJECT_PATH.
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
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


class ErreurAPI(Exception):
    """Erreur HTTP d'une API, avec la réponse du serveur pour le journal."""

    def __init__(self, methode, url, code, reponse):
        self.code = code
        chemin = url.split("?")[0].split("/projects/")[-1].split("api.github.com/")[-1]
        super().__init__(f"{methode} {chemin} : HTTP {code} {reponse[:300]}")


def appel(url, jeton_entete, methode="GET", donnees=None):
    corps = json.dumps(donnees).encode() if donnees is not None else None
    req = urllib.request.Request(url, data=corps, method=methode)
    for cle, valeur in jeton_entete.items():
        req.add_header(cle, valeur)
    if corps is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as rep:
            texte = rep.read().decode()
            return json.loads(texte) if texte else None
    except urllib.error.HTTPError as err:
        # Le message du serveur (jamais le jeton) explique l'échec dans le journal.
        raise ErreurAPI(methode, url, err.code, err.read().decode(errors="replace").strip()) from None


def github(chemin, methode="GET", donnees=None):
    return appel(f"https://api.github.com/{chemin}", {
        "Authorization": f"Bearer {JETON_GH}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "hopla-rapatriement-pr",
    }, methode, donnees)


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
    except ErreurAPI as err:
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


MARQUE = "<!-- rapatriement-gitlab -->"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\r")


def journal(job_id, lignes=40):
    req = urllib.request.Request(f"{API_GL}/projects/{PROJET}/jobs/{job_id}/trace")
    req.add_header("PRIVATE-TOKEN", JETON_GL)
    with urllib.request.urlopen(req, timeout=30) as rep:
        texte = ANSI.sub("", rep.read().decode(errors="replace"))
    utiles = [l for l in texte.splitlines() if l.strip() and not l.startswith(("section_start", "section_end"))]
    return "\n".join(utiles[-lignes:])


def rapporter(pr, mr):
    """Écrit (ou met à jour) un commentaire sur la PR GitHub avec le résultat du pipeline GitLab."""
    pipeline = gitlab(f"merge_requests/{mr['iid']}").get("head_pipeline")
    if not pipeline:
        return
    statut, sha = pipeline["status"], pipeline["sha"]
    if statut not in ("success", "failed", "canceled"):
        return
    entete = f"{MARQUE}\n<!-- sha={sha} statut={statut} -->\n"
    commentaires = github(f"repos/{DEPOT}/issues/{pr['number']}/comments?per_page=100")
    existant = next((c for c in commentaires if MARQUE in (c.get("body") or "")), None)
    if existant and entete in existant["body"]:
        return  # déjà signalé pour ce commit
    if statut == "success":
        corps = (f"✅ **CI GitLab verte** pour `{sha[:8]}` (merge request !{mr['iid']}). "
                 "La PR peut être relue puis fusionnée sur GitLab.")
    else:
        jobs = gitlab(f"pipelines/{pipeline['id']}/jobs?per_page=100")
        echecs = [j for j in jobs if j["status"] == "failed"]
        parties = [f"❌ **CI GitLab en échec** pour `{sha[:8]}` (merge request !{mr['iid']}).",
                   "Corrige les erreurs ci-dessous et pousse sur cette PR : la CI repassera au prochain rapatriement "
                   "(15 minutes au plus). Les règles sont dans `AGENTS.md`."]
        for job in echecs:
            try:
                extrait = journal(job["id"])
            except Exception as err:  # le résumé reste utile sans l'extrait
                extrait = f"(journal indisponible : {err})"
            parties.append(f"<details><summary>Job <code>{job['name']}</code> en échec</summary>\n\n```\n{extrait[-6000:]}\n```\n</details>")
        corps = "\n\n".join(parties)
    texte = entete + corps
    if existant:
        github(f"repos/{DEPOT}/issues/comments/{existant['id']}", "PATCH", {"body": texte})
    else:
        github(f"repos/{DEPOT}/issues/{pr['number']}/comments", "POST", {"body": texte})
    print(f"PR #{pr['number']} : résultat {statut} signalé sur GitHub.")


def titre(pr):
    """Titre de la merge request : une PR GitHub en brouillon reste en brouillon."""
    return ("Draft: " if pr.get("draft") else "") + pr["title"]


def suivre_titre(pr, mr):
    """Recopie sur la merge request le titre et l'état brouillon de la PR."""
    if mr["title"] != titre(pr):
        gitlab(f"merge_requests/{mr['iid']}", "PUT", {"title": titre(pr)})
        print(f"PR #{pr['number']} : titre ou brouillon mis à jour sur !{mr['iid']}.")


def ouvrir_mr(pr, branche, cible):
    """Ouvre la merge request. Juste après le push, GitLab peut ne pas encore
    connaître la branche (HTTP 400) : on réessaie quelques secondes plus tard."""
    for essai in range(6):
        try:
            return gitlab("merge_requests", "POST", {
                "source_branch": branche,
                "target_branch": cible,
                "title": titre(pr),
                "description": description(pr),
                "labels": "github",
                "remove_source_branch": True,
            })
        except ErreurAPI as err:
            if err.code != 400 or essai == 5:
                raise
            time.sleep(5)


def relancer_si_sans_pipeline(pr, mr):
    """Filet de sécurité : GitLab lance lui-même le pipeline d'une nouvelle
    merge request, mais s'il manque, on le demande au passage suivant."""
    if gitlab(f"merge_requests/{mr['iid']}").get("head_pipeline"):
        return
    try:
        gitlab(f"merge_requests/{mr['iid']}/pipelines", "POST")
        print(f"PR #{pr['number']} : pipeline lancé sur !{mr['iid']}.")
    except ErreurAPI as err:
        # 405 tant que GitLab prépare la merge request : on réessaiera.
        print(f"PR #{pr['number']} : pipeline pas encore lançable sur !{mr['iid']} ({err.code}).")


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
    if ouverte:
        suivre_titre(pr, ouverte)
    if sha_gitlab(branche) == tete and ouverte:
        print(f"PR #{n} : à jour (!{ouverte['iid']}).")
        relancer_si_sans_pipeline(pr, ouverte)
        rapporter(pr, ouverte)
        return
    git("fetch", "--quiet", URL_GH, f"+refs/pull/{n}/head:refs/rapatriement/pr-{n}", jeton=JETON_GH)
    git("fetch", "--quiet", URL_GL, f"+refs/heads/{cible}:refs/rapatriement/cible", jeton=JETON_GL, utilisateur="oauth2")
    deja = subprocess.run(["git", "merge-base", "--is-ancestor", tete, "refs/rapatriement/cible"])
    if deja.returncode == 0 and not ouverte:
        print(f"PR #{n} : ses commits sont déjà dans {cible} sur GitLab, rien à faire.")
        return
    # Seules les branches github/pr-* sont réécrites : elles appartiennent au rapatriement.
    git("push", "--quiet", "--force", URL_GL, f"refs/rapatriement/pr-{n}:refs/heads/{branche}",
        jeton=JETON_GL, utilisateur="oauth2")
    if ouverte:
        print(f"PR #{n} : nouveaux commits poussés sur !{ouverte['iid']}.")
        return
    mr = ouvrir_mr(pr, branche, cible)
    # Pas d'appel à merge_requests/:iid/pipelines ici : GitLab lance déjà le
    # pipeline de la nouvelle merge request, et l'appel répondait 405 tant que
    # la merge request était en préparation, ce qui faisait échouer le job.
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
