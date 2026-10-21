# Hopla pour Home Assistant

Intégration Home Assistant (HACS) pour [Hopla](https://github.com/Nico87LBS/hopla) :
listes de tâches, capteurs de points et de récompenses, validations, « objets »
Hopla et cartes de tableau de bord. C'est elle qui envoie les notifications, le
serveur Hopla n'en envoie aucune.

## Installation

### Avec HACS

1. Ouvre HACS dans Home Assistant.
2. Menu « ⋮ » → **Dépôts personnalisés**.
3. Ajoute `https://github.com/Nico87LBS/hopla-ha`, catégorie **Intégration**.
4. Cherche « Hopla », installe-la, puis redémarre Home Assistant.

### Configuration

**Paramètres** → **Appareils et services** → **Ajouter une intégration** → **Hopla**.

- **Adresse du serveur Hopla** : par exemple `http://ton-serveur:2021`.
- **Jeton d'API** : à créer dans les réglages de ton compte Hopla.
- **Nombre de jours de tâches à venir** (7 par défaut, 0 pour toutes).
- **Liste « Toutes les tâches »**, **une liste par personne**, **une liste par projet**.

Les options de l'intégration ajoutent la sécurité de la tablette (voir plus bas).

## Ce que l'intégration crée

Les noms d'entités ci-dessous sont ceux d'un Home Assistant en français : Home
Assistant les fabrique dans sa langue au moment de l'installation. Tu peux les
renommer ensuite ; les cartes Hopla retrouvent leurs capteurs sans dépendre du nom.

### Les entités

| Entité | État | À quoi elle sert |
| --- | --- | --- |
| `todo.hopla_toutes_les_taches` | Nombre de tâches à faire | Liste de toutes les tâches : on peut y créer, modifier, terminer et supprimer des tâches. Les tâches terminées aujourd'hui y restent visibles, en lecture seule |
| `todo.hopla_taches_de_elena` | Idem | Une liste par membre, si l'option est cochée |
| `todo.hopla_taches_<projet>` | Idem | Une liste par projet, si l'option est cochée |
| `calendar.hopla_echeances` | Calendrier | Les échéances à venir, récurrences comprises |
| `calendar.hopla_historique` | Calendrier | Les tâches faites, à leur date |
| `sensor.<nom de la tâche>` | Nom de la tâche | Un capteur par tâche (détails plus bas) |
| `sensor.hopla_points_elena` | Points encore disponibles | Un capteur par membre, avec son rang, sa série et ses quêtes |
| `sensor.hopla_validations_en_attente` | Nombre de tâches à valider | Ce qui attend un parent |
| `sensor.hopla_recompenses` | Nombre de récompenses actives | Les récompenses et les demandes en attente |
| `sensor.hopla_bonus_et_penalites` | Nombre de préréglages | Les bonus et pénalités tout prêts, et les derniers mouvements de points |
| `sensor.hopla_jeux_du_jour` | Nom de la tâche surprise du jour | La période bonus en cours et les défis |
| `binary_sensor.hopla_mode_parent` | Allumé si le mode parent est ouvert | La sécurité de la tablette (voir plus bas) |
| `switch`, `number`, `text` ou `sensor.hopla_things_<objet>` | La valeur de l'objet | Les « objets » Hopla : oui/non, nombre ou texte |

### Capteur de points d'un membre

`sensor.hopla_points_elena` : l'état est le nombre de points qu'Elena peut encore
dépenser.

| Attribut | Contenu |
| --- | --- |
| `hopla_member_id`, `display_name`, `username`, `role` | Qui est ce membre |
| `total_points` | Points gagnés depuis le début (c'est ce qui fixe le rang) |
| `points_redeemed` | Points dépensés en récompenses ou perdus en pénalités |
| `rank`, `rank_icon`, `rank_level` | Rang actuel, par exemple `Hop Hop`, `🐸`, `2` |
| `rank_points`, `next_rank`, `next_rank_icon`, `next_rank_points` | Points du rang actuel, et rang suivant avec les points qu'il demande (vide au dernier rang) |
| `rank_stars` | Étoiles de prestige ⭐ : une de plus à chaque tour complet des rangs, gardées pour toujours |
| `rank_round_points`, `next_star_points` | Points gagnés dans le tour en cours, et points du tour qui donnent l'étoile suivante |
| `streak`, `best_streak`, `streak_done_today` | Série : jours d'affilée avec au moins une tâche faite, record, et si aujourd'hui compte déjà |
| `quests` | Quêtes en cours : `name`, `progress`, `target`, `reward`, `done`, `period` (`week` ou `month`), `ends_at` |
| `recent_completions` | Tâches faites ces deux derniers jours : `task_id`, `name`, `points`, `completed_at` |
| `entity_picture` | Photo de profil Hopla |

### Capteur d'une tâche

L'état est le nom de la tâche.

| Attribut | Contenu |
| --- | --- |
| `task_id`, `description`, `labels`, `priority`, `is_active` | La tâche |
| `points` | Points qu'elle rapporte |
| `next_due_date` | Prochaine échéance |
| `frequency_type`, `frequency`, `interval_type` | Récurrence ; `interval_type` vaut `hours`, `days`, `weeks`, `months` ou `years` |
| `assigned_to`, `assigned_to_user_id`, `assignee_ids` | À qui elle revient, et qui peut la faire |
| `status`, `pending_approval` | État, et `true` si elle attend la validation d'un parent |

### Capteurs de la famille

| Capteur | Attribut | Contenu |
| --- | --- | --- |
| `sensor.hopla_validations_en_attente` | `tasks` | Chaque tâche à valider : `task_id`, `task_name`, `points`, `completed_by`, `completed_by_name` |
| `sensor.hopla_recompenses` | `rewards` | Chaque récompense : `id`, `name`, `points_cost`, `description`, et sa limite (`quota_count`, `quota_period`, `quota_used`, `quota_resets_at`) |
| | `requests` | Demandes en attente : `redemption_id`, `reward_name`, `points_cost`, `user_id`, `user_name`, `requested_at` |
| `sensor.hopla_bonus_et_penalites` | `points_presets` | Préréglages : `id`, `name`, `points` (négatif pour une pénalité) |
| | `recent` | Derniers mouvements de points : `user_name`, `action`, `points`, `delta`, `reason`, `created_at` |
| `sensor.hopla_jeux_du_jour` | `surprise` | Tâche surprise du jour : `task_id`, `task_name`, `points` en plus, et `task_ids`, les copies de la tâche au même nom (une par enfant), qui rapportent toutes le bonus |
| | `bonus_period` | Période bonus en cours : `name`, `multiplier`, `starts_at`, `ends_at` |
| | `streak_every`, `streak_bonus` | Le bonus de série : tous les combien de jours, et combien de points |
| | `challenges` | Défis en cours : `name`, `shared` (défi en famille), `members`, `progress` par membre, `total`, `target`, `reward`, `reward_text`, `done`, `winners`, `ends_at` |

Les jeux se règlent dans Hopla, onglet Jeux de la page Points.

## Synchro en temps réel

L'intégration garde une connexion ouverte avec le flux d'événements de Hopla,
avec le même jeton d'API. Chaque changement fait dans Hopla (tâche créée,
terminée, validée ou modifiée, récompense, objet, membre) arrive dans Home
Assistant en quelques secondes. Il n'y a pas d'intervalle à régler : tant que la
connexion tient, une mise à jour complète passe quand même toutes les 30 minutes
par sécurité, et toutes les 5 minutes quand elle est coupée. La connexion revient
toute seule, en attendant un peu plus après chaque échec (jusqu'à 5 minutes).

## Événements pour les automatisations

| Événement | Quand | Données |
| --- | --- | --- |
| `hopla_task_completed` | Une tâche est terminée, dans Hopla ou ici | `task_id`, `task_name`, `points`, `completed_by`, `completed_by_name` |
| `hopla_task_pending_approval` | Une tâche attend la validation d'un parent | `task_id`, `task_name`, `points`, `completed_by`, `completed_by_name` |
| `hopla_task_approval_resolved` | Elle a été validée ou refusée, ici ou dans Hopla | `task_id`, `task_name` |
| `hopla_reward_requested` | Un enfant demande une récompense depuis la tablette | `redemption_id`, `reward_id`, `reward_name`, `points_cost`, `user_id`, `user_name` |
| `hopla_reward_request_resolved` | La demande a été validée ou refusée | `redemption_id`, `reward_name`, `user_id` |
| `hopla_points_changed` | Les points d'un membre bougent : tâche, tâche annulée, récompense, bonus, pénalité ou remise à zéro | `user_id`, `user_name`, `action` (`task`, `undo`, `redeem`, `bonus`, `penalty` ou `reset`), `points`, `delta` (signé), `reason`, `created_by_name` |
| `hopla_surprise_task` | La tâche surprise du jour est tirée | `task_id`, `task_name`, `points`, `day` |
| `hopla_bonus_period_started` / `hopla_bonus_period_ended` | Une période bonus commence ou se termine | `name`, `multiplier`, `starts_at`, `ends_at` |
| `hopla_rank_up` | Un membre passe au rang suivant, ou gagne une étoile ⭐ et repart au premier rang | `user_id`, `user_name`, `name`, `icon`, `level`, `next_name`, `stars`, `new_star` |
| `hopla_quest_completed` | Un membre réussit une quête | `user_id`, `user_name`, `name`, `reward` |
| `hopla_challenge_won` | Un membre gagne un défi chacun pour soi | `user_id`, `user_name`, `name`, `reward`, `reward_text` |
| `hopla_goal_reached` | La famille atteint un défi commun | `name`, `total`, `target`, `reward_text`, `member_names` |
| `hopla_task_reminder` | À chaque rappel réglé sur une tâche dans Hopla | voir ci-dessous |

### Rappels de tâches

Les rappels réglés sur une tâche dans Hopla (avant l'échéance, à l'échéance ou
après) deviennent un événement `hopla_task_reminder` au bon moment, avec
`task_id`, `task_name`, `due_date`, `reminder_at`, `offset_minutes` (négatif avant
l'échéance), `kind` (`before`, `due` ou `after`), `assigned_to`,
`assigned_to_name`, `assignee_ids` et `points`. Terminer ou décaler la tâche
annule ses rappels. Les rappels dont l'heure est passée pendant que Home
Assistant était arrêté ne sont pas envoyés après coup.

## Blueprints

Pour importer un blueprint : **Paramètres** → **Automatisations et scènes** →
**Blueprints** → **Importer un blueprint**, puis colle l'adresse GitHub du fichier.

- [`task_reminder.yaml`](blueprints/automation/hopla/task_reminder.yaml) : un
  rappel par personne. Choisis son capteur de points Hopla, puis un service de
  notification (son téléphone par exemple) et d'autres actions si tu veux, comme
  une annonce sur une enceinte.
- [`approval_notification.yaml`](blueprints/automation/hopla/approval_notification.yaml) :
  sur le téléphone d'un parent, une notification avec les boutons Valider et
  Refuser pour chaque tâche à valider et chaque demande de récompense. Elle
  disparaît dès que la demande est traitée, où que ce soit.

## Mises à jour

Chaque nouvelle version de l'intégration est publiée comme une *release* GitHub.
HACS la voit et crée une entité de mise à jour, `update.hopla_update`. Home
Assistant l'affiche alors dans **Paramètres**, avec un badge, et on l'installe
d'une touche, puis on redémarre.

Pour être prévenu sur ton téléphone, une automatisation sur cette entité suffit :

```yaml
alias: Hopla - mise à jour disponible
triggers:
  - trigger: state
    entity_id: update.hopla_update
    to: "on"
actions:
  - action: notify.mobile_app_ton_telephone
    data:
      title: "Mise à jour de Hopla"
      message: >-
        La version {{ state_attr('update.hopla_update', 'latest_version') }} est disponible
        (installée : {{ state_attr('update.hopla_update', 'installed_version') }}).
```

L'icône de l'intégration est fournie dans `custom_components/hopla/brand/`.
Home Assistant l'affiche à partir de la version 2026.3.

## Sécurité de la tablette

Pour une tablette que toute la famille utilise, crée dans Home Assistant un
utilisateur dédié qui n'est pas administrateur, par exemple « Tablette ». Puis,
dans les options de l'intégration Hopla :

- **Parents** : choisis les comptes Home Assistant des parents.
- **Code parent** : quatre chiffres. Seul un condensé du code est enregistré.

Ensuite :

- Tout le monde peut terminer des tâches et demander des récompenses.
- Valider ou refuser une tâche, créer, modifier, passer ou supprimer une tâche,
  et valider une demande de récompense sont réservés aux parents.
- Sur la tablette, le cadenas de la carte famille ouvre le mode parent avec le
  code parent, pour deux minutes. Il se referme tout seul, ou d'une touche.
- Une récompense échangée depuis la tablette devient une demande : les points ne
  sont dépensés qu'une fois qu'un parent l'a validée.
- Les bonus et pénalités sont réservés aux parents.
- Après cinq codes faux, il faut attendre cinq minutes.
- Les automatisations comptent comme des parents, puisque ce sont eux qui les
  écrivent.

Sans parent choisi, rien ne change : tout le monde garde tous les droits.

## Services

| Service | Rôle | Réservé aux parents |
| --- | --- | --- |
| `hopla.complete_task` | Terminer une tâche, éventuellement pour un membre (`completed_by`). Une tâche à valider attend un parent, et la réponse contient `pending_approval: true` | |
| `hopla.complete_assigned_task` | Terminer une tâche pour son membre assigné | |
| `hopla.redeem_reward` | Échanger une récompense pour un membre (`user_id`). Venant d'un parent, c'est validé tout de suite ; sinon c'est une demande (`pending: true`) | |
| `hopla.approve_task` / `hopla.reject_task` | Valider ou refuser une tâche en attente | ✓ |
| `hopla.approve_reward` / `hopla.reject_reward` | Valider ou refuser une demande de récompense (`redemption_id`) | ✓ |
| `hopla.create_task`, `hopla.update_task`, `hopla.delete_task` | Créer, modifier, supprimer une tâche | ✓ |
| `hopla.skip_task`, `hopla.postpone_task` | Passer une tâche à sa prochaine occurrence | ✓ |
| `hopla.adjust_points` | Donner un bonus ou une pénalité à un membre (`user_id`), avec `points` (négatif pour une pénalité) ou un préréglage (`preset_id`), et une raison (`reason`) si tu veux. Une pénalité ne fait jamais passer le solde sous zéro | ✓ |
| `hopla.unlock_parent_mode` | Ouvrir le mode parent pour deux minutes avec le code (`pin`) | |
| `hopla.lock_parent_mode` | Refermer le mode parent | |

Pour réactiver une tâche archivée avec `hopla.update_task`, mets
`force_unarchive: true`. Pour l'assigner, donne `assigned_to` avec l'ID Hopla d'un
membre, ou `null` pour n'importe qui.

## Cartes

Les deux cartes sont fournies avec l'intégration et chargées automatiquement :
rien à installer à part. Recharge le navigateur après une mise à jour. Elles
suivent la langue de Home Assistant, en français ou en anglais ; leurs textes
sont dans [`frontend/locales`](custom_components/hopla/frontend/locales), un
fichier par langue.

### Carte famille

`custom:hopla-family-card` est faite pour une tablette murale. Un podium classe
les membres par points gagnés depuis le début, pour qu'une récompense échangée ne
fasse pas reculer, avec une couronne pour le premier (les ex æquo partagent la
marche). Sous chaque prénom, les points qui restent à dépenser, toujours affichés. Chaque tâche du jour tient sur une ligne : son nom, ses points et une
photo par membre assigné ; toucher une photo termine la tâche pour ce membre. Une
tâche à valider reste affichée avec un sablier et la photo de qui l'a faite,
jusqu'à la réponse d'un parent. Les tâches déjà faites aujourd'hui suivent, avec
la photo de qui les a faites. Toute photo qu'on peut toucher a un anneau.

Le podium montre la série de chacun avec une flamme, grisée tant que personne
n'a encore fait de tâche aujourd'hui pour la continuer. Pendant une période bonus,
un bandeau rappelle le multiplicateur et le temps restant, et la tâche surprise du
jour porte une étincelle avec ses points en plus.

Pour une tâche que chacun doit faire, comme faire son lit, crée-la dans Hopla une
fois par membre. La carte regroupe les tâches de même nom sur une ligne.

Les récompenses montrent une photo par membre : un cadeau quand il peut la
prendre, un cadenas avec les points qui manquent, une horloge avec le temps
restant quand la limite de la période est atteinte, ou un sablier quand une
demande attend un parent. Les limites se règlent sur la récompense dans Hopla.

Quand des parents sont choisis, un cadenas en haut à droite ouvre le pavé du code
parent. En mode parent, il affiche le temps restant et referme le mode d'une
touche. Les boutons Valider et Refuser n'apparaissent que pour un parent.

En mode parent, ou pour un parent, la carte montre aussi les bonus et pénalités
préréglés dans Hopla (onglet Jeux de la page Points) : touche deux fois la photo
d'un enfant pour lui donner « Chambre rangée (+5) » ou « Dispute (−3) ».

```yaml
type: custom:hopla-family-card
members: [2, 3]        # membres avec un bouton photo (par défaut : tout le monde)
labels: [enfants]      # seulement les tâches avec une de ces étiquettes
due: today             # today (du jour, en retard ou sans date) ou all
show_points: true      # le podium
show_todo: true        # les tâches à faire
show_done: true        # les tâches faites aujourd'hui
show_rewards: true     # les récompenses
show_approval: false   # boutons Valider et Refuser, pour les parents
allow_redeem: false    # échanger des récompenses depuis la carte (deux touches)
show_bonus: true       # les bonus et pénalités, pour les parents
show_goals: true       # les quêtes et les défis
```

Chaque partie peut être masquée : la même carte peut n'afficher que les
récompenses sur une autre vue. Les photos viennent des profils Hopla ; un parent
règle celle d'un enfant dans Hopla, sous Réglages → Comptes gérés.

### Carte des tâches d'un membre

`custom:hopla-user-todo-card` affiche les tâches d'un membre (ou de tous) avec
une case pour terminer et des boutons pour passer une occurrence, changer
l'échéance et réassigner. Son éditeur visuel regroupe les réglages en sections :
Essentiel, Filtres des tâches, Tâches terminées, Détails des tâches, Actions
disponibles et Apparence.

```yaml
type: custom:hopla-user-todo-card
entity: todo.hopla_toutes_les_taches
user_id: all                    # un ID de membre, ou all
display_filters: [overdue, today, future]   # vide pour toutes ; undated pour sans date
upcoming_days: 7                # jours à l'avance pour « À venir » (0 : sans limite)
task_view: both                 # pending, completed ou both
completed_days: 1               # jours d'historique (1 à 7)
completed_filter: all           # matching : suivre le filtre de dates
labels: [maison]                # filtrer par étiquettes
label_match: any                # any (OU) ou all (ET)
sort_by: due_date               # due_date, priority ou name
due_display: date               # date, relative ou both
show_points: true
show_recurrence: true
show_labels: false
include_anyone: false           # ajouter les tâches pour n'importe qui
```

Terminer une tâche la crédite au membre assigné, même si quelqu'un d'autre
touche le bouton ; une tâche pour n'importe qui est créditée au propriétaire du
jeton d'API. Les actions qui modifient une tâche (passer, changer l'échéance,
réassigner) demandent un parent quand la sécurité de la tablette est active.

## Licence

Cette intégration est une version modifiée d'un logiciel libre distribué sous
licence GNU General Public License v3.0, et reste distribuée sous la même
licence : voir le fichier [LICENSE](LICENSE).
