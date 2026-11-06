#!/usr/bin/env bash
# Les titres de PR et les messages de commit sont en français.
# Usage : PR_TITLE="..." bash scripts/check-french.sh <base>
# Les commits de fusion sont ignorés.
set -euo pipefail

base="${1:-origin/main}"
failed=0

# Un préfixe « fix: », « feat(x): » ou un verbe anglais en tête : c'est de l'anglais.
english_start='^(feat|fix|chore|refactor|style|test|tests|docs|build|perf|security|ci|revert)(\([^)]*\))?!?:|^(add|adds|added|fix|fixes|fixed|update|updates|remove|removes|implement|redesign|harden|preserve|persist|report|improve|allow|make|use|enable|disable|show|handle|prevent|support|correct|restore|reduce|extract|rename|move|clean|cover|keep|apply|require|validate|sanitize|refactor|create|delete|replace|ensure|detect|stop|never|expose|document|manage)\b'
# Un mot de liaison ou une lettre accentuée français : un titre français en a presque toujours un.
french_marker="[àâçéèêëîïôûùüÿœ]|(^|[^[:alpha:]])(le|la|les|un|une|des|du|de|d'|l'|et|ou|pour|dans|sur|avec|en|au|aux|ne|pas|plus|que|qui|sans|par|se|ce|ces|est|sont|tous|toutes|chaque)([^[:alpha:]]|$)"

check() {
  local what="$1" text="$2"
  [ -z "$text" ] && return 0
  local lower
  lower=$(printf '%s' "$text" | tr '[:upper:]' '[:lower:]')
  if printf '%s' "$lower" | grep -Eq "$english_start"; then
    echo "::error::$what doit être en français : « $text »"
    failed=1
  elif ! printf '%s' "$lower" | grep -Eq "$french_marker"; then
    echo "::error::$what ne ressemble pas à du français : « $text »"
    failed=1
  fi
}

[ -n "${PR_TITLE:-}" ] && check "Le titre de la PR" "$PR_TITLE"
while IFS= read -r subject; do
  check "Le message de commit" "$subject"
done < <(git log "$base..HEAD" --no-merges --format=%s)

exit "$failed"
