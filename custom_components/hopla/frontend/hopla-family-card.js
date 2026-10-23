// A family chore board: a podium of members' points, today's tasks with a
// photo button per member to mark who did it, what is already done, and the
// rewards each member can take.
// HA starts extra modules alongside its app bundle, which replaces both the
// custom-element registry and HTMLElement with its scoped-registry polyfill.
// Wait before defining classes so they use the final registry and base class.
await customElements.whenDefined('home-assistant');

const {translator, browserLanguage, reloadIfOutdated} = await import(new URL(`./hopla-i18n.js${new URL(import.meta.url).search}`, import.meta.url));
const KEYS = {allDone: 'all_done', noTasks: 'no_tasks', noMembers: 'no_members'};

const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function labelNames(value) {
  const labels = Array.isArray(value) ? value : typeof value === 'string' ? value.split(',') : [];
  return labels.map(label => typeof label === 'string' ? label : label?.name)
    .filter(name => typeof name === 'string' && name.trim()).map(name => name.trim().toLowerCase());
}

function isHopla(hass, id) {
  const platform = hass.entities?.[id]?.platform;
  return platform === undefined || platform === 'hopla';
}

const sameDay = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

// Only the drawn badges the integration ships, from hopla-1 to hopla-7.
const rankImage = image => /^hopla-[1-7]$/.test(image || '') ? image : null;
const badgeUrl = image => new URL(`./ranks/${image}.svg${new URL(import.meta.url).search}`, import.meta.url);

// The podium ranks the points earned since the start: spending on a reward
// does not make a child drop. The balance left to spend is the fallback.
const podiumScore = member => member.earned ?? member.points;

// Members on the podium: one step per member up to three, ties share a step
// and leave the lower steps empty.
export function podium(members) {
  const scores = [...new Set(members.map(podiumScore))].sort((a, b) => b - a);
  return [0, 1, 2].slice(0, Math.min(3, members.length))
    .map(rank => scores[rank] === undefined ? [] : members.filter(m => podiumScore(m) === scores[rank]));
}

const sameName = name => String(name ?? '').trim().toLowerCase();

// A task done several times a day has slots. Between two refreshes, the state
// that only depends on the time moves on: upcoming, open now, then missed once
// closed. Done and waiting slots keep theirs.
export function liveSlot(slot, now = new Date()) {
  if (!['upcoming', 'open', 'missed'].includes(slot.state)) return slot;
  const state = now < new Date(slot.opens_at) ? 'upcoming' : now < new Date(slot.closes_at) ? 'open' : 'missed';
  return {...slot, state};
}

// Today's slots of a task, as of now; another day's (a board left open
// overnight) wait for the next refresh.
export function todaySlots(slots, now = new Date()) {
  return (Array.isArray(slots) ? slots : []).filter(slot => slot.at && sameDay(new Date(slot.at), now)).map(slot => liveSlot(slot, now));
}

const slotNow = (slot, now = new Date()) => new Date(slot.opens_at) <= now && now < new Date(slot.closes_at);

// A task where the first one to do it does it for all has one set of slots for
// every child: a slot another child ticked is theirs, not this child's.
export function memberSlots(task, member) {
  if (!task.together) return task.slots;
  return task.slots.map(slot => ['done', 'pending'].includes(slot.state) && slot.completed_by != null && slot.completed_by !== member.id
    ? {...slot, state: 'taken'} : slot);
}

// One row per task name, so a task created once per child reads as one task:
// each child's photo completes their own copy, and a child who already did it
// today gets a check instead.
export function taskRows(tasks, done, members) {
  const rows = [];
  for (const task of tasks) {
    let row = rows.find(r => r.key === sameName(task.name));
    if (!row) rows.push(row = {key: sameName(task.name), name: task.name, points: task.points, due: task.due, tasks: [], slots: []});
    row.tasks.push(task);
    if (task.due && (!row.due || task.due < row.due)) row.due = task.due;
    if (task.slots?.length) {
      // Several times a day: each child's copy shows its slots on a ring.
      row.slotted = true;
      row.columns ??= task.slots;
      for (const member of task.members) {
        if (!row.slots.some(slot => slot.member.id === member.id)) row.slots.push({member, task, state: 'slots', slots: memberSlots(task, member)});
      }
      continue;
    }
    if (task.pending) {
      if (task.completedBy) row.slots.push({member: task.completedBy, task, state: 'pending'});
      else row.unknownPending = task;
    } else {
      for (const member of task.members) {
        if (!row.slots.some(slot => slot.member.id === member.id)) row.slots.push({member, task, state: 'tap'});
      }
    }
  }
  for (const row of rows) {
    for (const item of done) {
      if (row.slotted) break;
      if (sameName(item.name) === row.key && !row.slots.some(slot => slot.member.id === item.member.id)) {
        row.slots.push({member: item.member, state: 'done'});
      }
    }
    const order = member => { const i = members.findIndex(m => m.id === member.id); return i < 0 ? Infinity : i; };
    row.slots.sort((a, b) => order(a.member) - order(b.member));
    row.pending = row.tasks.some(task => task.pending);
  }
  return rows.sort((a, b) => (a.due ?? Infinity) - (b.due ?? Infinity) || a.name.localeCompare(b.name));
}

// Tasks done today, one row per task name like the tasks to do: a task done by
// each child shows once, with every child who did it.
export function doneRows(done) {
  const rows = [];
  for (const item of done) {
    let row = rows.find(r => r.key === sameName(item.name));
    if (!row) rows.push(row = {key: sameName(item.name), name: String(item.name).trim(), points: item.points, items: []});
    if (!row.items.some(other => other.member.id === item.member.id)) row.items.push(item);
    row.points = Math.max(Number(row.points) || 0, Number(item.points) || 0);
  }
  return rows;
}

// How a task shared by several people works: a copy each (same name, one per
// child), the first one to do it does it for all, or one person at a time.
export function taskMode(tasks, name) {
  const same = tasks.filter(task => sameName(task.name) === sameName(name));
  if (same.length > 1) return 'each';
  if (same[0]?.together) return 'first';
  return same[0]?.assignees.length > 1 ? 'one' : '';
}

// What a member sees on a reward: available, missing points, or out of quota until a date.
export function rewardState(reward, member, now = new Date()) {
  const resetsAt = reward.quota_resets_at ? new Date(reward.quota_resets_at) : null;
  const used = resetsAt && resetsAt > now ? Number(reward.quota_used?.[member.id] ?? reward.quota_used?.[String(member.id)] ?? 0) : 0;
  if (reward.quota_count > 0 && used >= reward.quota_count) return {kind: 'quota', resetsAt};
  const missing = reward.points_cost - member.points;
  if (missing > 0) return {kind: 'points', missing};
  return {kind: 'available'};
}

// Who may approve and spend points here. Without parents chosen in the
// integration options, everyone may; otherwise a parent's own account may,
// and anyone else only while parent mode is open.
export function parentAccess(hass, now = new Date()) {
  const entry = Object.entries(hass.states).find(([id, state]) => id.startsWith('binary_sensor.')
    && isHopla(hass, id) && state.attributes.hopla_parent_mode);
  if (!entry || !entry[1].attributes.enabled) return {guarded: false, parent: true};
  const [entity, state] = entry;
  const a = state.attributes;
  const until = a.unlocked_until ? new Date(a.unlocked_until) : null;
  const unlocked = state.state === 'on' && until !== null && until > now;
  const account = (a.parent_users || []).includes(hass.user?.id);
  return {guarded: true, entity, entryId: a.config_entry_id, hasPin: a.has_pin === true,
    account, unlocked, until: unlocked ? until : null, parent: account || unlocked};
}

