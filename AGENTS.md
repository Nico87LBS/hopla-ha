# Consignes obligatoires pour les agents — hopla-ha

Intégration Home Assistant de Hopla (installée par HACS depuis GitHub). La référence du code est GitLab (https://gitlab.lebosse.me/hopla/hopla-ha) ; GitHub en est le miroir.

## Branche, version et commits
1. Créer une branche dédiée à partir de `main` à jour ; ne jamais modifier `main` directement.
2. Monter `version` dans `custom_components/hopla/manifest.json` dans chaque PR qui change autre chose que la documentation, les scripts, les tests ou la CI : correctif → `0.34.0` à `0.34.1`, nouveauté → `0.35.0`.
3. Rédiger **tous** les messages de commit et le titre de la PR en français, sans préfixe anglais (`fix:`, `feat:`…).
4. Garder le même style visuel que l'interface web de Hopla (têtes et photos avec pastilles d'état).
5. Ne **jamais fusionner** une PR sans accord explicite de l'utilisateur.

## Contrôles à lancer avant de pousser
Ce sont ceux de `.github/workflows/validate.yml`, qui tournent sur chaque PR GitHub :

```sh
git fetch origin main
PR_TITLE="<titre de la PR>" bash scripts/check-french.sh origin/main
bash scripts/check-version.sh origin/main
python -m unittest discover -s tests -v
for t in tests/test_*.mjs; do node --experimental-default-type=module "$t" || exit 1; done
```

Les tests `*_dom.mjs` demandent `happy-dom` : `npm install --prefix /tmp/hopla-card-tests --no-package-lock happy-dom@20.14.5` puis `DOM_TEST_MODULE=/tmp/hopla-card-tests/node_modules/happy-dom/lib/index.js`. Plusieurs tests attendent `TZ=Europe/Brussels`.

## Où voir le résultat de la CI
Les vérifications de hopla-ha restent sur GitHub Actions (dépôt public) : lire les contrôles de la PR GitHub, corriger tant qu'ils sont rouges, et ne déclarer la PR prête qu'une fois tout vert. La PR est ensuite copiée en merge request sur GitLab, où elle est fusionnée.
