import assert from 'node:assert/strict';
globalThis.HTMLElement = class {};
globalThis.customElements = {define() {}, get() {}, whenDefined() { return Promise.resolve(); }};
globalThis.window = {};
const {boardData, labelNames, parentAccess, podium, rewardState, taskRows} = await import('../custom_components/hopla/frontend/hopla-family-card.js');

assert.deepEqual(labelNames([{name: 'Enfants '}, 'Maison', {name: ''}, null]), ['enfants', 'maison']);
assert.deepEqual(labelNames('a, b'), ['a', 'b']);

const member = (id, name, points, role = 'member') => ({state: String(points), attributes: {hopla_member_id: id, display_name: name, role, entity_picture: `/p/${id}.jpg`}});
const task = (id, name, extra = {}) => ({state: name, attributes: {task_id: id, friendly_name: name, is_active: true, assignee_ids: [2, 3], labels: [{name: 'enfants'}], ...extra}});
const hass = {
  entities: {'sensor.other_task': {platform: 'other'}},
  states: {
    'sensor.hopla_points_nico': member(1, 'Nico', 0, 'admin'),
    'sensor.hopla_points_elena': member(2, 'Elena', 5),
    'sensor.hopla_points_anna': member(3, 'Anna', 2),
    'sensor.chambre': task(10, 'Chambre', {next_due_date: '2026-10-20T08:00:00Z', points: 3, pending_approval: true}),
    'sensor.table': task(11, 'Table', {next_due_date: '2026-10-20T17:00:00Z', assignee_ids: [3]}),
    'sensor.dents': task(12, 'Dents'),
    'sensor.plantes': task(13, 'Plantes', {next_due_date: '2026-10-25T09:00:00Z'}),
    'sensor.poubelles': task(14, 'Poubelles', {labels: [], assignee_ids: [1]}),
    'sensor.archived': task(15, 'Archived', {is_active: false}),
    'sensor.other_task': task(16, 'Other integration'),
    'sensor.hopla_rewards': {state: '1', attributes: {rewards: [{id: 1, name: 'Lecture', points_cost: 3}]}},
  },
};
const now = new Date('2026-10-20T12:00:00');

let data = boardData(hass, {due: 'today', labels: ['Enfants'], members: [2, 3]}, now);
assert.deepEqual(data.members.map(m => m.name), ['Elena', 'Anna']);
assert.deepEqual(data.tasks.map(t => t.name), ['Chambre', 'Table', 'Dents'], 'today and undated tasks, other integrations excluded');
assert.equal(data.tasks[0].pending, true);
assert.deepEqual(data.tasks[1].members.map(m => m.name), ['Anna'], 'only assignees get a photo');
assert.deepEqual(data.rewards.map(r => r.name), ['Lecture']);

data = boardData(hass, {due: 'all'}, now);
assert.deepEqual(data.tasks.map(t => t.name), ['Chambre', 'Table', 'Plantes', 'Dents', 'Poubelles']);
assert.deepEqual(data.tasks.at(-1).members.map(m => m.name), ['Nico']);

// A task assigned only to members outside the board is hidden.
data = boardData(hass, {due: 'all', members: [2, 3]}, now);
assert.equal(data.tasks.some(t => t.name === 'Poubelles'), false);
// The bare task name is the state; friendly_name may carry the device name.
data = boardData({states: {'sensor.e': member(2, 'Elena', 1), 'sensor.x': {state: 'Ranger', attributes: {task_id: 1, friendly_name: 'Hopla Chores Ranger', is_active: true}}}}, {due: 'all'}, now);
assert.equal(data.tasks[0].name, 'Ranger');

// A pending task knows who completed it, from the pending approvals sensor.
const withPending = {states: {...hass.states, 'sensor.hopla_pending_approvals': {state: '1', attributes: {tasks: [{task_id: 10, completed_by: 2}]}}}};
data = boardData(withPending, {due: 'today', members: [2, 3]}, now);
assert.equal(data.tasks.find(t => t.id === 10).completedBy.name, 'Elena');

// Tasks done today come from each member's recent completions, newest first.
const recent = (id, name, points, items) => ({...member(id, name, points), attributes: {...member(id, name, points).attributes, recent_completions: items}});
const withDone = {states: {...hass.states,
  'sensor.hopla_points_elena': recent(2, 'Elena', 5, [{task_id: 20, name: 'Lit', points: 1, completed_at: '2026-10-20T07:00:00Z', labels: []}, {task_id: 21, name: 'Hier', completed_at: '2026-10-19T07:00:00Z'}]),
  'sensor.hopla_points_anna': recent(3, 'Anna', 2, [{task_id: 22, name: 'Chat', points: 2, completed_at: '2026-10-20T09:00:00Z', labels: []}])}};