// Members come from the points sensors, tasks from the task sensors.
export function boardData(hass, config, now = new Date()) {
  const members = [];
  const tasks = [];
  const completers = new Map();
  let rewards = null;
  let requests = [];
  let presets = [];
  let presetsEntry = null;
  let surprise = null;
  let period = null;
  let challenges = [];
  let ladder = [];
  for (const [id, state] of Object.entries(hass.states)) {
    if (!id.startsWith('sensor.') || !isHopla(hass, id)) continue;
    const a = state.attributes;
    if (a.hopla_member_id !== undefined) {
      members.push({id: a.hopla_member_id, name: a.display_name || a.friendly_name, role: a.role, away: a.away === true,
        picture: a.entity_picture || null, points: Number(state.state) || 0, recent: a.recent_completions || [],
        streak: Number(a.streak) || 0, streakToday: a.streak_done_today === true,
        rank: a.rank ? {name: a.rank, icon: a.rank_icon || '', image: rankImage(a.rank_image), level: Number(a.rank_level) || 1, from: Number(a.rank_points) || 0,
          next: a.next_rank ? {name: a.next_rank, icon: a.next_rank_icon || '', image: rankImage(a.next_rank_image), points: Number(a.next_rank_points) || 0} : null,
          stars: Number(a.rank_stars) || 0, points: Number(a.rank_round_points ?? a.total_points) || 0,
          starAt: Number(a.next_star_points) || 0} : null,
        earned: Number(a.total_points) || 0, quests: Array.isArray(a.quests) ? a.quests : []});
    } else if (a.task_id !== undefined && a.is_active !== false) {
      // The state is the bare task name; friendly_name may carry the device name.
      tasks.push({id: a.task_id, entity: id, name: state.state || a.friendly_name, points: a.points,
        due: a.next_due_date ? new Date(a.next_due_date) : null, labels: labelNames(a.labels),
        assignees: a.assignee_ids || [], assignedTo: a.assigned_to_user_id ?? null,
        together: a.assign_strategy === 'together', pending: a.pending_approval === true, slots: a.slots_today || [],
        frequencyType: a.frequency_type});
    } else if (a.hopla_games) {
      surprise = a.surprise || null;
      period = a.bonus_period || null;
      challenges = Array.isArray(a.challenges) ? a.challenges : [];
      ladder = Array.isArray(a.ranks) ? a.ranks.map(r => ({name: r.name || '', icon: r.icon || '', image: rankImage(r.image), points: Number(r.min_points) || 0})) : [];
    } else if (Array.isArray(a.points_presets)) {
      presets = a.points_presets;
      presetsEntry = a.config_entry_id || null;
    } else if (Array.isArray(a.rewards) && rewards === null) {
      rewards = a.rewards;
      requests = Array.isArray(a.requests) ? a.requests : [];
    } else if (Array.isArray(a.tasks) && a.tasks.every(t => 'completed_by' in t)) {
      for (const t of a.tasks) completers.set(t.task_id, t.completed_by);
    }
  }
  const chosen = config.members?.length ? config.members.map(Number) : null;
  const shown = chosen ? chosen.map(id => members.find(m => m.id === id)).filter(Boolean) : members;
  const wanted = (config.labels || []).map(label => label.trim().toLowerCase()).filter(Boolean);
  const labelled = labels => !wanted.length || labelNames(labels).some(label => wanted.includes(label));
  const endOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 23, 59, 59, 999);
  // Once its last slot of the day is ticked, a task is due tomorrow, but it
  // stays on today's board while one of its slots, or one of another child's
  // copy, is still to come or waits for a parent. A slot missed earlier no
  // longer keeps it: the day is over for that task.
  const busy = new Set(tasks.filter(task => todaySlots(task.slots, now).some(slot => ['upcoming', 'open', 'pending'].includes(slot.state)))
    .map(task => sameName(task.name)));
  const slottedToday = task => todaySlots(task.slots, now).length > 0 && busy.has(sameName(task.name));
  // A task started from outside (Home Assistant) waits, hidden, until it is
  // given a date; other tasks without a date can be done any day.
  const visible = tasks.filter(task => labelled(task.labels)
    && !(task.frequencyType === 'trigger' && !task.due)
    && (config.due !== 'today' || !task.due || task.due <= endOfDay || slottedToday(task)))
    .map(task => {
      // The heads of who has the task now: its assignee, or all of them for a
      // task for everyone together (or anyone's, with nobody chosen).
      const holders = !task.together && task.assignedTo != null ? [task.assignedTo] : task.assignees;
      // A child who is away does not have it: her tasks wait for her return.
      const candidates = (holders.length ? shown.filter(m => holders.includes(m.id)) : shown).filter(m => !m.away);
      // Every child's copy of the surprise task, same name, is worth the bonus.
      const isSurprise = surprise && (surprise.task_id === task.id || (surprise.task_ids || []).includes(task.id)
        || sameName(surprise.task_name) === sameName(task.name));
      const slots = todaySlots(task.slots, now);
      return {...task, slots, members: candidates, surprise: isSurprise ? surprise.points : 0,
        completedBy: task.pending && !slots.length ? shown.find(m => m.id === completers.get(task.id)) || null : null};
    })
    .filter(task => task.members.length || task.pending)
    .sort((a, b) => (a.due ?? Infinity) - (b.due ?? Infinity) || a.name.localeCompare(b.name));
  const withMode = rows => rows.map(row => ({...row, mode: taskMode(tasks, row.name)}));
  const done = shown.flatMap(member => member.recent
    .filter(item => item.completed_at && sameDay(new Date(item.completed_at), now) && labelled(item.labels))
    .map(item => ({...item, member})))
    .sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at));
  return {members: shown, tasks: visible, rows: withMode(taskRows(visible, done, shown)), done, doneRows: withMode(doneRows(done)), rewards: rewards || [], requests,
    presets, presetsEntry, surprise, period, ladder,
    // Running challenges, and finished ones until their end date, for the members shown.
    challenges: challenges.filter(c => new Date(c.ends_at) > now && c.members.some(id => shown.some(m => m.id === id)))};
}

const icon = {
  star: '<path d="M12 2l3 6.5 7 .8-5.2 4.8 1.4 7-6.2-3.6-6.2 3.6 1.4-7L2 9.3l7-.8z" fill="currentColor"/>',
  crown: '<path d="M3 19h18l1.5-11-5.5 4.5L12 5l-5 7.5L1.5 8z" fill="#f5b400" stroke="#d99a00" stroke-width="1.2" stroke-linejoin="round"/>',
  todo: '<path d="M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  check: '<path d="M20 6L9 17l-5-5" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>',
  gift: '<path d="M4 11h16v10H4zM3 7h18v4H3zM12 7v14M12 7c-1-3-5-4-5-1.5S10 7 12 7zm0 0c1-3 5-4 5-1.5S14 7 12 7z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="2" fill="currentColor"/><path d="M8 11V8a4 4 0 0 1 8 0v3" fill="none" stroke="currentColor" stroke-width="2.6"/>',
  clock: '<circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2.6"/><path d="M12 7.5V12l3 2" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>',
  plusminus: '<path d="M8 3v8M4 7h8M13 17h8M17 2L7 22" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>',
  flame: '<path d="M12 2c1 4 6 6 6 12a6 6 0 0 1-12 0c0-3 2-5 3-6 0 2 1 3 2 3 0-4-1-6 1-9z" fill="currentColor"/>',
  sparkle: '<path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7zM19 15l.9 2.6 2.6.9-2.6.9L19 22l-.9-2.6-2.6-.9 2.6-.9z" fill="currentColor"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z" fill="currentColor"/>',
  people: '<path d="M16 17v2H2v-2s0-4 7-4 7 4 7 4m-3.5-9.5A3.5 3.5 0 1 0 9 11a3.5 3.5 0 0 0 3.5-3.5m3.44 5.5A5.3 5.3 0 0 1 18 17v2h4v-2s0-3.63-6.06-4M15 4a3.4 3.4 0 0 0-1.93.59 5 5 0 0 1 0 5.82A3.4 3.4 0 0 0 15 11a3.5 3.5 0 0 0 0-7z" fill="currentColor"/>',
  person: '<path d="M12 4a4 4 0 1 1 0 8 4 4 0 0 1 0-8m0 10c4.42 0 8 1.79 8 4v2H4v-2c0-2.21 3.58-4 8-4z" fill="currentColor"/>',
  trophy: '<path d="M7 3h10v5a5 5 0 0 1-10 0zM7 5H3v2a4 4 0 0 0 4 4M17 5h4v2a4 4 0 0 1-4 4M12 13v4M8 21h8M9 17h6v4H9z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>',
  hourglass: '<path d="M6 2h12M6 22h12M7 2v3.5a3 3 0 0 0 .9 2.1L12 12l4.1-4.4A3 3 0 0 0 17 5.5V2M7 22v-3.5a3 3 0 0 1 .9-2.1L12 12l4.1 4.4a3 3 0 0 1 .9 2.1V22" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
  replay: '<path d="M4 12a8 8 0 1 0 2.3-5.6M4 4v4h4" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>',
  suitcase: '<path d="M9 6V4.5A1.5 1.5 0 0 1 10.5 3h3A1.5 1.5 0 0 1 15 4.5V6M5 6h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2zM8 6v14M16 6v14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/>',
  cross: '<path d="M6 6l12 12M18 6L6 18" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>',
  unlock: '<rect x="5" y="11" width="14" height="10" rx="2" fill="currentColor"/><path d="M8 11V8a4 4 0 0 1 7.5-2" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>',
  back: '<path d="M21 6H8l-6 6 6 6h13zM12 9l6 6M18 9l-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>',
};
const RESPONDING = ['complete_task', 'redeem_reward', 'unlock_parent_mode', 'adjust_points'];
const svg = (name, size, label) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" ${label ? `role="img" aria-label="${escape(label)}"` : 'aria-hidden="true"'}>${icon[name]}</svg>`;

