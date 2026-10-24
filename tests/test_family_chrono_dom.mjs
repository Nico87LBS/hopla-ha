import assert from 'node:assert/strict';
// A parent starts a speed bonus from the family tablet: the parent code first.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
await import('../custom_components/hopla/frontend/hopla-family-card.js');

const calls = [];
const soon = minutes => new Date(Date.now() + minutes * 60000).toISOString();
const states = {
  'sensor.hopla_points_elena': {state: '0', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member'}},
  'sensor.chambre': {state: 'Chambre', attributes: {task_id: 7, is_active: true, assignee_ids: [2], assigned_to_user_id: 2, points: 3,
    next_due_date: soon(5), chrono: {points: 5, ends_at: soon(12), live_id: 4}}},
  'sensor.chat': {state: 'Chat', attributes: {task_id: 8, is_active: true, assignee_ids: [2], assigned_to_user_id: 2, points: 1,
    next_due_date: soon(60)}},
  'binary_sensor.hopla_parent_mode': {state: 'off', attributes: {hopla_parent_mode: true, config_entry_id: 'entry', enabled: true,
    has_pin: true, parent_users: ['nico'], unlocked_until: null}},
};
const hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states,
  callService: async (...args) => { calls.push(args); return {response: {}}; }};
const show = user => {
  const card = document.createElement('hopla-family-card');
  card.setConfig({show_points: false});
  card.hass = {...hass, user: {id: user}};
  document.body.append(card);
  return card;
};
let card = show('tablet');
let root = card.shadowRoot;
const click = selector => root.querySelector(selector).dispatchEvent(new window.MouseEvent('click', {bubbles: true, composed: true}));
const settle = () => new Promise(resolve => setTimeout(resolve, 0));

const chip = root.querySelector('span.chrono');
assert.ok(chip, 'the children see the speed bonus');
assert.match(chip.textContent, /\+5 · 12 min/);
assert.equal(root.querySelector('[data-action="chrono-open"]'), null, 'but cannot start one');

// A parent on their own account starts one on another task.
card.remove();
card = show('nico');
root = card.shadowRoot;
click('[data-action="chrono-open"][data-task="8"]');
await settle();
click('[data-action="chrono-points"][data-value="10"]');
click('[data-action="chrono-minutes"][data-value="30"]');
click('[data-action="chrono-start"]');
await settle();
assert.deepEqual(calls.at(-1).slice(1, 3), ['start_chrono', {task_id: 8, points: 10, minutes: 30}]);
assert.equal(root.querySelector('.chrono-choices'), null, 'the window closes');

// The running one can be stopped.
click('[data-action="chrono-open"][data-task="7"]');
await settle();
assert.match(root.querySelector('.chrono-live').textContent, /\+5 points/);
click('[data-action="chrono-stop"]');
await settle();
assert.deepEqual(calls.at(-1).slice(1, 3), ['stop_chrono', {task_id: 7}]);
card.remove();
console.log('ok');
