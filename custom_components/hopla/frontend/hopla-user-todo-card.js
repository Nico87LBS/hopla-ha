// HA starts extra modules alongside its app bundle, which replaces both the
// custom-element registry and HTMLElement with its scoped-registry polyfill.
// Wait before defining classes so they use the final registry and base class.
await customElements.whenDefined('home-assistant');
const {translator, browserLanguage, reloadIfOutdated} = await import(new URL(`./hopla-i18n.js${new URL(import.meta.url).search}`, import.meta.url));
const english = translator('en');
const hassLanguage = hass => hass?.locale?.language || hass?.language || browserLanguage();
// Each element keeps a translator for its HA language and renders again when
// a language file finishes loading.
function elementTranslator(element) {
  const language = hassLanguage(element._hass);
  if (element._language !== language) { element._language = language; element._t = translator(language, () => element.render()); }
  return element._t;
}

function compareTasks(a, b, sortBy, language) {
  const timestamp = value => Number.isFinite(Date.parse(value)) ? Date.parse(value) : Infinity;
  const primary = sortBy === 'priority' ? (Number(b.priority) || 0) - (Number(a.priority) || 0)
    : sortBy === 'name' ? (a.name || '').localeCompare(b.name || '', language, {sensitivity:'base',numeric:true}) : 0;
  return primary || timestamp(a.next_due_date) - timestamp(b.next_due_date) || a.task_id - b.task_id;
}
export function upcomingDayLimit(value) {
  return value === undefined ? 7 : value === null || value === '' ? 0 : Number(value);
}
export function completedTasks(state, userId, now = new Date(), config = {}) {
  const owner = state?.attributes?.hopla_user_id ?? userId;
  const days = Number(config.completed_days ?? 1);
  const since = new Date(now.getFullYear(), now.getMonth(), now.getDate() - days + 1);
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const tasks = (state?.attributes?.completed_tasks || []).filter(task => {
    const completed = new Date(task.completed_at);
    const matchesDate = userTasks({attributes:{tasks:[task]}}, 'all',
      config.completed_filter === 'matching' ? config.display_filters ?? config.display_filter : 'all',
      now, config.upcoming_days, 'due_date', undefined, config.include_overdue, config.labels, config.label_match).length > 0;
    return completed >= since && completed <= now && completed < tomorrow && matchesDate
      && (owner === 'all' || task.completed_by === Number(owner));
  }).sort((a,b) => Date.parse(b.completed_at) - Date.parse(a.completed_at));
  const limit = Number(config.completed_limit ?? 0);
  return limit > 0 ? tasks.slice(0, limit) : tasks;
}
export function recurrenceText(task, t = english) {
  const fixed = ['daily', 'weekly', 'monthly', 'yearly', 'adaptive', 'trigger', 'always', 'days_of_the_week', 'day_of_the_month'];
  if (task.frequency_type !== 'interval') return fixed.includes(task.frequency_type) ? t(`todo.recurrence.${task.frequency_type}`) : '';
  const units = ['hours', 'days', 'weeks', 'months', 'years'];
  const count = task.frequency;
  if (!units.includes(task.interval_type) || !Number.isInteger(count) || count < 1) return '';
  return t(`todo.recurrence.${task.interval_type}`, {count});
}
export function taskLabels(value) {
  const labels = typeof value === 'string' ? value.split(',') : Array.isArray(value) ? value : [];
  return [...new Set(labels.map(label => typeof label === 'string' ? label : label?.name)
    .filter(name => typeof name === 'string' && name.trim()).map(name => name.trim()))];
}
export function labelColors(value, name) {
  const label = Array.isArray(value) ? value.find(label => typeof label?.name === 'string' && label.name.trim() === name
    && typeof label.color === 'string' && /^#[\da-f]{3}(?:[\da-f]{3})?$/i.test(label.color)) : null;
  if (!label) return null;
  const hex = label.color.slice(1);
  const full = hex.length === 3 ? [...hex].map(char => char + char).join('') : hex;
  const [r, g, b] = [0, 2, 4].map(offset => parseInt(full.slice(offset, offset + 2), 16));
  // Match Hopla's choice of black or white text for label backgrounds.
  return {backgroundColor: label.color, color: r * 0.299 + g * 0.587 + b * 0.114 > 186 ? '#000000' : '#ffffff'};
}
export function dateFilters(config) {
  if (config.display_filters !== undefined) return config.display_filters;
  switch (config.display_filter) {
    case 'overdue': return ['overdue'];
    case 'today': return ['today'];
    case 'upcoming': return [...(config.include_overdue !== false ? ['overdue'] : []), 'today', 'future'];
    default: return [];
  }
}
function selectedUser(state, userId) {
  return state?.attributes.hopla_user_id ?? userId ?? 'all';
}
export function userTasks(state, userId, displayFilter = 'all', now = new Date(), upcomingDays = 7, sortBy = 'due_date', language, includeOverdue = false, labels = [], labelMatch = 'any', includeAnyone = false) {
  if (typeof labels === 'boolean') { includeAnyone = labels; labels = []; }
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const tomorrow = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  const limit = upcomingDayLimit(upcomingDays);
  const upcomingEnd = new Date(now.getFullYear(), now.getMonth(), now.getDate() + limit + 1);
  userId = selectedUser(state, userId);
  const tasks = [...(state?.attributes?.tasks || []), ...(includeAnyone ? state?.attributes?.anyone_tasks || [] : [])];
  return tasks.filter(task => userId === 'all' || task.assigned_to === Number(userId) || (includeAnyone && task.assigned_to == null))
    // A task started from outside waits, hidden, until it is given a date.
    .filter(task => !(task.frequency_type === 'trigger' && !task.next_due_date))
    .filter(task => {
      if (!labels.length) return true;
      const names = taskLabels(task.labels);
      return labelMatch === 'all' ? labels.every(label => names.includes(label)) : labels.some(label => names.includes(label));
    })
    .filter(task => {
      if (Array.isArray(displayFilter)) {
        if (!displayFilter.length) return true;
        if (!task.next_due_date) return displayFilter.includes('undated');
        const value = task.next_due_date;
        const due = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value);
        return (displayFilter.includes('overdue') && isOverdue(value, now))
          || (displayFilter.includes('today') && due >= today && due < tomorrow)
          || (displayFilter.includes('future') && due >= tomorrow && (limit === 0 || due < upcomingEnd));
      }
      if (displayFilter === 'all') return true;
      if (displayFilter === 'overdue') return isOverdue(task.next_due_date, now);
      if (!task.next_due_date) return false;
      const value = task.next_due_date;
      const due = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value);
      if (displayFilter === 'today') return due >= today && due < tomorrow;
      if (displayFilter !== 'upcoming' || isNaN(due)) return false;
      if (isOverdue(value, now)) return includeOverdue;
      return due >= today && (limit === 0 || due < upcomingEnd);
    })
    .sort((a, b) => compareTasks(a, b, sortBy, language));
}
export function dueText(value, language, now = new Date(), timeFormat, display = 'date', t = translator(language)) {
  const dateOnly = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value);
  const date = value ? new Date(dateOnly ? `${value}T12:00:00` : value) : null;
  if (!date || isNaN(date)) return t('todo.no_due');
  const day = value => Date.UTC(value.getFullYear(), value.getMonth(), value.getDate());
  const days = Math.round((day(date) - day(now)) / 86400000);
  let label = days < 0 ? t('todo.overdue_days', {count: -days}) : days === 0 ? t('todo.today') : days === 1 ? t('todo.tomorrow')
    : date.toLocaleDateString(language, {weekday: 'short', month: 'short', day: 'numeric'});
  if (display !== 'date') {
    const relative = new Intl.RelativeTimeFormat(language, {numeric:'auto'});
    let oriented;
    if (days === 0 && hasDueTime(value)) {
      const hours = Math.round((date - now) / 3600000);
      const minutes = Math.round((date - now) / 60000);
      oriented = relative.format(hours || minutes === 0 ? hours : minutes, hours || minutes === 0 ? 'hour' : 'minute');
    } else oriented = relative.format(days === 7 ? 1 : days === -7 ? -1 : days, Math.abs(days) === 7 ? 'week' : 'day');
    oriented = oriented.charAt(0).toLocaleUpperCase(language) + oriented.slice(1);
    if (display === 'relative') return oriented;
    label = `${oriented} · ${date.toLocaleDateString(language, {weekday:'short',month:'short',day:'numeric'})}`;
  }
  if (!hasDueTime(value)) return label;
  const time = date.toLocaleTimeString(language, {hour:'2-digit', minute:'2-digit', hour12:timeFormat === '12' ? true : timeFormat === '24' ? false : undefined});
  return `${label} · ${time}`;
}
export function hasDueTime(value) {
  if (!value || /^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value);
  // Hopla date-only deadlines can arrive as a local end-of-day timestamp.
  return !isNaN(date) && !(date.getHours() === 23 && date.getMinutes() === 59);
}
export function isOverdue(value, now = new Date()) {
  if (!value) return false;
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
  const due = new Date(dateOnly ? `${value}T00:00:00` : value);
  const cutoff = dateOnly ? new Date(now.getFullYear(), now.getMonth(), now.getDate()) : now;
  return !isNaN(due) && due < cutoff;
}
export function emptyMessage(config, userName, t = english) {
  const filters = dateFilters(config);
  let filter = config.display_filters !== undefined
    ? filters.length ? filters.map(value=>t(`todo.filters.${value}`)).join(', ') : t('todo.filters.all')
    : t(`todo.filters.${config.display_filter || 'all'}`);
  if ((config.display_filter === 'upcoming' && config.display_filters === undefined) || filters.includes('future')) {
    const days = upcomingDayLimit(config.upcoming_days);
    filter = days === 0 ? t('todo.filters.no_limit', {filter}) : t('todo.filters.ahead', {filter, count: days});
  }
  let message = config.user_id === 'all' ? t('todo.empty.all_users') : t(config.include_anyone ? 'todo.empty.user_anyone' : 'todo.empty.user', {name: userName});
  message = t('todo.empty.filter', {message, filter});
  if (config.labels?.length) message = t('todo.empty.labels', {message, labels: config.labels.join(t(config.label_match === 'all' ? 'todo.empty.and' : 'todo.empty.or'))});
  return message;
}
export function actionData(state, task) {
  const data = {task_id: task.task_id, config_entry_id: state.attributes.config_entry_id};
  return data;
}
export function assignableMembers(state, task) {
  return (state?.attributes.circle_members || []).filter(member => !task.assignee_ids?.length || task.assignee_ids.includes(member.user_id));
}
export function localDateTime(value) {
  const date = value ? new Date(value) : new Date();
  if (isNaN(date)) return '';
  const pad = value => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
export function descriptionText(value) {
  if (typeof value !== 'string' || !value.trim()) return '';
  // Template contents are inert and never attached to the page. Only text is rendered.
  const template = document.createElement('template'); template.innerHTML = value;
  const omitted = new Set(['SCRIPT','STYLE','NOSCRIPT','IFRAME','OBJECT','EMBED','SVG','MATH','HEAD','TEMPLATE']);
  const blocks = new Set(['P','DIV','SECTION','ARTICLE','BLOCKQUOTE','PRE','H1','H2','H3','H4','H5','H6']);
  const text = node => {
    if (node.nodeType === 3) return node.nodeValue || '';
    if (node.nodeType !== 1 || omitted.has(node.tagName)) return '';
    if (node.tagName === 'BR') return '\n';
    const content = [...node.childNodes].map(text).join('');
    if (node.tagName === 'LI') return `- ${content.trim()}\n`;
    if (blocks.has(node.tagName) || ['UL','OL','TR'].includes(node.tagName)) return `\n${content}\n`;
    if (['TD','TH'].includes(node.tagName)) return `${content}\t`;
    return content;
  };
  return [...template.content.childNodes].map(text).join('').replace(/\u00a0/g,' ')
    .replace(/[ \t]+\n/g,'\n').replace(/\n{3,}/g,'\n\n').trim();
}
// HA replaces its hass object for unrelated entity updates too. Only the selected
// list and presentation settings affect this card's DOM.
function samePresentation(previous, next) {
  return previous.locale === next.locale && previous.themes === next.themes
    && previous.config === next.config && previous.localize === next.localize;
}
class HoplaUserTodoCard extends HTMLElement {
  static getConfigElement() { return document.createElement('hopla-user-todo-editor'); }
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(id => id.startsWith('todo.') && hass.states[id].attributes.circle_members);
    return {entity, user_id: hass.states[entity]?.attributes.hopla_user_id ?? hass.states[entity]?.attributes.circle_members?.[0]?.user_id};
  }
  constructor() {
    super(); this.attachShadow({mode: 'open'}); this._pending = new Map(); this._completed = new Map();
    this._outside = event => {
      const path = event.composedPath();
      if (this._panel && !path.includes(this) && !path.some(node => node.localName === 'ha-dialog-date-picker') && !this._pending.has(this._panel.taskId)) this.closePanel();
    };
  }
  connectedCallback() { document.addEventListener('pointerdown', this._outside); this.ensureForm(); }
  async ensureForm() {
    if (customElements.get('ha-form') || this._loadingForm) return;
    this._loadingForm = true;
    try {
      const helpers = await window.loadCardHelpers();
      const card = await helpers.createCardElement({type:'entities',entities:[]});
      await card.constructor.getConfigElement();
      this.render();
    } catch { /* Native inputs remain available if HA controls cannot be loaded. */ }
    finally { this._loadingForm = false; }
  }
  disconnectedCallback() { document.removeEventListener('pointerdown', this._outside); }
  t(key, values) { return elementTranslator(this)(key, values); }
  setConfig(config) {
    const signature = JSON.stringify(config);
    if (signature === this._configInputSignature) return;
    const error = key => new Error(this.t(`todo.errors.${key}`));
    if (!config.entity?.startsWith('todo.')) throw error('entity');
    if (config.task_view && !['both','pending','completed'].includes(config.task_view)) throw error('task_view');
    if (config.completed_filter !== undefined && !['all','matching'].includes(config.completed_filter)) throw error('completed_filter');
    for (const [key, min, max] of [['completed_days',1,7],['completed_limit',0,500]]) {
      if (config[key] != null && (config[key] === '' || typeof config[key] === 'boolean' || !Number.isInteger(Number(config[key])) || Number(config[key]) < min || Number(config[key]) > max)) throw new Error(this.t(`todo.errors.${key}`, {min, max}));
    }
    if (config.user_id !== undefined && config.user_id !== 'all' && (!Number.isInteger(Number(config.user_id)) || Number(config.user_id) < 1)) throw error('user');
    if (config.display_filter && !['all','overdue','today','upcoming'].includes(config.display_filter)) throw error('display_filter');
    if (config.display_filters !== undefined && (!Array.isArray(config.display_filters) || config.display_filters.some(filter=>!['overdue','today','future','undated'].includes(filter)))) throw error('display_filters');
    if (config.labels !== undefined && (!Array.isArray(config.labels) || config.labels.some(label => typeof label !== 'string' || !label.trim()))) throw error('labels');
    if (config.label_match !== undefined && !['any','all'].includes(config.label_match)) throw error('label_match');
    if (config.sort_by && !['due_date','priority','name'].includes(config.sort_by)) throw error('sort_by');
    if (config.due_display && !['date','relative','both'].includes(config.due_display)) throw error('due_display');
    if (config.row_spacing !== undefined && !['auto','compact','comfortable'].includes(config.row_spacing)) throw error('row_spacing');
    if (config.upcoming_days !== undefined && (!Number.isInteger(Number(config.upcoming_days)) || Number(config.upcoming_days) < 0 || Number(config.upcoming_days) > 365)) throw error('upcoming_days');
    this._config = {task_view:'both', completed_days:1, completed_filter:'all', completed_limit:0, row_spacing:'auto', display_filter:'all', sort_by:'due_date', button_style: 'text', button_size: 'compact', button_shape: 'rounded',
      button_content: 'icon', complete_control: 'checkbox', include_overdue:true, include_anyone:false, due_display:'date', show_labels:false, show_points:false, show_recurrence:false, use_label_colors:false, show_assignee:true, show_complete:true, show_postpone:true, show_due_date:true, show_reassign:true, ...config, completed_days:config.completed_days ?? 1, completed_limit:config.completed_limit ?? 0, labels:taskLabels(config.labels), user_id: config.user_id === undefined || config.user_id === 'all' ? 'all' : Number(config.user_id), upcoming_days:upcomingDayLimit(config.upcoming_days)};
    if (this._panel && this._panel.kind !== 'details' && !this._config[{skip:'show_postpone',date:'show_due_date',assign:'show_reassign'}[this._panel.kind]]) this._panel = null;
    this._configInputSignature = signature;
    this.render();
  }
  set hass(hass) {
    if (reloadIfOutdated(hass)) return;
    const previous = this._hass;
    const minute = Math.floor(Date.now() / 60000);
    const unchanged = previous && previous !== hass && this._lastHassMinute === minute
      && previous.states[this._config?.entity] === hass.states[this._config?.entity]
      && samePresentation(previous, hass);
    this._hass = hass; this._lastHassMinute = minute;
    if (!unchanged) this.render();
  }
  getCardSize() {
    const state = this._hass?.states[this._config?.entity];
    return 2 + (this._config?.task_view === 'completed' ? 0 : this.filteredTasks(state).length)
      + (this._config?.task_view === 'pending' ? 0 : completedTasks(state, this._config?.user_id, new Date(), this._config).length);
  }
  filteredTasks(state) {
    return userTasks(state, this._config?.user_id, this._config?.display_filters ?? this._config?.display_filter, new Date(), this._config?.upcoming_days, this._config?.sort_by, this._hass?.locale?.language, this._config?.include_overdue, this._config?.labels, this._config?.label_match, this._config?.include_anyone);
  }
  async act(task, complete, dueDate, assignedTo) {
    if (this._pending.has(task.task_id)) return;
    const state = this._hass.states[this._config.entity];
    this._pending.set(task.task_id, complete); this._error = ''; this.render();
    try {
      const data = actionData(state, task);
      if (dueDate) data.due_date = dueDate;
      if (assignedTo !== undefined) data.assigned_to = assignedTo;
      await this._hass.callService('hopla', dueDate || assignedTo !== undefined ? 'update_task' : complete ? 'complete_assigned_task' : 'postpone_task', data);
      this._panel = null;
      if (complete) {
        this._completed.set(task.task_id, task);
        setTimeout(() => { this._completed.delete(task.task_id); this.render(); }, 1000);
      }
    } catch (err) { this._error = err.message || String(err); }
    finally { this._pending.delete(task.task_id); this.render(); }
  }
  closePanel() {
    const taskId = this._panel?.taskId;
    const kind = this._panel?.kind;
    this._panel = null; this._error = ''; this.render();
    this.shadowRoot.querySelector(`[data-action="${kind}"][data-task-id="${taskId}"]`)?.focus();
  }
  togglePanel(task, kind) {
    if (this._panel?.taskId === task.task_id && this._panel.kind === kind) { this.closePanel(); return; }
    const value = localDateTime(task.next_due_date);
    this._panel = {taskId: task.task_id, kind, date: value.slice(0, 10), time: task.next_due_date ? value.slice(11) : '09:00:00', showTime:false, assignedTo:task.assigned_to ?? null};
    this._error = '';
    this.render();
    this.shadowRoot.querySelector('.action-panel input, .action-panel select, .action-panel ha-form, .action-panel button')?.focus();
  }
  render() {
    if (!this._config || !this._hass) return;
    const state = this._hass.states[this._config.entity];
    const userId = selectedUser(state, this._config.user_id);
    const member = state?.attributes.circle_members?.find(m => m.user_id === userId);
    const focusedField = this.shadowRoot.activeElement?.dataset.field;
    this.shadowRoot.activeElement?.blur();
    this.shadowRoot.innerHTML = `<style>
      ha-card { padding: 12px; } h2 { margin: 0 0 8px; font-size: 20px; font-weight: 500; }
      .row { position:relative; display: flex; align-items: center; gap: 8px; padding: 2px 0; }
      .row.has-labels { padding:8px 0; }
      ha-card[data-spacing="compact"] .row { padding:2px 0; }
      ha-card[data-spacing="comfortable"] .row { padding:8px 0; }
      ha-card[data-labels="true"] { margin-block:4px; }
      .completed .name { text-decoration:line-through; color:var(--secondary-text-color); }
      .history-heading { font-size:14px; font-weight:500; color:var(--secondary-text-color); margin:16px 0 6px; border-top:1px solid var(--divider-color); padding-top:12px; }
      .history-check { color:var(--success-color, #43a047); width:44px; flex-shrink:0; }
      .history-row { padding:6px 0; }
      .actions { display:flex; align-items:center; gap:4px; flex-shrink:0; }
      .task { flex: 1; min-width: 0; } .name { overflow-wrap: anywhere; } .due { color: var(--secondary-text-color); font-size: 12px; margin-top: 2px; }
      .due.overdue { color:var(--warning-color); }
      .due { display:flex; align-items:center; gap:4px; }
      .task-points { display:inline-flex; align-items:center; gap:3px; flex-shrink:0; padding:0 5px; border-radius:10px; background:var(--secondary-background-color); color:var(--secondary-text-color); font-size:11px; line-height:18px; }
      .task-points ha-icon { --mdc-icon-size:12px; }
      .task-recurrence { display:flex; align-items:center; gap:4px; color:var(--secondary-text-color); font-size:12px; line-height:16px; }
      .task-recurrence ha-icon { --mdc-icon-size:14px; flex-shrink:0; }
      .due .recurring, .due .due-clock { --mdc-icon-size:14px; flex-shrink:0; }
      .due .assignee { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      ha-card button.task, ha-card div.task { display:flex; flex-direction:column; align-items:flex-start; justify-content:center; gap:2px; border:0; border-radius:0; padding:0; min-width:0; min-height:44px; text-align:left; background:transparent; color:var(--primary-text-color); font:inherit; }
      .task .name { display:flex; flex-wrap:wrap; align-items:center; gap:4px; line-height:20px; } .task .due { margin-top:0; line-height:16px; }
      .task-labels { display:flex; flex-wrap:wrap; gap:4px; max-width:100%; margin-top:2px; }
      .task-label { max-width:100%; box-sizing:border-box; padding:1px 6px; border-radius:10px; background:var(--secondary-background-color); color:var(--secondary-text-color); font-size:11px; line-height:16px; overflow-wrap:anywhere; text-align:start; }
      .description-indicator { --mdc-icon-size:16px; flex-shrink:0; color:var(--secondary-text-color); }
      .description { white-space:pre-wrap; overflow-wrap:anywhere; font-size:14px; color:var(--secondary-text-color); margin:2px 0 8px; }
      button { cursor: pointer; border: 1px solid var(--divider-color); border-radius: 8px; padding: 9px 11px; background: var(--card-background-color); color: var(--primary-color); font: inherit; font-size: 13px; }
      button:disabled, input:disabled { opacity: .5; cursor: default; }
      .complete-checkbox { width:44px; height:44px; display:flex; align-items:center; justify-content:center; flex-shrink:0; cursor:pointer; }
      input[type="checkbox"] { width:18px; height:18px; margin:0; accent-color:var(--primary-color); cursor:pointer; } button:focus-visible { outline: 2px solid var(--primary-color); }
      button { display:inline-flex; justify-content:center; align-items:center; gap:6px; box-sizing:border-box; min-width:44px; min-height:44px; } ha-icon { --mdc-icon-size:20px; display:inline-flex; align-items:center; justify-content:center; width:var(--mdc-icon-size); height:var(--mdc-icon-size); line-height:0; vertical-align:middle; }
      [data-style="text"] button { border-color:transparent; background:transparent; }
      [data-style="filled"] button { color:var(--text-primary-color); background:var(--primary-color); border-color:transparent; }
      [data-size="compact"] button { padding:5px 8px; font-size:12px; } [data-size="normal"] button { min-width:48px; min-height:48px; } [data-size="large"] button { min-width:52px; min-height:52px; padding:12px 16px; font-size:15px; }
      [data-shape="pill"] button { border-radius:24px; } [data-shape="square"] button { border-radius:0; }
      .error { color: var(--error-color); } .empty { color: var(--secondary-text-color); }
      .action-panel { display:flex; flex-wrap:wrap; align-items:center; gap:4px; margin:2px 0 6px; }
      .action-panel ha-form { flex:1; min-width:180px; --ha-space-6:8px; --time-input-flex:1; --ha-input-padding-bottom:0; --ha-input-required-marker:""; }
      .action-panel.date-panel { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; }
      .date-panel ha-form { min-width:0; }
      .date-panel .error { grid-column:1 / -1; }
      .panel-actions { display:flex; align-items:center; gap:4px; flex-shrink:0; margin-inline-start:auto; }
      .action-panel input, .action-panel select { flex:1; min-width:125px; width:0; box-sizing:border-box; height:44px; padding:8px; color-scheme:var(--ha-color-scheme,light); background:var(--secondary-background-color); color:var(--primary-text-color); border:0; border-bottom:1px solid var(--secondary-text-color); border-radius:4px 4px 0 0; font:inherit; font-size:14px; }
      .action-panel select option { background:var(--secondary-background-color); color:var(--primary-text-color); }
      .action-panel select option:hover, .action-panel select option:checked { background:Highlight; color:HighlightText; }
      .action-panel button { flex-shrink:0; border-color:transparent; background:transparent; color:var(--primary-color); }
      .action-panel .error { flex-basis:100%; margin:0; font-size:12px; } .skip-prompt { flex:1; font-size:13px; color:var(--secondary-text-color); }
      button[aria-pressed="true"], button[aria-expanded="true"] { background:var(--secondary-background-color); }
    </style><ha-card></ha-card>`;
    const card = this.shadowRoot.querySelector('ha-card');
    card.dataset.style = this._config.button_style;
    card.dataset.size = this._config.button_size;
    card.dataset.shape = this._config.button_shape;
    card.dataset.spacing = this._config.row_spacing;
    const t = (key, values) => this.t(key, values);
    const onTask = (action, task) => t('common.on_task', {action, task: task.name});
    const addText = (parent, tag, text, cls) => { const el = document.createElement(tag); el.textContent = text; if(cls) el.className = cls; parent.append(el); return el; };
    addText(card, 'h2', this._config.title || (userId === 'all' ? t('todo.title_all') : t('todo.title_user', {name: member?.display_name || t('common.user', {id: userId})})));
    if (this._error && !this._panel) addText(card, 'p', this._error, 'error');
    if (!state || ['unavailable', 'unknown'].includes(state.state)) { addText(card, 'p', t('todo.unavailable'), 'empty'); return; }
    const tasks = this._config.task_view === 'completed' ? [] : this.filteredTasks(state);
    for (const task of this._completed.values()) if (this._config.task_view !== 'completed' && !tasks.some(item => item.task_id === task.task_id) && this.filteredTasks({attributes:{tasks:[task]}}).length) tasks.push(task);
    tasks.sort((a,b) => compareTasks(a,b,this._config.sort_by,this._hass.locale?.language));
    if (!tasks.length && this._config.task_view !== 'completed') addText(card, 'p', emptyMessage({...this._config,user_id:userId}, member?.display_name || member?.username || t('common.user', {id: userId}), t), 'empty');
    for (const task of tasks) {
      const row = document.createElement('div'); row.className = 'row'; card.append(row);
      const completed = this._completed.has(task.task_id);
      if (completed) row.classList.add('completed');
      if (this._config.show_complete && this._config.complete_control === 'checkbox') {
        const target = document.createElement('label'); target.className = 'complete-checkbox'; row.append(target);
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
        checkbox.disabled = this._pending.has(task.task_id) || completed; checkbox.checked = this._pending.get(task.task_id) === true || completed;
        checkbox.setAttribute('aria-label', onTask(t('todo.complete'), task));
        checkbox.title = onTask(t('todo.complete'), task);
        checkbox.addEventListener('change', () => this.act(task, true)); target.append(checkbox);
      }
      const hasDescription = !!descriptionText(task.description);
      const text = document.createElement(hasDescription ? 'button' : 'div'); text.className = 'task'; row.append(text);
      if (hasDescription) {
      text.type = 'button';
      text.dataset.action = 'details'; text.dataset.taskId = task.task_id;
      text.title = onTask(t('todo.show_description'), task);
      text.setAttribute('aria-label', text.title);
      text.setAttribute('aria-expanded', String(this._panel?.taskId === task.task_id && this._panel.kind === 'details'));
      text.setAttribute('aria-controls', `description-${task.task_id}`);
      text.addEventListener('click', () => this.togglePanel(task, 'details'));
      text.addEventListener('keydown', event => { if (event.key === 'Escape' && this._panel?.kind === 'details') { event.stopPropagation(); this.closePanel(); } });
      }
      const name = addText(text, 'span', task.name, 'name');
      if (this._config.show_points && Number.isFinite(task.points)) {
        const label = t('common.points', {count: task.points});
        const badge = addText(name, 'span', String(task.points), 'task-points');
        badge.title = t('todo.task_value', {label}); badge.setAttribute('aria-label', label);
        const star = document.createElement('ha-icon'); star.setAttribute('icon', 'mdi:star-outline');
        star.setAttribute('aria-hidden', 'true'); badge.prepend(star);
      }
      if (hasDescription) {
        const indicator = document.createElement('ha-icon'); indicator.className = 'description-indicator';
        indicator.setAttribute('icon', this._panel?.taskId === task.task_id && this._panel.kind === 'details' ? 'mdi:chevron-up' : 'mdi:chevron-down');
        indicator.setAttribute('aria-hidden', 'true'); name.append(indicator);
      }
      const dateOnly = typeof task.next_due_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(task.next_due_date);
      const due = task.next_due_date ? new Date(dateOnly ? `${task.next_due_date}T12:00:00` : task.next_due_date) : null;
      const dueLabel = addText(text, 'span', dueText(task.next_due_date, this._hass.locale?.language, new Date(), this._hass.locale?.time_format, this._config.due_display, t), 'due');
      if (!completed && isOverdue(task.next_due_date)) dueLabel.classList.add('overdue');
      if (due && !isNaN(due)) {
        const clock = document.createElement('ha-icon'); clock.className = 'due-clock';
        clock.setAttribute('icon', 'mdi:clock'); clock.setAttribute('aria-hidden', 'true'); dueLabel.prepend(clock);
      }
      if (due && !isNaN(due)) dueLabel.title = due.toLocaleString(this._hass.locale?.language, {dateStyle:'full',timeStyle:hasDueTime(task.next_due_date) ? 'short' : undefined});
      const recurrence = this._config.show_recurrence ? recurrenceText(task, t) : '';
      if (!recurrence && (task.is_recurring ?? task.can_postpone)) {
        const recurring = document.createElement('ha-icon'); recurring.className = 'recurring';
        recurring.setAttribute('icon', 'mdi:autorenew'); recurring.title = t('todo.recurring');
        recurring.setAttribute('role', 'img'); recurring.setAttribute('aria-label', t('todo.recurring'));
        dueLabel.prepend(recurring);
      }
      if (this._config.show_assignee && (userId !== 'all' && this._config.include_anyone || userId === 'all' && state.attributes.circle_members?.length > 1)) {
        const assignee = state.attributes.circle_members.find(member => member.user_id === task.assigned_to);
        const name = assignee?.display_name || assignee?.username || (task.assigned_to ? t('common.user', {id: task.assigned_to}) : t('common.anyone'));
        const label = addText(dueLabel, 'span', `· ${name}`, 'assignee'); label.title = t('todo.assigned_to', {name});
      }
      if (recurrence) {
        const label = addText(text, 'span', recurrence, 'task-recurrence'); label.title = recurrence;
        const icon = document.createElement('ha-icon'); icon.setAttribute('icon', 'mdi:autorenew');
        icon.setAttribute('aria-hidden', 'true'); label.prepend(icon);
      }
      if (this._config.show_labels) {
        const labels = taskLabels(task.labels);
        if (labels.length) {
          row.classList.add('has-labels'); card.dataset.labels = 'true';
          const chips = document.createElement('span'); chips.className = 'task-labels'; text.append(chips);
          for (const label of labels) {
            const chip = addText(chips, 'span', label, 'task-label');
            const colors = this._config.use_label_colors ? labelColors(task.labels, label) : null;
            if (colors) Object.assign(chip.style, colors);
          }
        }
      }
      const actions = document.createElement('div'); actions.className = 'actions'; row.append(actions);
      for (const [label, complete] of [[this._config.complete_label || t('todo.complete'), true], [this._config.postpone_label || t('todo.skip'), false]]) {
        if (complete && (!this._config.show_complete || this._config.complete_control === 'checkbox')) continue;
        if (!complete && (!this._config.show_postpone || !task.can_postpone)) continue;
        const button = document.createElement('button'); actions.append(button); button.type = 'button';
        button.disabled = this._pending.has(task.task_id) || completed;
        if (this._config.button_content !== 'label') {
          const icon = document.createElement('ha-icon'); icon.setAttribute('icon', this._config[complete ? 'complete_icon' : 'postpone_icon'] || (complete ? 'mdi:check' : 'mdi:calendar-arrow-right'));
          button.append(icon);
        }
        if (this._config.button_content !== 'icon') button.append(document.createTextNode(label));
        const color = actionColor(this._config[complete ? 'complete_color' : 'postpone_color']);
        if (color) button.style.setProperty(this._config.button_style === 'filled' ? 'background-color' : 'color', color);
        button.title = onTask(label, task);
        button.setAttribute('aria-label', button.title);
        if (!complete) { button.dataset.action = 'skip'; button.dataset.taskId = task.task_id; button.setAttribute('aria-expanded', String(this._panel?.taskId === task.task_id && this._panel.kind === 'skip')); }
        button.addEventListener('click', () => complete ? this.act(task, true) : this.togglePanel(task, 'skip'));
      }
      if (this._config.show_due_date) {
      const changeDate = document.createElement('button'); changeDate.type = 'button';
      changeDate.className = 'date-action';
      const dateLabel = this._config.due_date_label || t('todo.change_due');
      if (this._config.button_content !== 'label') {
        const icon = document.createElement('ha-icon'); icon.setAttribute('icon', this._config.due_date_icon || 'mdi:calendar-edit'); changeDate.append(icon);
      }
      if (this._config.button_content !== 'icon') changeDate.append(document.createTextNode(dateLabel));
      const dueColor = actionColor(this._config.due_date_color);
      if (dueColor) changeDate.style.setProperty(this._config.button_style === 'filled' ? 'background-color' : 'color', dueColor);
      changeDate.disabled = this._pending.has(task.task_id) || completed;
      changeDate.title = onTask(dateLabel, task); changeDate.setAttribute('aria-label', changeDate.title);
      changeDate.dataset.action = 'date'; changeDate.dataset.taskId = task.task_id;
      changeDate.setAttribute('aria-expanded', String(this._panel?.taskId === task.task_id && this._panel.kind === 'date'));
      changeDate.addEventListener('click', () => this.togglePanel(task, 'date')); actions.append(changeDate);
      }
      if (this._config.show_reassign) {
        const reassign = document.createElement('button'); reassign.type = 'button';
        const label = this._config.reassign_label || t('todo.reassign');
        if (this._config.button_content !== 'label') {
          const icon = document.createElement('ha-icon'); icon.setAttribute('icon', this._config.reassign_icon || 'mdi:account-switch-outline'); reassign.append(icon);
        }
        if (this._config.button_content !== 'icon') reassign.append(document.createTextNode(label));
        const color = actionColor(this._config.reassign_color);
        if (color) reassign.style.setProperty(this._config.button_style === 'filled' ? 'background-color' : 'color', color);
        reassign.disabled = this._pending.has(task.task_id) || completed;
        reassign.title = onTask(label, task); reassign.setAttribute('aria-label', reassign.title);
        reassign.dataset.action = 'assign'; reassign.dataset.taskId = task.task_id;
        reassign.setAttribute('aria-expanded', String(this._panel?.taskId === task.task_id && this._panel.kind === 'assign'));
        reassign.addEventListener('click', () => this.togglePanel(task, 'assign')); actions.append(reassign);
      }
      if (!actions.childElementCount) actions.remove();
      if (this._panel?.taskId === task.task_id) this.renderPanel(row, task, addText);
    }
    if (this._config.task_view !== 'pending') {
      const history = completedTasks(state, this._config.user_id, new Date(), this._config);
      const days = Number(this._config.completed_days);
      const suffix = days === 1 ? 'today' : 'days';
      addText(card, 'h3', t('todo.history_heading', {period: t(`todo.completed_${suffix}`, {days}), count: history.length}), 'history-heading');
      if (!history.length) addText(card, 'p', t(`todo.none_${this._config.completed_filter === 'matching' ? 'matching_' : ''}${suffix}`, {days}), 'empty');
      for (const task of history) {
        const row = document.createElement('div'); row.className = 'row completed history-row'; row.dataset.uid = task.uid; card.append(row);
        const check = document.createElement('ha-icon'); check.className = 'history-check'; check.setAttribute('icon','mdi:check-circle-outline'); check.setAttribute('aria-label',t('todo.completed')); row.append(check);
        const text = document.createElement('div'); text.className = 'task'; row.append(text);
        addText(text, 'span', task.name, 'name');
        const performer = state.attributes.circle_members?.find(member => member.user_id === task.completed_by);
        const name = performer?.display_name || performer?.username || (task.completed_by ? t('common.user', {id: task.completed_by}) : t('common.unknown_user'));
        const time = Number(this._config.completed_days) > 1
          ? new Date(task.completed_at).toLocaleString(this._hass.locale?.language, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:this._hass.locale?.time_format === '12' ? true : this._hass.locale?.time_format === '24' ? false : undefined})
          : new Date(task.completed_at).toLocaleTimeString(this._hass.locale?.language, {hour:'2-digit', minute:'2-digit', hour12:this._hass.locale?.time_format === '12' ? true : this._hass.locale?.time_format === '24' ? false : undefined});
        addText(text, 'span', `${time} · ${name}`, 'due');
      }
    }
    if (focusedField) this.shadowRoot.querySelector(`[data-field="${focusedField}"]`)?.focus();
  }
  renderPanel(row, task, addText) {
    const panel = this._panel;
    if (panel.kind === 'details') {
      const content = descriptionText(task.description);
      if (!content) { this._panel = null; return; }
      const description = document.createElement('div'); description.className = 'description';
      description.id = `description-${task.task_id}`;
      description.textContent = content;
      row.after(description); return;
    }
    const t = (key, values) => this.t(key, values);
    const busy = this._pending.has(task.task_id);
    const form = document.createElement('form'); form.className = 'action-panel'; row.after(form);
    const controls = document.createElement('div'); controls.className = 'panel-actions';
    const draftDate = () => {
      const value = `${panel.date}T${panel.time}`;
      const date = new Date(value);
      return !isNaN(date) && localDateTime(date) === (value.length === 16 ? value + ':00' : value) ? date : null;
    };
    const changed = () => panel.kind === 'skip' || (panel.kind === 'assign'
      ? panel.assignedTo !== (task.assigned_to ?? null)
      : draftDate() && (!task.next_due_date || localDateTime(draftDate()) !== localDateTime(task.next_due_date)));
    let save;
    const updateSave = () => {
      if (!save) return;
      save.disabled = busy || !changed() || (panel.kind === 'assign' && panel.assignedTo !== null && !assignableMembers(this._hass.states[this._config.entity], task).some(member => member.user_id === panel.assignedTo));
    };
    form.setAttribute('aria-label', t('common.on_task', {action: t(panel.kind === 'date' ? 'todo.change_due' : panel.kind === 'assign' ? 'todo.reassign' : 'todo.skip'), task: task.name}));
    const iconButton = (label, icon, handler) => {
      const node=document.createElement('button'); node.type='button'; node.disabled=busy;
      node.title=label; node.setAttribute('aria-label',label); node.dataset.field=`control-${label}`;
      const glyph=document.createElement('ha-icon'); glyph.setAttribute('icon',icon); node.append(glyph);
      if (handler) node.addEventListener('click',handler); controls.append(node); return node;
    };
    const field = (type, label, value, handler) => {
      const input=document.createElement('input'); input.type=type; input.required=true;
      input.value=value; input.disabled=busy; input.dataset.field=type;
      input.style.colorScheme=this._hass.themes?.darkMode ? 'dark' : 'light';
      input.setAttribute('aria-label',label); input.title=label;
      input.addEventListener('input',handler); form.append(input); return input;
    };
    if (panel.kind === 'date') {
      if (customElements.get('ha-form')) {
        form.classList.add('date-panel');
        const fields = document.createElement('ha-form'); fields.dataset.field = 'date-fields';
        fields.dataset.withTime = String(panel.showTime);
        fields.setAttribute('aria-label', t('todo.due_date_time'));
        fields.hass = this._hass; fields.disabled = busy;
        fields.computeLabel = schema => schema.name === 'date' ? t('todo.due_date') : '';
        fields.schema = [{name:'',type:'grid',column_min_width:'150px',schema:[
          // Save validates the date below; omitting required avoids HA's empty hint row.
          {name:'date',selector:{date:{}}},
          ...(panel.showTime ? [{name:'time',required:true,selector:{time:{no_second:true}}}] : [])
        ]}];
        fields.data = {date:panel.date,time:panel.time};
        fields.addEventListener('value-changed', event => {
          event.stopPropagation();
          const values = event.detail.value;
          if ('date' in values) panel.date = values.date || '';
          if ('time' in values) panel.time = values.time || '';
          updateSave();
          if (!fields.isConnected) this.render();
        });
        form.append(fields);
      } else {
      field('date',t('todo.due_date'),panel.date,event => { panel.date=event.target.value; updateSave(); });
      if (panel.showTime) {
        const input=field('time',t('todo.time_zone', {zone: Intl.DateTimeFormat().resolvedOptions().timeZone}),panel.time,event => { panel.time=event.target.value; updateSave(); }); input.step='1';
      }
      }
      const time=iconButton(t(panel.showTime ? 'todo.hide_time' : 'todo.set_time'),'mdi:clock-outline', () => { panel.showTime=!panel.showTime; this.render(); });
      time.setAttribute('aria-expanded',String(panel.showTime));
    } else if (panel.kind === 'assign') {
      const state = this._hass.states[this._config.entity];
      const members = assignableMembers(state, task);
      const select = document.createElement('select'); select.required = true; select.disabled = busy;
      select.style.colorScheme = this._hass.themes?.darkMode ? 'dark' : 'light';
      select.dataset.field = 'assignee'; select.setAttribute('aria-label', t('todo.assigned_user'));
      const anyone = document.createElement('option'); anyone.value = 'anyone'; anyone.textContent = t('common.anyone'); select.append(anyone);
      for (const member of members) {
        const option = document.createElement('option'); option.value = String(member.user_id); option.textContent = member.display_name || member.username || t('common.user', {id: member.user_id}); select.append(option);
      }
      select.value = panel.assignedTo === null ? 'anyone' : String(panel.assignedTo);
      select.addEventListener('change', event => { panel.assignedTo = event.target.value === 'anyone' ? null : Number(event.target.value); updateSave(); }); form.append(select);
    } else addText(form,'span',t('todo.skip_prompt'), 'skip-prompt');
    save = document.createElement('button'); save.type = 'submit'; save.className = 'save-action';
    const saveIcon = document.createElement('ha-icon');
    saveIcon.setAttribute('icon', panel.kind === 'skip' ? 'mdi:skip-next-outline' : 'mdi:content-save-outline');
    save.append(saveIcon);
    save.setAttribute('aria-label', t(panel.kind === 'date' ? 'todo.save_due' : panel.kind === 'assign' ? 'todo.save_assignee' : 'todo.confirm_skip'));
    save.title = save.getAttribute('aria-label');
    controls.append(save); updateSave();
    form.append(controls);
    if (this._error) { const error=addText(form,'p',this._error,'error'); error.setAttribute('role','alert'); }
    form.addEventListener('keydown',event => { if (event.key === 'Escape' && !busy) { event.stopPropagation(); this.closePanel(); } });
    form.addEventListener('submit',event => {
      event.preventDefault(); if (busy || !form.reportValidity() || form.querySelector('ha-form')?.reportValidity?.() === false) return;
      if (panel.kind === 'skip') { this.act(task,false); return; }
      if (panel.kind === 'assign') {
        if (panel.assignedTo !== null && !assignableMembers(this._hass.states[this._config.entity], task).some(member => member.user_id === panel.assignedTo)) { this._error = t('todo.choose_assignee'); this.render(); return; }
        if (!changed()) return;
        this.act(task, false, undefined, panel.assignedTo); return;
      }
      const date = draftDate();
      if (!date) { this._error=t('todo.choose_date'); this.render(); return; }
      if (!changed()) return;
      this.act(task,false,date.toISOString());
    });
  }
}
const EDITOR_DEFAULTS = {
  task_view:'both',
  completed_days:1, completed_filter:'all', completed_limit:0,
  row_spacing:'auto',
  display_filters:[], label_match:'any', sort_by:'due_date', upcoming_days:7, include_anyone:false, due_display:'date', show_labels:false, show_points:false, show_recurrence:false, use_label_colors:false, show_assignee:true, show_complete:true, show_postpone:true, show_due_date:true, show_reassign:true, complete_control:'checkbox', button_style:'text', button_size:'compact',
  button_shape:'rounded', button_content:'icon', complete_icon:'mdi:check', postpone_icon:'mdi:calendar-arrow-right',
  due_date_icon:'mdi:calendar-edit', reassign_icon:'mdi:account-switch-outline', complete_color:'primary', postpone_color:'primary', due_date_color:'primary', reassign_color:'primary'
};
const STYLE_PRESETS = {
  todo:{complete_control:'checkbox',button_style:'text',button_size:'compact',button_shape:'rounded',button_content:'icon'},
  labeled:{complete_control:'checkbox',button_style:'text',button_size:'compact',button_shape:'rounded',button_content:'icon_and_label'},
  outlined:{complete_control:'checkbox',button_style:'outlined',button_size:'normal',button_shape:'rounded',button_content:'icon'},
  filled:{complete_control:'checkbox',button_style:'filled',button_size:'normal',button_shape:'rounded',button_content:'icon'}
};
const ACTION_OVERRIDES = ['complete','postpone','due_date','reassign'].flatMap(action=>['label','icon','color'].map(part=>`${action}_${part}`));
// Action labels follow the editor's language, so they are not fixed defaults.
const actionLabels = t => ({complete_label:t('todo.complete'), postpone_label:t('todo.skip'), due_date_label:t('todo.change_due'), reassign_label:t('todo.reassign')});
export function actionColor(value) {
  if (!value || value === 'none') return null;
  if (value === 'primary' || value === 'accent') return `var(--${value}-color)`;
  if (/^[a-z]+(?:-[a-z]+)?$/.test(value)) return `var(--${value}-color, ${value})`;
  return value;
}
class HoplaUserTodoEditor extends HTMLElement {
  constructor() {
    super(); this.attachShadow({mode:'open'});
    this._expandedGroups=new Map();this._groupSchemas=new Map();
    this.shadowRoot.addEventListener('expanded-will-change',event=>{
      const group=event.composedPath().find(node=>node.localName==='ha-form-expandable');
      const name=group?.schema?.name;
      if (!this._groupSchemas.has(name) || typeof event.detail?.expanded !== 'boolean') return;
      this._expandedGroups.set(name,event.detail.expanded);
      this.render();
    });
  }
  connectedCallback() { this.ensureForm(); }
  async ensureForm() {
    if (customElements.get('ha-form') || this._loading) return;
    this._loading=true;
    try {
      const helpers=await window.loadCardHelpers();
      const card=await helpers.createCardElement({type:'entities',entities:[]});
      await card.constructor.getConfigElement();
      if (!customElements.get('ha-form')) throw new Error('HA form controls are unavailable');
      this._loadError='';
    } catch { this._loadError=this.t('editor.load_error'); }
    finally { this._loading=false; this.render(); }
  }
  setConfig(config) {
    if (JSON.stringify(config) === JSON.stringify(this._config)) return;
    this._config={...config}; this.render();
  }
  set hass(hass) {
    const previous = this._hass;
    const lists = Object.entries(hass.states).filter(([id,state])=>id.startsWith('todo.') && state.attributes.circle_members);
    const unchanged = previous && previous !== hass && samePresentation(previous,hass)
      && previous.entities === hass.entities && previous.devices === hass.devices && previous.areas === hass.areas
      && this._editorLists?.length === lists.length
      && lists.every(([id,state],index)=>this._editorLists[index][0] === id && this._editorLists[index][1] === state);
    this._hass=hass; this._editorLists=lists;
    if (!unchanged) this.render();
  }
  t(key, values) { return elementTranslator(this)(key, values); }
  preset() {
    const defaults={...EDITOR_DEFAULTS,...actionLabels(this.t.bind(this))};
    if (ACTION_OVERRIDES.some(key=>this._config[key] && this._config[key] !== defaults[key])) return 'custom';
    return Object.keys(STYLE_PRESETS).find(name=>Object.entries(STYLE_PRESETS[name]).every(([key,value])=>(this._config[key] ?? EDITOR_DEFAULTS[key])===value)) || 'custom';
  }
  formChanged(event) {
    event.stopPropagation();
    const values=event.detail.value;
    const config={...this._config};
    for (const [key,value] of Object.entries(values)) {
      if (key==='appearance_preset' || JSON.stringify(value)===JSON.stringify(this._formData[key])) continue;
      if (key==='display_filters') {
        config.display_filters=value || [];
        delete config.display_filter;
        delete config.include_overdue;
      }
      // Preserve an explicitly cleared editable field across HA's setConfig
      // feedback so displayed defaults do not interrupt typing a replacement.
      else if ((['upcoming_days','completed_days','completed_limit'].includes(key) || ACTION_OVERRIDES.includes(key)) && (value==='' || value===undefined || value===null)) config[key]=null;
      else if (value==='' || value===undefined || value===null) delete config[key];
      else config[key]=key==='user_id' && value !== 'all' ? Number(value) : value;
    }
    if (values.appearance_preset !== this._formData.appearance_preset && STYLE_PRESETS[values.appearance_preset]) {
      Object.assign(config,STYLE_PRESETS[values.appearance_preset]);
      for (const key of ACTION_OVERRIDES) delete config[key];
    }
    const state=this._hass.states[config.entity];
    if (state?.attributes.hopla_user_id !== undefined) config.user_id=state.attributes.hopla_user_id;
    else if (config.entity !== this._config.entity) {
      const members=state?.attributes.circle_members || [];
      if (config.user_id !== 'all' && !members.some(member=>member.user_id===config.user_id)) {
        if (members.length) config.user_id=members[0].user_id;
        else delete config.user_id;
      }
    }
    if (JSON.stringify(config) === JSON.stringify(this._config)) return;
    this._config=config;
    this.dispatchEvent(new CustomEvent('config-changed',{detail:{config},bubbles:true,composed:true}));
    this.render();
  }
  render() {
    if (!this._hass || !this._config) return;
    if (!customElements.get('ha-form')) {
      this.shadowRoot.textContent=this._loadError || this.t('editor.loading');
      if (!this._loadError) this.ensureForm();
      return;
    }
    if (!this._form) {
      this.shadowRoot.innerHTML='<style>:host{display:block}ha-form{display:block}ha-alert{display:block;margin-bottom:16px}ha-alert[hidden]{display:none}</style>';
      this._warning=document.createElement('ha-alert');this._warning.setAttribute('alert-type','info');this.shadowRoot.append(this._warning);
      this._form=document.createElement('ha-form');this.shadowRoot.append(this._form);
      // A missing text comes back as its key, which means there is no label or help.
      const text=(key,fallback)=>{ const value=this.t(key); return value===key ? fallback : value; };
      this._form.computeLabel=schema=>schema.title || this._actionLabels?.[schema.name] || text(`editor.labels.${schema.name}`,schema.name);
      this._form.computeHelper=schema=>text(`editor.help.${schema.name}`) || (schema.name.endsWith('_color') ? this.t('editor.help.color') : schema.name.endsWith('_icon') ? this.t('editor.help.icon') : schema.name.endsWith('_label') ? this.t('editor.help.label') : undefined);
      this._form.addEventListener('value-changed',event=>this.formChanged(event));
    }
    const entities=Object.keys(this._hass.states).filter(id=>id.startsWith('todo.') && this._hass.states[id].attributes.circle_members);
    const members=this._hass.states[this._config.entity]?.attributes.circle_members || [];
    const owner=this._hass.states[this._config.entity]?.attributes.hopla_user_id;
    const filters=dateFilters(this._config);
    // Keep selected names available when no current task has that label.
    const attributes=this._hass.states[this._config.entity]?.attributes || {};
    const labels=[...new Set([...[...(attributes.tasks || []),...(attributes.anyone_tasks || []),...(attributes.completed_tasks || [])].flatMap(task=>taskLabels(task.labels)), ...taskLabels(this._config.labels)])]
      .sort((a,b)=>a.localeCompare(b,this._hass.locale?.language));
    this._warning.hidden=owner !== undefined || !!members.length;
    this._warning.textContent=this.t('editor.no_members');
    const t=(key,values)=>this.t(key,values);
    const option=key=>t(`editor.options.${key}`);
    const select=(name,options)=>({name,selector:{select:{mode:'dropdown',options:options.map(([value,label])=>({value,label}))}}});
    const choices=(name,prefix,values)=>select(name,values.map(value=>[value,option(`${prefix}_${value}`)]));
    this._groupSchemas.clear();
    const group=(name,schema)=>{
      const title=t(`editor.groups.${name}`);
      const expanded=this._expandedGroups.get(name) ?? ['basics','filters'].includes(name);
      this._groupSchemas.set(name,schema);
      // HA creates nested forms even in collapsed panels. Keep expensive
      // selectors unmounted until opened, and remove them again when closed.
      return {name,title,type:'expandable',flatten:true,expanded,schema:expanded ? schema : []};
    };
    const hasPending = this._config.task_view !== 'completed';
    const hasCompleted = this._config.task_view !== 'pending';
    const matchesCompleted = hasCompleted && this._config.completed_filter === 'matching';
    const labelFields = [
      {name:'labels',selector:{select:{mode:'dropdown',multiple:true,options:labels.map(label=>({value:label,label}))}}},
      ...(taskLabels(this._config.labels).length > 1 ? [choices('label_match','match',['any','all'])] : [])
    ];
    this._actionLabels={};
    const actionGroup=(action,title)=>{
      const fields=[{name:`${action}_icon`,selector:{icon:{}}},{name:`${action}_label`,selector:{text:{}}},{name:`${action}_color`,selector:{ui_color:{default_color:'primary'}}}];
      fields.forEach((field,index)=>{this._actionLabels[field.name]=t('editor.labels.action_part',{action:title,part:t(`editor.labels.${['icon','label','color'][index]}`)});});
      return {name:action,type:'grid',flatten:true,column_min_width:'150px',schema:fields};
    };
    const actionFields=[
      ...(this._config.show_complete !== false && this._config.complete_control==='button' ? [actionGroup('complete',t('editor.labels.show_complete'))] : []),
      ...(this._config.show_postpone !== false ? [actionGroup('postpone',t('editor.labels.show_postpone'))] : []),
      ...(this._config.show_due_date !== false ? [actionGroup('due_date',t('editor.labels.show_due_date'))] : []),
      ...(this._config.show_reassign !== false ? [actionGroup('reassign',t('editor.labels.show_reassign'))] : [])
    ];
    const schema=[
      {...group('basics',[
      {name:'entity',required:true,selector:{entity:{include_entities:entities,filter:{domain:'todo'}}}},
      ...(owner === undefined ? [{...select('user_id',[...(members.length > 1 ? [['all',option('all_users')]] : []), ...members.map(member=>[String(member.user_id),member.display_name || member.username || t('common.user',{id:member.user_id})])]),required:true,disabled:!members.length}] : []),
      ...(hasPending && selectedUser(this._hass.states[this._config.entity], this._config.user_id) !== 'all' ? [{name:'include_anyone',selector:{boolean:{}}}] : []),
      {name:'title',selector:{text:{}}},
      choices('task_view','view',['both','pending','completed'])
      ])},
      {...group('filters',[
      ...labelFields,
      ...(hasPending || matchesCompleted ? [
      {name:'display_filters',title:t(hasPending ? 'editor.labels.display_filters' : 'editor.labels.original_due_dates'),selector:{select:{mode:'dropdown',multiple:true,options:['overdue','today','future','undated'].map(value=>({value,label:t(`todo.filters.${value}`)}))}}},
      ...(filters.includes('future') ? [{name:'upcoming_days',selector:{number:{min:0,max:365,step:1,mode:'box',unit_of_measurement:t('editor.days')}}}] : [])
      ] : []),
      ...(hasPending ? [choices('sort_by','sort',['due_date','priority','name'])] : [])
      ])},
      ...(hasCompleted ? [group('completed_options',[
        {name:'completed_days',selector:{number:{min:1,max:7,step:1,mode:'box',unit_of_measurement:t('editor.days')}}},
        choices('completed_filter','completed',['all','matching']),
        {name:'completed_limit',selector:{number:{min:0,max:500,step:1,mode:'box'}}}
      ])] : []),
      ...(hasPending ? [group('display_options',[
      ...(selectedUser(this._hass.states[this._config.entity], this._config.user_id) !== 'all' && this._config.include_anyone || this._config.user_id === 'all' && !this._hass.states[this._config.entity]?.attributes.hopla_user_id && members.length > 1 ? [{name:'show_assignee',selector:{boolean:{}}}] : []),
      choices('due_display','due',['date','relative','both']),
      ...['show_labels',...(this._config.show_labels ? ['use_label_colors'] : []),'show_points','show_recurrence'].map(name=>({name,selector:{boolean:{}}}))
      ])] : []),
      ...(hasPending ? [group('actions_options',[
        ...['show_complete','show_postpone','show_due_date','show_reassign'].map(name=>({name,selector:{boolean:{}}}))
      ])] : []),
      ...(hasPending ? [group('appearance',[
        choices('appearance_preset','preset',['todo','labeled','outlined','filled','custom']),
        choices('row_spacing','spacing',['auto','compact','comfortable']),
        ...(this._config.show_complete !== false ? [choices('complete_control','control',['checkbox','button'])] : []),
        choices('button_content','content',['icon','icon_and_label','label']),
        choices('button_style','style',['text','outlined','filled']),
        choices('button_size','size',['compact','normal','large']),
        choices('button_shape','shape',['rounded','pill','square'])
      ])] : []),
      ...(hasPending && actionFields.length ? [group('customization_options',actionFields)] : [])
    ];
    const signature=JSON.stringify(schema);
    if (signature!==this._schemaSignature) {this._schemaSignature=signature;this._form.schema=schema;}
    const formData={...EDITOR_DEFAULTS,...actionLabels(t),...this._config,display_filters:filters,labels:taskLabels(this._config.labels),user_id:String(owner ?? this._config.user_id ?? 'all'),appearance_preset:this.preset()};
    const dataSignature=JSON.stringify(formData);
    if (this._form.hass !== this._hass) this._form.hass=this._hass;
    if (dataSignature !== this._formDataSignature) {
      this._formDataSignature=dataSignature;this._formData=formData;this._form.data=formData;
    }
  }
}
if (!customElements.get('hopla-user-todo-card')) customElements.define('hopla-user-todo-card', HoplaUserTodoCard);
if (!customElements.get('hopla-user-todo-editor')) customElements.define('hopla-user-todo-editor', HoplaUserTodoEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === 'hopla-user-todo-card')) {
  const t = translator(browserLanguage());
  window.customCards.push({type: 'hopla-user-todo-card', name: t('todo.card_name'), description: t('todo.card_description')});
}