class HoplaFamilyCard extends HTMLElement {
  static getConfigElement() { return document.createElement('hopla-family-card-editor'); }
  static getStubConfig(hass) {
    const {members} = boardData(hass, {});
    const children = members.filter(m => m.role && m.role !== 'admin');
    return {due: 'today', members: (children.length ? children : members).map(m => m.id)};
  }
  constructor() {
    super();
    this.attachShadow({mode: 'open'});
    this._busy = new Map();   // task id or reward key -> member id being sent
    this._flash = new Map();  // task id -> message shown briefly after a tap
    this._armed = null;       // reward key waiting for a confirming second tap
    this._pin = null;         // digits typed on the parent code pad while it is open
    this.shadowRoot.addEventListener('click', event => this.onClick(event));
  }
  connectedCallback() {
    // Quota countdowns move on even when no sensor changes.
    this._timer = setInterval(() => this.render(), 60000);
  }
  disconnectedCallback() { clearInterval(this._timer); clearTimeout(this._lockTimer); }
  setConfig(config) {
    if (config.due && !['today', 'all'].includes(config.due)) throw new Error(this.t('errors.due'));
    if (config.members !== undefined && !Array.isArray(config.members)) throw new Error(this.t('errors.members'));
    if (config.labels !== undefined && !Array.isArray(config.labels)) throw new Error(this.t('errors.labels'));
    this._config = {due: 'today', show_points: true, show_todo: true, show_done: true, show_rewards: true, show_approval: false, allow_redeem: false, show_bonus: true, show_goals: true, ...config};
    this.render();
  }
  set hass(hass) {
    if (reloadIfOutdated(hass)) return;
    const previous = this._hass;
    this._hass = hass;
    const relevant = id => (id.startsWith('sensor.') || id.startsWith('binary_sensor.')) && isHopla(hass, id);
    if (previous && Object.keys(hass.states).every(id => !relevant(id) || previous.states[id] === hass.states[id])
      && Object.keys(previous.states).every(id => !relevant(id) || hass.states[id])
      && previous.locale?.language === hass.locale?.language) return;
    this.render();
  }
  getCardSize() { return 4 + (this._data?.rows.length || 0) + (this._data?.doneRows.length || 0) + (this._data?.rewards.length || 0); }
  getGridOptions() { return {columns: 12, min_columns: 6}; }
  t(key, values = {}) {
    const language = this._hass?.locale?.language || this._hass?.language || browserLanguage();
    if (this._language !== language) { this._language = language; this._t = translator(language, () => this.render()); }
    return this._t(key.includes('.') ? key : `family.${KEYS[key] || key}`, values);
  }
  duration(until) {
    const minutes = Math.max(1, Math.ceil((until - new Date()) / 60000));
    if (minutes < 60) return this.t('minutes', {n: minutes});
    if (minutes < 48 * 60) return this.t('hours', {n: Math.ceil(minutes / 60)});
    return this.t('days', {n: Math.ceil(minutes / 1440)});
  }
  async call(service, data, key, memberId) {
    this._busy.set(key, memberId); this._error = ''; this.render();
    try {
      const result = await this._hass.callService('hopla', service, data, undefined, false, RESPONDING.includes(service));
      return result?.response ?? {};
    } catch (err) {
      this._error = err?.message || String(err);
      return null;
    } finally {
      this._busy.delete(key); this.render();
    }
  }
  async onClick(event) {
    if (event.target.classList?.contains('rank-scrim')) { this._rankFor = null; this.render(); return; }
    const button = event.target.closest('button[data-action]');
    if (!button || button.disabled) return;
    const {action, task, member, reward, request, digit, preset, slot, tasks} = button.dataset;
    if (action === 'parent') {
      const access = parentAccess(this._hass);
      if (access.unlocked) await this.call('lock_parent_mode', {config_entry_id: access.entryId}, 'parent', null);
      else { this._pin = ''; this._pinError = ''; this.render(); }
      return;
    }
    // The rank details only show things: no parent code needed.
    if (action === 'rank') { this._rankFor = Number(member); this.render(); return; }
    if (action === 'rank-close') { this._rankFor = null; this.render(); return; }
    if (action === 'pin-cancel') { this._pin = null; this.render(); return; }
    if (action === 'pin-back') { this._pin = this._pin.slice(0, -1); this.render(); return; }
    if (action === 'pin-digit') {
      if (this._pin === null || this._pin.length >= 4) return;
      this._pin += digit; this._pinError = ''; this.render();
      if (this._pin.length < 4) return;
      const pin = this._pin;
      this._error = '';
      const response = await this.call('unlock_parent_mode', {pin, config_entry_id: parentAccess(this._hass).entryId}, 'parent', null);
      if (response) this._pin = null;
      else { this._pin = ''; this._pinError = this._error; this._error = ''; }
      this.render();
      return;
    }
    if (action === 'approve-request' || action === 'reject-request') {
      const key = `request-${request}`;
      await this.call(action === 'approve-request' ? 'approve_reward' : 'reject_reward', {redemption_id: Number(request)}, key, null);
      return;
    }
    if (action === 'complete') {
      const taskId = Number(task);
      if (this._busy.has(taskId)) return;
      const response = await this.call('complete_task', {task_id: taskId, completed_by: Number(member)}, taskId, Number(member));
      if (response) this.flash(taskId, response.pending_approval ? this.t('submitted') : this.t('bravo'));
    } else if (action === 'approve' || action === 'reject') {
      await this.call(`${action}_task`, {task_id: Number(task)}, Number(task), null);
    } else if (action === 'slot-approve' || action === 'slot-reject') {
      await this.call(action === 'slot-approve' ? 'approve_task' : 'reject_task', {task_id: Number(task), slot: Number(slot)}, Number(task), null);
    } else if (action === 'slot-catchup') {
      await this.call('catch_up_slot', {task_id: Number(task), slot: Number(slot), completed_by: Number(member)}, Number(task), Number(member));
    } else if (action === 'approve-all') {
      // Each child's copy: approving the task approves its waiting slots.
      for (const id of tasks.split(',').map(Number)) {
        if (await this.call('approve_task', {task_id: id}, id, null) === null) break;
      }
    } else if (action === 'bonus') {
      // Two touches, like redeeming: a parent's tap on the wrong face costs a child points.
      const key = `preset-${preset}-${member}`;
      if (this._armed !== key) { this._armed = key; this.render(); setTimeout(() => { if (this._armed === key) { this._armed = null; this.render(); } }, 4000); return; }
      this._armed = null;
      const response = await this.call('adjust_points', {user_id: Number(member), preset_id: Number(preset),
        ...(this._data.presetsEntry ? {config_entry_id: this._data.presetsEntry} : {})}, key, Number(member));
      if (response) {
        const name = this._data.members.find(m => m.id === Number(member))?.name || '';
        this.flash(key, this.t(response.action === 'penalty' ? 'penalty_done' : 'bonus_done', {count: response.points, name}));
      }
    } else if (action === 'redeem') {
      const key = `reward-${reward}-${member}`;
      if (this._armed !== key) { this._armed = key; this.render(); setTimeout(() => { if (this._armed === key) { this._armed = null; this.render(); } }, 4000); return; }
      this._armed = null;
      const response = await this.call('redeem_reward', {reward_id: Number(reward), user_id: Number(member)}, key, Number(member));
      if (response) this.flash(key, response.pending ? this.t('requested') : this.t('bravo'));
    }
  }
  flash(key, message) {
    this._flash.set(key, message); this.render();
    setTimeout(() => { this._flash.delete(key); this.render(); }, 2500);
  }
  face(member, size, extra = '') {
    const initial = escape((member.name || '?').charAt(0).toUpperCase());
    return member.picture
      ? `<img class="face${extra}" style="width:${size}px;height:${size}px" src="${escape(member.picture)}" alt="">`
      : `<span class="face initial${extra}" style="width:${size}px;height:${size}px;font-size:${Math.round(size / 2.4)}px">${initial}</span>`;
  }
  badge(kind, iconName, text = '') {
    return `<span class="badge ${kind}${text ? ' wide' : ''}">${svg(iconName, 11)}${escape(text)}</span>`;
  }
  points(value, muted = false, cost = false) {
    return value ? `<span class="pts${muted ? ' muted' : ''}${cost ? ' cost' : ''}">${svg('star', 14)}${cost ? '' : '+'}${value}</span>` : '';
  }
  header(iconName, kind, title, count) {
    return `<div class="head ${kind}"><span class="head-icon ${kind}">${svg(iconName, 18)}</span><h2>${escape(title)}</h2><span class="count ${kind}">${count}</span></div>`;
  }
  renderPodium(members) {
    const steps = podium(members);
    const step = (group, rank) => {
      const size = rank === 0 ? 76 : 60;
      const faces = group.length
        ? group.map(m => `<div class="podium-member">${rank === 0 && podiumScore(m) > 0 ? `<span class="crown">${svg('crown', 30)}</span>` : ''}<span class="podium-face">${this.face(m, size, `${rank === 0 && podiumScore(m) > 0 ? ' leader' : ''}${m.away ? ' away' : ''}`)}${this.coin(m)}${this.away(m)}</span><div class="podium-name">${escape(m.name)}${this.streak(m)}</div>${this.rank(m)}</div>`).join('')
        : `<div class="podium-member"><span class="face empty" style="width:${size}px;height:${size}px"></span><div class="podium-name">&nbsp;</div></div>`;
      const score = group.length ? `<span class="score">${podiumScore(group[0])}</span><span class="unit">${escape(this.t('earned', {count: podiumScore(group[0])}))}</span>` : '';
      return `<div class="podium-col rank${rank + 1}"><div class="podium-faces">${faces}</div><div class="step">${score}</div></div>`;
    };
    const order = [[0], [1, 0], [1, 0, 2]][steps.length - 1];
    return `<div class="podium steps${steps.length}">${order.map(rank => step(steps[rank], rank)).join('')}</div>`;
  }
  // The points left to spend, as a pastille on the face.
  coin(member) {
    const label = this.t('to_spend', {count: member.points});
    return `<span class="coin" title="${escape(label)}" aria-label="${escape(label)}">${svg('star', 12)}${member.points}</span>`;
  }
  // Away, such as at the other parent's home: a grey suitcase on the face.
  away(member) {
    if (!member.away) return '';
    const label = this.t('away', {name: member.name});
    return `<span class="away-pin" title="${escape(label)}" aria-label="${escape(label)}">${svg('suitcase', 14)}</span>`;
  }
  streak(member) {
    if (!member.streak) return '';
    const label = this.t('streak', {count: member.streak});
    return `<span class="streak${member.streakToday ? '' : ' at-risk'}" title="${escape(member.streakToday ? label : `${label} · ${this.t('streak_at_risk')}`)}">${svg('flame', 14)}${member.streak}</span>`;
  }
  // A drawn badge, or the rank's emoji when the circle chose its own ranks.
  rankBadge(rank, size, extra = '') {
    return rank.image ? `<img class="rank-img${extra}" style="width:${size}px;height:${size}px" src="${badgeUrl(rank.image)}" alt="">`
      : `<span class="rank-img${extra}" style="width:${size}px;height:${size}px;font-size:${Math.round(size * .7)}px">${escape(rank.icon)}</span>`;
  }
  rankProgress(rank) {
    // Past the last rank, the bar leads to the next prestige star.
    const target = rank.next ? rank.next.points : rank.starAt;
    const pct = target ? Math.min(100, Math.round(100 * (rank.points - rank.from) / Math.max(1, target - rank.from))) : 100;
    return {target, pct, left: target ? Math.max(0, target - rank.points) : 0};
  }
  rankStars(rank) {
    return !rank.stars ? '' : rank.stars <= 3 ? '⭐'.repeat(rank.stars) : `⭐×${rank.stars}`;
  }
  rank(member) {
    if (!member.rank) return '';
    const {rank} = member;
    const {pct, left} = this.rankProgress(rank);
    const title = rank.next ? this.t('rank_next', {count: left, name: rank.next.name})
      : rank.starAt ? this.t('rank_star', {count: left}) : this.t('rank_top');
    const next = rank.next ? this.rankBadge(rank.next, 22, ' next') : rank.starAt ? '<span class="rank-img next star">⭐</span>' : '';
    const label = `${this.rankStars(rank)} ${rank.name}`.trim();
    return `<button class="rank" data-action="rank" data-member="${member.id}" title="${escape(title)}" aria-label="${escape(`${this.t('rank_open', {name: member.name})} · ${title}`)}">
      <span class="rank-chip">${rank.image || rank.icon ? this.rankBadge(rank, 30) : ''}<span>${escape(label)}</span></span>
      <span class="rank-prog"><span class="bar"><i style="width:${pct}%"></i></span>${next}</span></button>`;
  }
  // The rank details, over the card: where the member stands and every rank.
  renderRankDetails(members, ladder) {
    const member = this._rankFor === null || this._rankFor === undefined ? null : members.find(m => m.id === this._rankFor && m.rank);
    if (!member) return '';
    const {rank} = member;
    const {target, pct, left} = this.rankProgress(rank);
    const token = '\u0001';
    const bold = (text, name) => escape(text).replace(token, `<b>${escape(name)}</b>`);
    const goal = rank.next ? `<div class="rank-goal">${this.rankBadge(rank.next, 40, ' next')}<span>${bold(this.t('rank_goal', {count: left, name: token}), rank.next.name)}</span></div>`
      : rank.starAt ? `<div class="rank-goal"><span class="rank-img next star" style="width:40px;height:40px;font-size:28px">⭐</span><span>${escape(this.t('rank_star', {count: left}))}</span></div>`
      : `<div class="rank-goal"><span>${escape(this.t('rank_top'))}</span></div>`;
    const steps = ladder.map((item, i) => {
      const level = i + 1;
      const state = level < rank.level ? 'got' : level === rank.level ? 'here' : 'later';
      const mark = state === 'got' ? `${svg('check', 12)}${escape(this.t('rank_got'))}` : state === 'here' ? escape(this.t('rank_here')) : escape(this.t('common.pts', {count: item.points}));
      return `<li class="${state}">${this.rankBadge(item, 34, state === 'later' ? ' next' : '')}<span>${escape(item.name)}</span><span class="mark">${mark}</span></li>`;
    }).join('');
    return `<div class="rank-scrim"><div class="rank-dialog" role="dialog" aria-label="${escape(this.t('rank_open', {name: member.name}))}">
      <div class="rank-head">${this.face(member, 28)}<span>${escape(member.name)}</span>
        <button class="close" data-action="rank-close" aria-label="${escape(this.t('close'))}">${svg('cross', 16)}</button></div>
      <div class="rank-hero">${this.rankBadge(rank, 84)}<div>
        <div class="rank-level">${escape(ladder.length ? this.t('rank_level', {level: rank.level, total: ladder.length}) : this.t('rank_level_alone', {level: rank.level}))}</div>
        <div class="rank-name">${escape(rank.name)}</div>
        <div class="rank-sub">${escape([rank.stars ? `${this.rankStars(rank)} ${this.t('rank_stars', {count: rank.stars})}` : '', this.t('rank_earned', {count: member.earned})].filter(Boolean).join(' · '))}</div></div></div>
      <div class="rank-big"><span class="bar"><i style="width:${pct}%"></i></span>
        <div class="rank-nums"><span>${rank.from}</span><span>${target ? `<b>${rank.points}</b> / ${escape(this.t('common.pts', {count: target}))}` : `<b>${escape(this.t('common.pts', {count: rank.points}))}</b>`}</span></div></div>
      ${goal}
      ${steps ? `<ul class="rank-ladder">${steps}</ul>` : ''}
      <div class="rank-foot">${escape(this.t('rank_explain'))}</div>
    </div></div>`;
  }
  gauge(value, target, done) {
    const pct = done ? 100 : Math.min(100, Math.round(100 * value / Math.max(1, target)));
    return `<span class="gauge${done ? ' full' : ''}"><i style="width:${pct}%"></i></span><span class="gauge-n">${Math.min(value, target)}/${target}</span>`;
  }
  renderChallenges(challenges, members) {
    const byId = new Map(members.map(m => [m.id, m]));
    return challenges.map(c => {
      const reward = c.reward_text ? `<div class="goal-reward">${svg('gift', 14)}${escape(this.t(c.done ? 'goal_won' : 'goal_to_win', {reward: c.reward_text}))}</div>` : '';
      const end = c.done ? '' : `<span class="period-end">${escape(this.t('period_left', {time: this.duration(new Date(c.ends_at))}))}</span>`;
      const lines = c.shared
        ? `<div class="goal-line"><span class="goal-faces">${c.members.map(id => byId.get(id)).filter(Boolean).map(m => this.face(m, 26)).join('')}</span>${this.gauge(c.total, c.target, c.done)}</div>`
        : c.members.map(id => byId.get(id)).filter(Boolean).map(m => `<div class="goal-line">${this.face(m, 26)}${this.gauge(c.progress[m.id] || 0, c.target, c.winners.includes(m.id))}</div>`).join('');
      return `<div class="goal${c.done ? ' done' : ''}"><div class="goal-head">${svg('trophy', 18)}<b>${escape(c.name)}</b>${c.shared ? `<span class="goal-tag">${escape(this.t('goal_family'))}</span>` : ''}${end}</div>${lines}${reward}</div>`;
    }).join('');
  }
  renderQuests(members) {
    const rows = members.flatMap(m => m.quests.map(q => ({...q, member: m})));
    if (!rows.length) return '';
    return `<section>${this.header('flag', 'quest', this.t('quests'), rows.filter(q => !q.done).length)}${rows.map(q =>
      `<div class="row quest${q.done ? ' is-done' : ''}">${this.face(q.member, 32)}<span class="name">${escape(q.name)}</span>${this.gauge(q.progress, q.target, q.done)}${q.reward ? `<span class="pts bonus">+${q.reward}</span>` : ''}</div>`).join('')}</section>`;
  }
  renderPeriod(period) {
    if (!period) return '';
    const end = new Date(period.ends_at);
    return `<div class="period">${svg('bolt', 18)}<span><b>${escape(this.t('period', {multiplier: period.multiplier}))}</b> · ${escape(period.name)}</span>
      <span class="period-end">${escape(this.t('period_left', {time: this.duration(end)}))}</span></div>`;
  }
  // 7h30 in French, 7:30 otherwise.
  slotTime(time) {
    const [hour, minute] = String(time || '').split(':');
    if (!minute) return time || '';
    return this.t('slot_time', {h: Number(hour), hh: hour, m: minute});
  }
  slotLabel(slot) {
    return [slot.name, this.slotTime(slot.time)].filter(Boolean).join(' ');
  }
  // The ring round a child's face: one arc per slot, coloured by its state.
  ring(slots) {
    const colors = {done: '#0EA5E9', pending: '#F59E0B', missed: '#E07A2E', open: '#BAE6FD', upcoming: '#D9D9D9', taken: '#EEEEEE'};
    const circle = 2 * Math.PI * 29;
    const part = circle / slots.length;
    const gap = slots.length > 1 ? 8.7 : 0;
    const arcs = slots.map((slot, i) => `<circle cx="32" cy="32" r="29" stroke="${colors[slot.state] || colors.upcoming}"
      stroke-dasharray="${(part - gap).toFixed(1)} ${(circle - part + gap).toFixed(1)}" stroke-dashoffset="${(-(i * part + gap / 2)).toFixed(1)}"/>`).join('');
    return `<svg class="ring" width="64" height="64" viewBox="0 0 64 64" aria-hidden="true"><g transform="rotate(-90 32 32)" fill="none" stroke-width="5" stroke-linecap="${gap ? 'round' : 'butt'}">${arcs}</g></svg>`;
  }
  // A task done several times a day: a ring per child to tick the slot open
  // now, or, for a parent with slots to approve or catch up, a grid of
  // children by slots.
  renderSlotted(row) {
    const now = new Date();
    const busy = row.tasks.find(task => this._busy.has(task.id));
    const all = row.slots.flatMap(entry => entry.slots);
    const pendingCount = all.filter(slot => slot.state === 'pending').length;
    const missedCount = all.filter(slot => slot.state === 'missed').length;
    const surprise = row.tasks.find(task => task.surprise);
    const sparkle = surprise ? `<span class="surprise" title="${escape(this.t('surprise', {n: surprise.surprise}))}">${svg('sparkle', 14)}+${surprise.surprise}</span>` : '';
    const parent = this._config.show_approval && this._access.parent;
    if (parent && (pendingCount || missedCount)) {
      const head = row.columns.map(c => `<span class="gh${slotNow(c, now) ? ' now' : ''}">${escape(c.name || this.slotTime(c.time))}${c.name ? `<small>${escape(this.slotTime(c.time))}</small>` : ''}</span>`).join('');
      const lines = row.slots.map(({member: m, task, slots}) => {
        const cells = row.columns.map(column => {
          const slot = slots.find(s => s.index === column.index);
          if (!slot) return '<span></span>';
          const label = `${m.name} · ${this.slotLabel(slot)}`;
          const data = `data-task="${task.id}" data-slot="${slot.index}" data-member="${m.id}" ${busy ? 'disabled' : ''}`;
          if (slot.state === 'pending') return `<span class="capsule">
            <button class="cap ok" data-action="slot-approve" ${data} aria-label="${escape(this.t('common.on_task', {action: this.t('approve'), task: label}))}">${svg('check', 20)}</button>
            <button class="cap no" data-action="slot-reject" ${data} aria-label="${escape(this.t('common.on_task', {action: this.t('reject'), task: label}))}">${svg('cross', 18)}</button></span>`;
          if (slot.state === 'missed') return `<button class="catchup" data-action="slot-catchup" ${data} aria-label="${escape(this.t('common.on_task', {action: this.t('catch_up'), task: label}))}">${svg('replay', 15)}${escape(this.t('catch_up'))}</button>`;
          if (slot.state === 'taken') return `<span class="gdot taken" role="img" aria-label="${escape(this.t('common.on_task', {action: label, task: this.t('slot_state.taken')}))}"></span>`;
          if (slot.state === 'done') return `<span class="gdot done" role="img" aria-label="${escape(this.t('common.on_task', {action: label, task: this.t('slot_state.done')}))}">${svg('check', 16)}</span>`;
          if (slot.state === 'open') return `<button class="gdot open" data-action="slot-catchup" ${data} aria-label="${escape(this.t('common.on_task', {action: this.t('slot_tick'), task: label}))}">${svg('check', 16)}</button>`;
          return `<span class="gdot later" role="img" aria-label="${escape(this.t('common.on_task', {action: label, task: this.t('slot_state.upcoming')}))}"></span>`;
        }).join('');
        return `<span class="gname">${this.face(m, 30)}<span>${escape(m.name)}</span></span>${cells}`;
      }).join('');
      const summary = [pendingCount ? this.t('to_approve', {count: pendingCount}) : '', missedCount ? this.t('missed_slots', {count: missedCount}) : ''].filter(Boolean).join(' · ');
      const waiting = [...new Set(row.slots.filter(entry => entry.slots.some(slot => slot.state === 'pending')).map(entry => entry.task.id))];
      const approveAll = pendingCount > 1 ? `<button class="approve-all" data-action="approve-all" data-tasks="${waiting.join(',')}" ${busy ? 'disabled' : ''}>${svg('check', 16)}${escape(this.t('approve_all', {count: pendingCount}))}</button>` : '';
      return `<div class="row slotted open-grid"><div class="grid-top"><span class="name"><span>${escape(row.name)}</span>${this.mode(row)}</span>${this.points(row.points)}${sparkle}</div>
        <div class="grid" style="grid-template-columns: minmax(80px, 110px) repeat(${row.columns.length}, minmax(0, 1fr))"><span></span>${head}${lines}</div>
        <div class="gfoot"><span>${escape(summary)}</span>${approveAll}</div></div>`;
    }
    const flash = row.tasks.map(task => this._flash.get(task.id)).find(Boolean);
    const pills = row.columns.map(c => `<span class="slot-pill${slotNow(c, now) ? ' now' : ''}">${escape(this.slotLabel(c))}</span>`).join('');
    const right = flash ? `<span class="flash">${escape(flash)}</span>` : row.slots.map(({member: m, task, slots}) => {
      const open = slots.find(slot => slot.state === 'open');
      const waiting = slots.some(slot => slot.state === 'pending');
      const states = slots.map(slot => `${this.slotLabel(slot)} ${this.t(`slot_state.${slot.state}`)}`).join(', ');
      const label = open ? `${this.t('common.on_task', {action: m.name, task: this.t('slot_tick_named', {slot: open.name || this.slotTime(open.time)})})} · ${states}` : `${m.name} · ${states}`;
      return `<button class="ringbtn${busy && this._busy.get(busy.id) === m.id ? ' busy' : ''}" data-action="complete" data-task="${task.id}" data-member="${m.id}"
        ${open && !busy ? '' : 'disabled'} aria-label="${escape(label)}" title="${escape(label)}">${this.ring(slots)}<span class="ring-face">${this.face(m, 48)}</span>${waiting ? this.badge('amber', 'hourglass') : ''}</button>`;
    }).join('');
    return `<div class="row slotted${surprise ? ' is-surprise' : ''}"><span class="name"><span>${escape(row.name)}</span>${this.mode(row)}<span class="slot-pills">${pills}</span></span>${this.points(row.points)}${sparkle}<span class="faces">${right}</span></div>`;
  }
  // The mode of a task shared by several people, under its name.
  mode(row) {
    if (!row.mode) return '';
    const symbol = {each: 'people', first: 'bolt', one: 'person'}[row.mode];
    return `<span class="mode ${row.mode}">${svg(symbol, 14)}${escape(this.t(`common.mode_${row.mode}`))}</span>`;
  }
  renderTask(row) {
    if (row.slotted) return this.renderSlotted(row);
    const busy = row.tasks.find(task => this._busy.has(task.id));
    const flash = row.tasks.map(task => this._flash.get(task.id)).find(Boolean);
    let right;
    if (flash) right = `<span class="flash">${escape(flash)}</span>`;
    else {
      const approval = task => this._config.show_approval && this._access.parent ? `
        <button class="icon-btn ok" data-action="approve" data-task="${task.id}" ${busy ? 'disabled' : ''} aria-label="${escape(this.t('approve'))}">${svg('check', 18)}</button>
        <button class="icon-btn no" data-action="reject" data-task="${task.id}" ${busy ? 'disabled' : ''} aria-label="${escape(this.t('reject'))}">${svg('cross', 16)}</button>` : '';
      right = row.slots.map(({member: m, task, state}) => {
        if (state === 'pending') return `<span class="slot waiting" title="${escape(m.name)}">${this.face(m, 48)}${this.badge('wait', 'clock')}</span>${approval(task)}`;
        if (state === 'done') return `<span class="slot" title="${escape(m.name)}">${this.face(m, 48)}${this.badge('done', 'check')}</span>`;
        return `<button class="slot tap${busy && this._busy.get(busy.id) === m.id ? ' busy' : ''}" data-action="complete" data-task="${task.id}" data-member="${m.id}"
          ${busy ? 'disabled' : ''} aria-label="${escape(this.t('common.on_task', {action: m.name, task: row.name}))}">${this.face(m, 48)}</button>`;
      }).join('') + (row.unknownPending ? approval(row.unknownPending) : '');
    }
    const waiting = row.pending ? `<span class="hourglass">${svg('hourglass', 18, this.t('pending'))}</span>` : '';
    const surprise = row.tasks.find(task => task.surprise);
    const sparkle = surprise ? `<span class="surprise" title="${escape(this.t('surprise', {n: surprise.surprise}))}">${svg('sparkle', 14)}+${surprise.surprise}</span>` : '';
    return `<div class="row${row.pending ? ' is-pending' : ''}${surprise ? ' is-surprise' : ''}"><span class="name"><span>${escape(row.name)}</span>${this.mode(row)}</span>${this.points(row.points)}${sparkle}${waiting}<span class="faces">${right}</span></div>`;
  }
  renderDone(row) {
    const faces = row.items.map(item => `<span class="slot" title="${escape(item.member.name)}">${this.face(item.member, 40)}${this.badge('done', 'check')}</span>`).join('');
    return `<div class="row small"><span class="name muted"><span>${escape(row.name)}</span>${this.mode(row)}</span>${this.points(row.points, true)}<span class="faces">${faces}</span></div>`;
  }
  renderReward(reward, members, requests) {
    const period = reward.quota_count > 0 && reward.quota_period ? `<span class="sub">${escape(this.t(reward.quota_period, {n: reward.quota_count}))}</span>` : '';
    const slots = members.map(m => {
      const request = requests.find(item => item.reward_id === reward.id && item.user_id === m.id);
      if (request) {
        const busy = this._busy.has(`request-${request.redemption_id}`) ? 'disabled' : '';
        const buttons = this._access.parent ? `
          <button class="icon-btn ok" data-action="approve-request" data-request="${request.redemption_id}" ${busy} aria-label="${escape(this.t('common.on_task', {action: this.t('approve'), task: `${m.name} · ${reward.name}`}))}">${svg('check', 18)}</button>
          <button class="icon-btn no" data-action="reject-request" data-request="${request.redemption_id}" ${busy} aria-label="${escape(this.t('common.on_task', {action: this.t('reject'), task: `${m.name} · ${reward.name}`}))}">${svg('cross', 16)}</button>` : '';
        return `<span class="slot waiting" title="${escape(this.t('common.on_task', {action: m.name, task: this.t('request_pending')}))}">${this.face(m, 44)}${this.badge('wait', 'hourglass')}</span>${buttons}`;
      }
      const state = rewardState(reward, m);
      const key = `reward-${reward.id}-${m.id}`;
      if (state.kind === 'quota') {
        const time = state.resetsAt ? this.duration(state.resetsAt) : '';
        return `<span class="slot off" title="${escape(this.t('common.on_task', {action: m.name, task: this.t('quota', {time})}))}">${this.face(m, 44, ' grey')}${this.badge('gray', 'clock', time)}</span>`;
      }
      if (state.kind === 'points') {
        return `<span class="slot off" title="${escape(this.t('common.on_task', {action: m.name, task: this.t('missing', {n: state.missing})}))}">${this.face(m, 44, ' grey')}${this.badge('gray', 'lock', `−${state.missing}`)}</span>`;
      }
      const content = `${this.face(m, 44)}${this.badge('gift', 'gift')}`;
      return this._config.allow_redeem
        ? `<button class="slot tap${this._armed === key ? ' armed' : ''}" data-action="redeem" data-reward="${reward.id}" data-member="${m.id}" ${this._busy.has(key) ? 'disabled' : ''}
            aria-label="${escape(this.t('common.on_task', {action: m.name, task: `${this._armed === key ? this.t('confirm') : this.t('available')} ${reward.name}`}))}">${content}</button>`
        : `<span class="slot" title="${escape(m.name)}">${content}</span>`;
    }).join('');
    const flash = members.map(m => this._flash.get(`reward-${reward.id}-${m.id}`)).find(Boolean);
    const armed = flash ? `<span class="sub armed-text">${escape(flash)}</span>`
      : members.some(m => this._armed === `reward-${reward.id}-${m.id}`) ? `<span class="sub armed-text">${escape(this.t('confirm'))}</span>` : period;
    return `<div class="row"><span class="name"><span>${escape(reward.name)}</span>${armed}</span>${this.points(reward.points_cost, false, true)}<span class="faces">${slots}</span></div>`;
  }
  renderPreset(preset, members) {
    const bonus = preset.points > 0;
    const slots = members.map(m => {
      const key = `preset-${preset.id}-${m.id}`;
      const armed = this._armed === key;
      return `<button class="slot tap${armed ? ' armed' : ''}" data-action="bonus" data-preset="${preset.id}" data-member="${m.id}" ${this._busy.has(key) ? 'disabled' : ''}
        aria-label="${escape(this.t('common.on_task', {action: m.name, task: armed ? this.t('bonus_confirm') : preset.name}))}">${this.face(m, 44)}</button>`;
    }).join('');
    const flash = members.map(m => this._flash.get(`preset-${preset.id}-${m.id}`)).find(Boolean);
    const sub = flash ? `<span class="sub armed-text">${escape(flash)}</span>`
      : members.some(m => this._armed === `preset-${preset.id}-${m.id}`) ? `<span class="sub armed-text">${escape(this.t('bonus_confirm'))}</span>` : '';
    const amount = `<span class="pts ${bonus ? 'bonus' : 'penalty'}">${bonus ? '+' : '−'}${Math.abs(preset.points)}</span>`;
    return `<div class="row"><span class="name"><span>${escape(preset.name)}</span>${sub}</span>${amount}<span class="faces">${slots}</span></div>`;
  }
  renderParentButton() {
    const access = this._access;
    if (!access.guarded || access.account) return '';
    const label = access.unlocked ? this.t('parent_close', {time: this.duration(access.until)}) : this.t('parent_open');
    return `<button class="parent-btn${access.unlocked ? ' open' : ''}" data-action="parent" ${this._busy.has('parent') ? 'disabled' : ''}
      aria-label="${escape(label)}" title="${escape(label)}">${svg(access.unlocked ? 'unlock' : 'lock', 18)}${access.unlocked ? `<span>${escape(this.duration(access.until))}</span>` : ''}</button>`;
  }
  renderPinPad() {
    if (this._pin === null) return '';
    const busy = this._busy.has('parent') ? 'disabled' : '';
    const dots = [0, 1, 2, 3].map(i => `<span class="dot${i < this._pin.length ? ' full' : ''}"></span>`).join('');
    const keys = ['1', '2', '3', '4', '5', '6', '7', '8', '9'].map(d => `<button class="key" data-action="pin-digit" data-digit="${d}" ${busy}>${d}</button>`).join('');
    const message = this._pinError || (this._access.hasPin ? this.t('pin_prompt') : this.t('pin_missing'));
    return `<div class="pin-pad" role="dialog" aria-label="${escape(this.t('parent_open'))}">
      <div class="pin-title">${svg('lock', 18)}${escape(this.t('parent_mode'))}</div>
      <div class="dots" aria-hidden="true">${dots}</div>
      <div class="pin-message${this._pinError ? ' error-text' : ''}" role="status">${escape(message)}</div>
      <div class="keys">${keys}
        <button class="key small" data-action="pin-cancel">${escape(this.t('cancel'))}</button>
        <button class="key" data-action="pin-digit" data-digit="0" ${busy}>0</button>
        <button class="key small" data-action="pin-back" aria-label="${escape(this.t('erase'))}" ${this._pin ? '' : 'disabled'}>${svg('back', 22)}</button>
      </div></div>`;
  }
  render() {
    if (!this._config || !this._hass) return;
    const data = this._data = boardData(this._hass, this._config);
    this._access = parentAccess(this._hass);
    // Parent mode closes by itself; show the board locked again on time.
    clearTimeout(this._lockTimer);
    if (this._access.until) this._lockTimer = setTimeout(() => this.render(), Math.max(0, this._access.until - new Date()) + 500);
    const title = this._config.title ?? (this._config.due === 'today' ? this.t('today') : this.t('all'));
    const empty = data.members.length ? (this._config.due === 'today' ? this.t('allDone') : this.t('noTasks')) : this.t('noMembers');
    const rewards = this._config.show_rewards && data.members.length ? data.rewards : [];
    const done = this._config.show_done ? data.doneRows : [];
    // Bonuses and penalties are for parents: on the tablet, only in parent mode.
    const presets = this._config.show_bonus && this._access.parent && data.members.length ? data.presets : [];
    this.shadowRoot.innerHTML = `<style>
      :host { --dt-ring: #6366f1; --dt-gold: #f5b400; --dt-blue: #3b6fd8; --dt-green: #1e8e3e; --dt-line: var(--divider-color, rgba(127,127,127,.2)); }
      ha-card { padding: 20px 20px 12px; }
      .face { border-radius: 50%; object-fit: cover; display: block; flex: none; }
      .initial { display: grid; place-items: center; background: var(--primary-color); color: var(--text-primary-color, #fff); font-weight: 700; }
      .face.grey { filter: grayscale(1); opacity: .35; }
      .face.away { filter: grayscale(1); opacity: .45; }
      .away-pin { position: absolute; left: -6px; top: -4px; width: 24px; height: 24px; box-sizing: border-box; border-radius: 50%;
        background: #8e8a99; color: #fff; border: 2px solid var(--card-background-color, #fff); display: flex; align-items: center; justify-content: center; }
      .face.empty { border: 2px dashed var(--dt-line); box-sizing: border-box; }
      .face.leader { box-shadow: 0 0 0 3px var(--card-background-color, #fff), 0 0 0 5px var(--dt-gold); }
      .podium { display: flex; justify-content: center; align-items: flex-end; gap: 10px; margin: 4px 0 24px; }
      .podium-col { flex: 0 1 150px; display: flex; flex-direction: column; align-items: center; min-width: 0; }
      .podium-col.rank1 { flex-basis: 170px; }
      .steps1 .podium-col.rank1 { flex-basis: 220px; }
      .steps2 .podium-col { flex-basis: 170px; }
      .podium-faces { display: flex; gap: 10px; justify-content: center; }
      .podium-member { display: flex; flex-direction: column; align-items: center; }
      .crown { line-height: 0; margin-bottom: 2px; }
      .podium-face { position: relative; line-height: 0; }
      .coin { position: absolute; right: -10px; bottom: -4px; display: inline-flex; align-items: center; gap: 2px; padding: 2px 7px 2px 5px; border-radius: 999px;
        background: #fff4cc; color: #8a5d00; font-size: 13px; font-weight: 800; line-height: 1.2; border: 2px solid var(--card-background-color, #fff); box-shadow: 0 1px 3px rgba(0,0,0,.15); }
      .coin svg { color: var(--dt-gold); }
      .podium-name { margin-top: 6px; font-weight: 700; font-size: 16px; display: flex; align-items: center; gap: 6px; }
      .step { width: 100%; margin-top: 10px; border-radius: 14px 14px 0 0; display: flex; flex-direction: column; align-items: center; justify-content: center; font-weight: 800; }
      .step .score { font-size: 24px; line-height: 1; }
      .step .unit { font-size: 11px; font-weight: 700; opacity: .75; }
      .rank1 .step { height: 92px; background: rgba(245,180,0,.16); color: #a87300; } .rank1 .step .score { font-size: 26px; }
      .rank2 .step { height: 64px; background: rgba(59,111,216,.12); color: var(--dt-blue); }
      .rank3 .step { height: 48px; background: rgba(160,110,70,.14); color: #8a6f57; } .rank3 .step .score { font-size: 18px; }
      section { margin-bottom: 20px; }
      .head { display: flex; align-items: center; gap: 10px; padding-bottom: 10px; border-bottom: 2px solid var(--dt-line); }
      .head.todo { border-color: var(--dt-blue); } .head.done { border-color: var(--dt-green); } .head.gift { border-color: #a87300; }
      .head h2 { margin: 0; font-size: 17px; font-weight: 700; }
      .head-icon { width: 32px; height: 32px; border-radius: 10px; display: grid; place-items: center; flex: none; }
      .head-icon.todo { background: rgba(59,111,216,.12); color: var(--dt-blue); }
      .head-icon.done { background: rgba(30,142,62,.12); color: var(--dt-green); }
      .head-icon.gift { background: rgba(245,180,0,.16); color: #a87300; }
      .count { margin-left: auto; font-size: 13px; font-weight: 700; }
      .count.todo { color: var(--dt-blue); } .count.done { color: var(--dt-green); } .count.gift { color: #a87300; }
      .row { display: flex; align-items: center; gap: 10px; min-height: 64px; box-sizing: border-box; margin-top: 8px; padding: 0 10px 0 16px;
        border: 1px solid var(--dt-line); border-radius: 16px; box-shadow: 0 1px 2px rgba(0,0,0,.05); }
      .row.small { min-height: 56px; }
      .name { flex: 1 1 auto; min-width: 0; font-size: 17px; font-weight: 400; display: flex; flex-direction: column; }
      .name.muted { font-size: 16px; font-weight: 400; color: var(--secondary-text-color); }
      .mode { display: inline-flex; align-items: center; gap: 4px; margin-top: 2px; font-size: 13px; font-weight: 600; line-height: 1.3; }
      .mode svg { flex: none; }
      .mode.each { color: var(--dt-blue); } .mode.first { color: #e8590c; } .mode.one { color: var(--secondary-text-color); }
      .sub { font-size: 12px; font-weight: 400; color: var(--secondary-text-color); margin-top: 2px; }
      .armed-text { color: var(--dt-green); font-weight: 600; }
      .pts { display: inline-flex; align-items: center; gap: 3px; padding: 4px 10px 4px 8px; border-radius: 999px; font-size: 14px; font-weight: 800;
        background: rgba(79,70,229,.12); color: #4f46e5; white-space: nowrap; }
      .pts svg { color: var(--dt-gold); }
      .pts.muted { background: rgba(127,127,127,.12); color: var(--secondary-text-color); font-weight: 700; } .pts.muted svg { color: rgba(127,127,127,.5); }
      .pts.cost { background: rgba(245,180,0,.16); color: #8a5a00; }
      .pts.bonus { background: rgba(30,142,62,.14); color: var(--dt-green); }
      .pts.penalty { background: rgba(217,48,37,.12); color: var(--error-color, #d93025); }
      .head.bonus { border-color: #7c4dff; } .head-icon.bonus { background: rgba(124,77,255,.12); color: #7c4dff; } .count.bonus { color: #7c4dff; }
      .hourglass { color: #8a6f57; line-height: 0; }
      .streak { display: inline-flex; align-items: center; gap: 1px; font-size: 13px; font-weight: 800; color: #e8590c; }
      .streak.at-risk { color: #b0a59a; }
      .surprise { display: inline-flex; align-items: center; gap: 3px; padding: 4px 9px 4px 7px; border-radius: 999px; font-size: 13px; font-weight: 800;
        background: linear-gradient(90deg, rgba(236,72,153,.16), rgba(124,77,255,.16)); color: #a21caf; white-space: nowrap; }
      .row.is-surprise { border-color: rgba(162,28,175,.45); }
      .period { display: flex; align-items: center; gap: 8px; margin: 0 0 18px; padding: 10px 14px; border-radius: 14px;
        background: rgba(245,180,0,.16); color: #8a5a00; font-size: 15px; }
      .period-end { margin-left: auto; font-size: 13px; white-space: nowrap; }
      .rank { display: flex; flex-direction: column; align-items: center; gap: 3px; margin-top: 4px; padding: 3px 6px; border-radius: 12px; touch-action: manipulation; }
      .rank:active { background: rgba(99,102,241,.1); }
      .rank-chip { display: flex; align-items: center; gap: 4px; font-size: 13px; font-weight: 700; color: var(--dt-ring); }
      .rank-img { display: grid; place-items: center; flex: none; line-height: 1; object-fit: contain; }
      .rank-img.next { opacity: .4; filter: grayscale(.6); }
      .rank-prog { display: flex; align-items: center; gap: 5px; }
      .bar { display: block; height: 8px; border-radius: 4px; background: var(--dt-line); overflow: hidden; }
      .rank-prog .bar { width: 92px; }
      .bar i, .gauge i { display: block; height: 100%; background: var(--dt-ring); border-radius: inherit; }
      /* Fixed like HA's own dialogs: the card may be shorter than the details. */
      .rank-scrim { position: fixed; inset: 0; z-index: 10; background: rgba(20,18,30,.45); display: flex; align-items: center; justify-content: center; padding: 12px; box-sizing: border-box; }
      .rank-dialog { width: 100%; max-width: 440px; max-height: 100%; overflow-y: auto; box-sizing: border-box; background: var(--card-background-color, #fff); border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,.25); padding: 16px 16px 14px; }
      .rank-head { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; }
      .rank-head .close { margin-left: auto; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: rgba(127,127,127,.12); color: var(--secondary-text-color); }
      .rank-hero { display: flex; align-items: center; gap: 12px; margin: 12px 0 8px; }
      .rank-level { font-size: 12px; font-weight: 700; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .05em; }
      .rank-name { font-size: 20px; font-weight: 800; line-height: 1.15; color: var(--dt-ring); }
      .rank-sub { font-size: 13px; color: var(--secondary-text-color); margin-top: 2px; }
      .rank-big .bar { height: 12px; border-radius: 6px; }
      .rank-nums { display: flex; justify-content: space-between; font-size: 13px; color: var(--secondary-text-color); margin-top: 4px; }
      .rank-nums b { color: var(--primary-text-color); }
      .rank-goal { display: flex; align-items: center; gap: 8px; margin: 10px 0 12px; padding: 8px 10px; border-radius: 12px; background: rgba(99,102,241,.08); font-size: 14px; }
      .rank-goal b { color: var(--dt-ring); }
      .rank-ladder { list-style: none; margin: 0; padding: 0; }
      .rank-ladder li { display: flex; align-items: center; gap: 10px; padding: 5px 6px; border-radius: 10px; font-size: 14px; }
      .rank-ladder li > span:nth-child(2) { flex: 1; min-width: 0; }
      .rank-ladder .mark { display: inline-flex; align-items: center; gap: 3px; font-size: 12px; font-weight: 700; color: var(--secondary-text-color); white-space: nowrap; }
      .rank-ladder .got .mark { color: var(--dt-green); }
      .rank-ladder .here { background: rgba(245,180,0,.16); font-weight: 800; } .rank-ladder .here .mark { color: #a87300; }
      .rank-ladder .later { color: var(--secondary-text-color); }
      .rank-foot { margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--dt-line); font-size: 12px; line-height: 1.4; color: var(--secondary-text-color); }
      .gauge { flex: 1; min-width: 60px; height: 8px; border-radius: 4px; background: var(--dt-line); overflow: hidden; }
      .gauge.full i { background: var(--dt-green); }
      .gauge-n { font-size: 13px; font-weight: 700; color: var(--secondary-text-color); white-space: nowrap; }
      .goal { margin: 0 0 18px; padding: 12px 14px; border-radius: 14px; background: rgba(245,180,0,.1); border: 1px solid rgba(245,180,0,.35); }
      .goal.done { background: rgba(30,142,62,.1); border-color: rgba(30,142,62,.35); }
      .goal-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; color: #a87300; }
      .goal.done .goal-head { color: var(--dt-green); }
      .goal-head b { color: var(--primary-text-color); }
      .goal-tag { font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: rgba(245,180,0,.2); }
      .goal-line { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
      .goal-faces { display: flex; } .goal-faces .face + .face { margin-left: -8px; }
      .goal-reward { display: flex; align-items: center; gap: 6px; margin-top: 8px; font-size: 14px; font-weight: 600; }
      .row.quest .name { flex: 1 1 40%; } .row.quest .gauge { flex: 1 1 30%; }
      .row.quest.is-done { opacity: .7; }
      .head.quest { border-color: #e8590c; } .head-icon.quest { background: rgba(232,89,12,.12); color: #e8590c; } .count.quest { color: #e8590c; }
      .faces { display: flex; gap: 8px; margin-left: 6px; justify-content: flex-end; align-items: center; padding: 6px 0; }
      .slot { position: relative; display: block; line-height: 0; margin: 0 2px; }
      button { font: inherit; color: inherit; cursor: pointer; border: none; background: none; padding: 0; }
      button:disabled { cursor: default; opacity: .5; }
      .tap { border-radius: 50%; touch-action: manipulation; }
      .tap .face { box-shadow: 0 0 0 2px var(--card-background-color, #fff), 0 0 0 4px var(--dt-ring); }
      .tap:not(:disabled):active { transform: scale(.92); }
      .tap.busy { opacity: 1; } .tap.busy .face { box-shadow: 0 0 0 2px var(--card-background-color, #fff), 0 0 0 4px var(--primary-color); }
      .tap.armed .face { box-shadow: 0 0 0 2px var(--card-background-color, #fff), 0 0 0 4px var(--dt-green); }
      .waiting .face { opacity: .55; box-shadow: 0 0 0 2px var(--card-background-color, #fff), 0 0 0 4px #c9b8a8; }
      .badge { position: absolute; right: -3px; bottom: -3px; min-width: 20px; height: 20px; box-sizing: border-box; border-radius: 10px;
        border: 2px solid var(--card-background-color, #fff); display: flex; align-items: center; justify-content: center; gap: 2px;
        color: #fff; font-size: 10px; font-weight: 700; line-height: 1; white-space: nowrap; }
      .badge.wide { right: -10px; padding: 0 5px 0 3px; }
      .badge.gift, .badge.done { background: var(--dt-green); } .badge.wait { background: #8a6f57; } .badge.gray { background: #80868b; }
      .slot-pills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
      .slot-pill { padding: 2px 8px; border-radius: 999px; background: rgba(127,127,127,.12); color: var(--secondary-text-color); font-size: 13px; font-weight: 500; line-height: 18px; white-space: nowrap; }
      .slot-pill.now { background: rgba(59,111,216,.14); color: #1d4ed8; font-weight: 600; }
      .ringbtn { position: relative; width: 64px; height: 64px; flex: none; border-radius: 50%; touch-action: manipulation; }
      .ringbtn:disabled { opacity: 1; }
      .ringbtn:not(:disabled):active { transform: scale(.92); }
      .ringbtn.busy .ring { opacity: .5; }
      .ring { position: absolute; inset: 0; }
      .ring-face { position: absolute; inset: 8px; line-height: 0; }
      .ringbtn .badge { right: 0; bottom: 0; width: 22px; height: 22px; }
      .badge.amber { background: #F59E0B; }
      .row.open-grid { display: block; padding: 12px 12px 10px 16px; border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,.12); }
      .grid-top { display: flex; align-items: center; gap: 10px; }
      .grid { display: grid; gap: 8px 10px; align-items: center; margin-top: 12px; }
      .gh { text-align: center; font-size: 13px; font-weight: 600; line-height: 16px; color: var(--secondary-text-color); display: flex; flex-direction: column; }
      .gh small { font-size: 12px; font-weight: 500; }
      .gh.now { color: #1d4ed8; }
      .gname { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; min-width: 0; }
      .gname > span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .capsule { justify-self: center; display: inline-flex; gap: 4px; padding: 4px; border-radius: 999px; background: #f5f5f4; border: 1px solid #e7e5e4; }
      .cap { width: 48px; height: 44px; border-radius: 999px; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.08); display: grid; place-items: center; }
      .cap.ok { color: #15803d; } .cap.no { color: #b91c1c; }
      .catchup { justify-self: center; display: inline-flex; align-items: center; gap: 6px; min-height: 44px; padding: 0 14px; border-radius: 999px; background: #ffedd5; color: #9a3412; font-size: 13px; font-weight: 600; }
      .gdot { justify-self: center; width: 34px; height: 34px; border-radius: 50%; box-sizing: border-box; display: grid; place-items: center; }
      .gdot.done { background: #0EA5E9; color: #fff; }
      .gdot.open { border: 3px solid #0EA5E9; color: transparent; min-width: 44px; min-height: 44px; }
      .gdot.open:hover { color: #0EA5E9; }
      .gdot.later { border: 2px dashed #d9d9d9; }
      .gdot.taken { background: rgba(127,127,127,.12); width: 14px; height: 14px; }
      .gfoot { display: flex; align-items: center; gap: 10px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--dt-line); font-size: 13px; color: var(--secondary-text-color); }
      .gfoot > span { flex: 1; }
      .approve-all { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 18px; border-radius: 999px; background: #15803d; color: #fff; font-size: 14px; font-weight: 600; }
      .icon-btn { width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; }
      .icon-btn.ok { background: rgba(30,142,62,.14); color: var(--dt-green); } .icon-btn.no { background: rgba(217,48,37,.12); color: var(--error-color, #d93025); }
      .flash { font-weight: 700; color: var(--success-color, var(--dt-green)); }
      .empty-text { font-size: 17px; padding: 14px 2px 4px; }
      .error { color: var(--error-color); margin: 8px 0; }
      ha-card { position: relative; display: block; }
      .parent-btn { position: absolute; top: 10px; right: 10px; z-index: 1; display: flex; align-items: center; gap: 4px; height: 36px; min-width: 36px;
        padding: 0 9px; border-radius: 18px; white-space: nowrap; color: var(--secondary-text-color); background: rgba(127,127,127,.1); font-size: 13px; font-weight: 700; justify-content: center; }
      .parent-btn.open { color: var(--dt-green); background: rgba(30,142,62,.14); }
      .pin-pad { position: absolute; inset: 0; z-index: 2; border-radius: inherit; background: var(--card-background-color, #fff);
        display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px; padding: 16px; }
      .pin-title { display: flex; align-items: center; gap: 8px; font-size: 18px; font-weight: 700; }
      .dots { display: flex; gap: 14px; }
      .dot { width: 16px; height: 16px; border-radius: 50%; border: 2px solid var(--dt-ring); box-sizing: border-box; }
      .dot.full { background: var(--dt-ring); }
      .pin-message { min-height: 20px; font-size: 14px; color: var(--secondary-text-color); text-align: center; }
      .error-text { color: var(--error-color, #d93025); }
      .keys { display: grid; grid-template-columns: repeat(3, 72px); gap: 12px; }
      .key { height: 64px; border-radius: 32px; background: rgba(99,102,241,.1); font-size: 26px; font-weight: 600; touch-action: manipulation;
        display: grid; place-items: center; }
      .key.small { font-size: 14px; background: none; }
      .key:not(:disabled):active { transform: scale(.94); }
    </style><ha-card>
      ${this.renderParentButton()}${this.renderPinPad()}${this._config.show_points ? this.renderRankDetails(data.members, data.ladder) : ''}
      ${this._config.show_points && data.members.length ? this.renderPodium(data.members) : ''}
      ${this.renderPeriod(data.period)}
      ${this._config.show_goals ? this.renderChallenges(data.challenges, data.members) : ''}
      ${this._config.show_todo ? `<section>${this.header('todo', 'todo', title, data.rows.length)}
        ${data.rows.length ? data.rows.map(row => this.renderTask(row)).join('') : `<div class="empty-text">${escape(empty)}</div>`}</section>` : ''}
      ${this._config.show_goals ? this.renderQuests(data.members) : ''}
      ${done.length ? `<section>${this.header('check', 'done', this.t('done'), done.length)}${done.map(item => this.renderDone(item)).join('')}</section>` : ''}
      ${rewards.length ? `<section>${this.header('gift', 'gift', this.t('rewards'), rewards.length)}${rewards.map(r => this.renderReward(r, data.members, data.requests)).join('')}</section>` : ''}
      ${presets.length ? `<section>${this.header('plusminus', 'bonus', this.t('bonus_title'), presets.length)}${presets.map(p => this.renderPreset(p, data.members)).join('')}</section>` : ''}
      ${this._error ? `<div class="error">${escape(this._error)}</div>` : ''}
    </ha-card>`;
  }
}

