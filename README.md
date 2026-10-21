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

### Listes de tâches

Des listes natives de Home Assistant : « Toutes les tâches », une par personne et
une par projet si tu les actives. On peut y créer, modifier, terminer et supprimer
des tâches. Les tâches terminées aujourd'hui y apparaissent aussi, en lecture
seule.

### Capteurs

- **Un capteur par tâche**, avec `points`, `status`, `pending_approval`,
  `assignee_ids`, `frequency`, `interval_type` (`hours`, `days`, `weeks`,
  `months` ou `years`) et l'échéance.
- **Un capteur de points par membre**, par exemple `sensor.hopla_points_elena` :
  l'état est le nombre de points encore disponibles, avec `total_points`,
  `points_redeemed`, la photo de profil Hopla du membre et sa série : `streak`
  (jours d'affilée avec au moins une tâche faite), `best_streak` et
  `streak_done_today`. Il porte aussi le rang, qui suit les points gagnés depuis
  le début (`rank`, `rank_icon`, `rank_level`, `next_rank`, `next_rank_points`),
  et les quêtes en cours (`quests` : `name`, `progress`, `target`, `reward`,
  `done`).
- **`sensor.hopla_pending_approvals`** : les tâches qui attendent une validation,
  avec qui les a faites (attribut `tasks`).
- **`sensor.hopla_rewards`** : les récompenses actives et leur coût (attribut
  `rewards`), et les demandes de récompense en attente (attribut `requests`).
- **`sensor.hopla_bonus_et_penalites`** : les préréglages de bonus et de
  pénalités réglés dans Hopla (attribut `points_presets`, avec `id`, `name` et
  `points`, négatif pour une pénalité) et les derniers mouvements de points
  (attribut `recent`).
- **`sensor.hopla_jeux_du_jour`** : l'état est le nom de la tâche surprise du
  jour, avec les attributs `surprise` (`task_id`, `task_name`, `points` en plus),
  `bonus_period` (la période bonus en cours : `name`, `multiplier`, `ends_at`),
  `streak_every`, `streak_bonus` et `challenges` (les défis en cours :
  `name`, `shared` pour un défi en famille, `total`, `target`, `progress` par
  membre, `reward_text`, `done`, `winners`). Les règles se règlent dans Hopla, onglet
  Jeux de la page Points.
- **`binary_sensor.hopla_mode_parent`** : allumé quand le mode parent est ouvert
  sur la tablette.

### Objets Hopla

Les « objets » Hopla deviennent des interrupteurs (oui/non), des nombres ou des
textes dans Home Assistant.

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
| `hopla_points_changed` | Les points d'un membre bougent : tâche, tâche annulée, récompense, bonus ou pénalité | `user_id`, `user_name`, `action` (`task`, `undo`, `redeem`, `bonus` ou `penalty`), `points`, `delta` (signé), `reason`, `created_by_name` |
| `hopla_surprise_task` | La tâche surprise du jour est tirée | `task_id`, `task_name`, `points`, `day` |
| `hopla_bonus_period_started` / `hopla_bonus_period_ended` | Une période bonus commence ou se termine | `name`, `multiplier`, `starts_at`, `ends_at` |
| `hopla_rank_up` | Un membre passe au rang suivant | `user_id`, `user_name`, `name`, `icon`, `level`, `next_name` |
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
les membres par points, avec une couronne pour le premier (les ex æquo partagent
la marche). Chaque tâche du jour tient sur une ligne : son nom, ses points et une
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
entity: todo.toutes_les_taches
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