data = boardData(withDone, {due: 'today', members: [2, 3]}, now);
assert.deepEqual(data.done.map(d => `${d.name}:${d.member.name}`), ['Chat:Anna', 'Lit:Elena']);
assert.deepEqual(boardData(withDone, {due: 'today', members: [2, 3], labels: ['enfants']}, now).done, [], 'label filter applies to done tasks');
// A task done by each child shows once, with both faces.
const twice = {states: {...hass.states,
  'sensor.hopla_points_elena': recent(2, 'Elena', 5, [{task_id: 30, name: 'Lit', points: 8, completed_at: '2026-10-20T07:00:00Z', labels: []}]),
  'sensor.hopla_points_anna': recent(3, 'Anna', 2, [{task_id: 31, name: 'lit ', points: 3, completed_at: '2026-10-20T09:00:00Z', labels: []},
    {task_id: 22, name: 'Chat', points: 2, completed_at: '2026-10-20T08:00:00Z', labels: []}])}};
data = boardData(twice, {due: 'today', members: [2, 3]}, now);
assert.deepEqual(data.doneRows.map(r => `${r.name}:${r.items.map(i => i.member.name).join('+')}:${r.points}`), ['lit:Anna+Elena:8', 'Chat:Anna:2']);

// Podium: one step per member up to three, ties share a step.
const m = (id, points) => ({id, points});
assert.deepEqual(podium([m(1, 5)]).map(step => step.map(x => x.id)), [[1]]);
assert.deepEqual(podium([m(1, 5), m(2, 3)]).map(step => step.map(x => x.id)), [[1], [2]]);
assert.deepEqual(podium([m(1, 4), m(2, 4)]).map(step => step.map(x => x.id)), [[1, 2], []]);
assert.deepEqual(podium([m(1, 4), m(2, 4), m(3, 1)]).map(step => step.map(x => x.id)), [[1, 2], [3], []]);
assert.deepEqual(podium([m(1, 9), m(2, 7), m(3, 5), m(4, 1)]).map(step => step.map(x => x.id)), [[1], [2], [3]]);
// Points earned since the start rank the podium, not the balance left after rewards.
assert.deepEqual(podium([{id: 1, points: 2, earned: 90}, {id: 2, points: 30, earned: 40}]).map(step => step.map(x => x.id)), [[1], [2]]);

// Rewards: available, missing points, or out of quota until the reset.
const elena = {id: 2, points: 5};
assert.deepEqual(rewardState({points_cost: 3}, elena, now), {kind: 'available'});
assert.deepEqual(rewardState({points_cost: 9}, elena, now), {kind: 'points', missing: 4});
const daily = {points_cost: 3, quota_count: 1, quota_used: {'2': 1}, quota_resets_at: '2026-10-20T22:00:00Z'};
assert.equal(rewardState(daily, elena, now).kind, 'quota');
assert.equal(rewardState(daily, {id: 3, points: 3}, now).kind, 'available', 'quota is per member');
assert.equal(rewardState(daily, elena, new Date('2026-10-21T08:00:00')).kind, 'available', 'usage expires with the period');
// A task created once per child is one row: each photo completes that child's
// copy, a pending copy shows who did it, and a copy done today shows a check.
const E = {id: 2, name: 'Elena'}, A = {id: 3, name: 'Anna'};
const copy = (id, name, members, extra = {}) => ({id, name, points: 1, due: null, members, pending: false, completedBy: null, ...extra});
let rows = taskRows([copy(30, 'Faire son lit', [A]), copy(31, 'faire son lit ', [E])], [], [E, A]);
assert.equal(rows.length, 1);
assert.deepEqual(rows[0].slots.map(s => `${s.member.name}:${s.state}:${s.task.id}`), ['Elena:tap:31', 'Anna:tap:30']);
rows = taskRows([copy(30, 'Faire son lit', [A])], [{name: 'Faire son lit', member: E}, {name: 'Chat', member: A}], [E, A]);
assert.deepEqual(rows[0].slots.map(s => `${s.member.name}:${s.state}`), ['Elena:done', 'Anna:tap']);
rows = taskRows([copy(30, 'Lit', [A]), copy(31, 'Lit', [E], {pending: true, completedBy: E})], [], [E, A]);
assert.deepEqual(rows[0].slots.map(s => `${s.member.name}:${s.state}`), ['Elena:pending', 'Anna:tap']);
assert.equal(rows[0].pending, true);
rows = taskRows([copy(32, 'Dents', [E, A])], [{name: 'Dents', member: E}], [E, A]);
assert.deepEqual(rows[0].slots.map(s => s.state), ['tap', 'tap'], 'a member who can still do the task keeps a photo');
// Parent access: everyone without parents set, a parent's own account, or the tablet while parent mode is open.
const parentMode = (attributes, state = 'off') => ({state, attributes: {hopla_parent_mode: true, config_entry_id: 'entry', enabled: true,
  parent_users: ['nico-ha'], has_pin: true, unlocked_until: null, ...attributes}});