class HoplaFamilyCardEditor extends HTMLElement {
  setConfig(config) { this._config = {...config}; this.render(); }
  set hass(hass) { const first = !this._hass; this._hass = hass; if (first) this.render(); }
  t(key, values) {
    const language = this._hass?.locale?.language || this._hass?.language || browserLanguage();
    if (this._language !== language) { this._language = language; this._t = translator(language, () => this.render()); }
    return this._t(key, values);
  }
  render() {
    if (!this._hass || !this._config) return;
    const {members} = boardData(this._hass, {});
    const labels = new Set();
    for (const [id, state] of Object.entries(this._hass.states)) {
      if (id.startsWith('sensor.') && state.attributes.task_id !== undefined) labelNames(state.attributes.labels).forEach(l => labels.add(l));
    }
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.computeLabel = schema => this.t(`family.editor.${schema.name}`);
      this._form.addEventListener('value-changed', event => {
        event.stopPropagation();
        const config = {...event.detail.value};
        for (const key of Object.keys(config)) if (config[key] === '' || (Array.isArray(config[key]) && !config[key].length)) delete config[key];
        if (config.members) config.members = config.members.map(Number);
        this._config = config;
        this.dispatchEvent(new CustomEvent('config-changed', {detail: {config}, bubbles: true, composed: true}));
      });
      this.append(this._form);
    }
    this._form.hass = this._hass;
    this._form.schema = [
      {name: 'title', selector: {text: {}}},
      {name: 'members', selector: {select: {multiple: true, options: members.map(m => ({value: String(m.id), label: m.name}))}}},
      {name: 'labels', selector: {select: {multiple: true, custom_value: true, options: [...labels]}}},
      {name: 'due', selector: {select: {mode: 'dropdown', options: [{value: 'today', label: this.t('family.editor.due_today')}, {value: 'all', label: this.t('family.editor.due_all')}]}}},
      {name: 'show_points', selector: {boolean: {}}},
      {name: 'show_todo', selector: {boolean: {}}},
      {name: 'show_done', selector: {boolean: {}}},
      {name: 'show_rewards', selector: {boolean: {}}},
      {name: 'show_approval', selector: {boolean: {}}},
      {name: 'allow_redeem', selector: {boolean: {}}},
      {name: 'show_bonus', selector: {boolean: {}}},
      {name: 'show_goals', selector: {boolean: {}}},
    ];
    this._form.data = {due: 'today', show_points: true, show_todo: true, show_done: true, show_rewards: true, show_approval: false, allow_redeem: false, show_bonus: true, show_goals: true,
      ...this._config, members: (this._config.members || []).map(String)};
  }
}

if (!customElements.get('hopla-family-card')) customElements.define('hopla-family-card', HoplaFamilyCard);
if (!customElements.get('hopla-family-card-editor')) customElements.define('hopla-family-card-editor', HoplaFamilyCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === 'hopla-family-card')) {
  const t = translator(browserLanguage());
  window.customCards.push({type: 'hopla-family-card', name: t('family.card_name'), description: t('family.card_description')});
}
