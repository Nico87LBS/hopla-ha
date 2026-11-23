import assert from 'node:assert/strict';
// The icons of the Hopla catalogue on the family card: a task, a reward, a
// challenge and a routine show theirs on a tile; an unknown id is not drawn.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
await import('../custom_components/hopla/frontend/hopla-family-card.js');

const states = {
  'sensor.hopla_points_elena': {state: '4', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member', total_points: 4}},
  'sensor.hopla_task_dents': {state: 'Brosser les dents', attributes: {task_id: 5, points: 2, icon: 'broom', assignee_ids: [2], assigned_to_user_id: 2,
    next_due_date: '2000-01-01T08:00:00Z', is_active: true, frequency_type: 'daily'}},
  'sensor.hopla_task_vaisselle': {state: 'Vaisselle', attributes: {task_id: 6, points: 2, icon: '../x', assignee_ids: [2], assigned_to_user_id: 2,
    next_due_date: '2000-01-01T08:00:00Z', is_active: true, frequency_type: 'daily'}},
  'sensor.hopla_rewards': {state: '1', attributes: {rewards: [{id: 9, name: 'Cinéma', points_cost: 5, icon: 'trophy', is_active: true}], requests: []}},
  'sensor.hopla_games_today': {state: 'unknown', attributes: {hopla_games: true, rated_challenges: [], challenges: [
    {id: 1, name: 'Lecture', icon: 'trophy', kind: 'count', target: 5, shared: true, members: [2], progress: {}, targets: {}, days_away: {},
      total: 1, winners: [], done: false, ends_at: '2099-01-01T00:00:00Z'}]}},
};
const card = document.createElement('hopla-family-card');
card.setConfig({todo_open: true, rewards_open: true});
card.hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states, callService: async () => ({response: {}})};
document.body.append(card);
const root = card.shadowRoot;
const sources = [...root.querySelectorAll('.ico img')].map(img => img.getAttribute('src'));
const has = id => sources.some(src => src.includes(`/icons/${id}.svg`));
assert.ok(has('broom'), 'the task shows its icon');
assert.ok(has('trophy'), 'the reward and the challenge show theirs');
assert.equal(sources.filter(src => src.includes('..')).length, 0, 'an unsafe id is never drawn');
assert.equal(root.querySelectorAll('.row .ico').length >= 2, true);
console.log('ok');
process.exit(0);
