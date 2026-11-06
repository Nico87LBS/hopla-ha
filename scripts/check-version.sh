#!/usr/bin/env bash
# La version du manifest est X.Y.Z et monte à chaque PR qui change autre chose que de la documentation.
# Usage : bash scripts/check-version.sh <base>   (par exemple origin/main)
set -euo pipefail

base="${1:-origin/main}"
manifest=custom_components/hopla/manifest.json
version=$(jq -r .version "$manifest")
echo "$version" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || { echo "::error file=$manifest::La version doit être X.Y.Z, pas « $version »"; exit 1; }

previous=$(git show "$base:$manifest" 2>/dev/null | jq -r .version || true)
[ -z "$previous" ] && exit 0

# La documentation, la CI, les scripts et les tests ne demandent pas de nouvelle version.
changed=$(git diff --name-only "$base"...HEAD | grep -vE '(\.md$|^\.github/|^scripts/|^tests/)' || true)
[ -z "$changed" ] && exit 0

highest=$(printf '%s\n%s\n' "$previous" "$version" | sort -V | tail -1)
if [ "$version" = "$previous" ] || [ "$highest" != "$version" ]; then
  echo "::error file=$manifest::La version est $version, elle doit dépasser $previous (0.28.0 → 0.28.1 pour une correction, 0.29.0 pour une nouveauté)."
  exit 1
fi