assert.equal(parentAccess({states: {}}).parent, true, 'no parent mode sensor keeps full access');
assert.equal(parentAccess({states: {'binary_sensor.mode_parent': parentMode({enabled: false})}}).guarded, false);
let access = parentAccess({user: {id: 'tablette'}, states: {'binary_sensor.mode_parent': parentMode({})}}, now);
assert.deepEqual([access.guarded, access.parent, access.entryId], [true, false, 'entry']);
assert.equal(parentAccess({user: {id: 'nico-ha'}, states: {'binary_sensor.mode_parent': parentMode({})}}, now).parent, true);
const open = parentMode({unlocked_until: '2026-10-20T12:01:30'}, 'on');
access = parentAccess({user: {id: 'tablette'}, states: {'binary_sensor.mode_parent': open}}, now);
assert.deepEqual([access.parent, access.unlocked], [true, true]);
assert.equal(parentAccess({user: {id: 'tablette'}, states: {'binary_sensor.mode_parent': open}}, new Date('2026-10-20T12:02:00')).parent, false,
  'an expired parent mode counts as closed even before the sensor updates');

// Reward requests come with the rewards sensor.
const withRequests = {states: {...hass.states, 'sensor.hopla_rewards': {state: '1', attributes: {rewards: [{id: 1, name: 'Lecture', points_cost: 3}],
  requests: [{redemption_id: 9, reward_id: 1, user_id: 2, reward_name: 'Lecture'}]}}}};
assert.deepEqual(boardData(withRequests, {}, now).requests.map(r => r.redemption_id), [9]);
assert.deepEqual(boardData(hass, {}, now).requests, []);
console.log('family card tests passed');

// Bonus and penalty presets come with their own sensor.
const withPresets = {...hass, states: {...hass.states, 'sensor.hopla_bonus': {state: '2', attributes: {
  points_presets: [{id: 1, name: 'Chambre rangée', points: 5}, {id: 2, name: 'Dispute', points: -3}], config_entry_id: 'abc'}}}};
const presetData = boardData(withPresets, {}, now);
assert.deepEqual(presetData.presets.map(p => p.points), [5, -3]);
assert.equal(presetData.presetsEntry, 'abc');
assert.equal(presetData.rewards.length, 1, 'the presets sensor is not taken for the rewards one');
assert.deepEqual(boardData(hass, {}, now).presets, []);

// Today's games: the surprise task, the bonus period and the streaks.
const withGames = {...hass, states: {...hass.states,
  'sensor.hopla_points_elena': {state: '5', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member', streak: 4, streak_done_today: true}},
  'sensor.hopla_jeux_du_jour': {state: 'Dents', attributes: {hopla_games: true, surprise: {task_id: 12, task_name: 'Dents', points: 5},
    bonus_period: {id: 1, name: 'Week-end double', multiplier: 2, ends_at: '2026-10-21T20:00:00Z'}}}}};
const games = boardData(withGames, {}, now);
assert.equal(games.period.multiplier, 2);
assert.equal(games.tasks.find(t => t.id === 12).surprise, 5);
assert.equal(games.tasks.find(t => t.id === 11).surprise, 0);
// Each child's copy of the surprise task, with the same name, keeps the bonus.
const dents = Object.values(withGames.states).find(s => s.attributes.task_id === 12);
const withCopy = {...withGames, states: {...withGames.states, 'sensor.dents_anna': {...dents, attributes: {...dents.attributes, task_id: 99}}}};
assert.equal(boardData(withCopy, {}, now).tasks.find(t => t.id === 99).surprise, 5);
assert.equal(games.members.find(m => m.id === 2).streak, 4);
assert.equal(games.rewards.length, 1, 'the games sensor is not taken for another one');
assert.equal(boardData(hass, {}, now).period, null);

// Ranks, quests and challenges.
const quest = {id: 7, name: 'Mettre la table', target: 5, progress: 3, reward: 8, done: false};
const withProgress = {...hass, states: {...hass.states,
  'sensor.hopla_points_elena': {state: '5', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member', total_points: 140,
    rank: 'Hop Hop', rank_icon: '🐸', rank_level: 2, rank_points: 100, next_rank: 'Super Hop', next_rank_icon: '🦘', next_rank_points: 300,
    quests: [quest]}},
  'sensor.hopla_jeux_du_jour': {state: 'unknown', attributes: {hopla_games: true, challenges: [
    {id: 1, name: 'Piscine', shared: true, members: [2, 3], progress: {2: 15, 3: 5}, total: 20, target: 200, done: false, winners: [], ends_at: '2026-10-25T00:00:00Z'},
    {id: 2, name: 'Fini', shared: false, members: [2], progress: {2: 3}, total: 3, target: 3, done: true, winners: [2], ends_at: '2026-10-19T00:00:00Z'},
    {id: 3, name: 'Nico seul', shared: false, members: [1], progress: {}, total: 0, target: 3, done: false, winners: [], ends_at: '2026-10-25T00:00:00Z'},
  ]}}}};
const progress = boardData(withProgress, {members: [2, 3]}, now);
const elenaProgress = progress.members.find(m => m.id === 2);
assert.deepEqual(elenaProgress.rank, {name: 'Hop Hop', icon: '🐸', level: 2, from: 100, next: {name: 'Super Hop', icon: '🦘', points: 300},
  stars: 0, points: 140, starAt: 0});
assert.equal(elenaProgress.earned, 140);
assert.deepEqual(elenaProgress.quests, [quest]);
assert.equal(progress.members.find(m => m.id === 3).rank, null);
assert.deepEqual(progress.challenges.map(c => c.id), [1], 'ended challenges and other members’ ones are left out');
