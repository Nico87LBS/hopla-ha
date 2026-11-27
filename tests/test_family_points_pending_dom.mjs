import assert from 'node:assert/strict';
// The hops of a task made by a child wait for a parent: the family card tags
// that task, and only that one.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
await import('../custom_components/hopla/frontend/hopla-family-card.js');

const states = {
  'sensor.hopla_points_elena': {state: '4', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member', total_points: 4, hops_pending: 12}},
  'sensor.hopla_points_anna': {state: '9', attributes: {hopla_member_id: 3, display_name: 'Anna', role: 'member', total_points: 9, hops_pending: 0}},
  'sensor.hopla_task_dents': {state: 'Brosser les dents', attributes: {task_id: 5, points: 2, points_pending: true, assignee_ids: [2], assigned_to_user_id: 2,
    next_due_date: '2000-01-01T08:00:00Z', is_active: true, frequency_type: 'daily'}},
  'sensor.hopla_task_vaisselle': {state: 'Vaisselle', attributes: {task_id: 6, points: 2, points_pending: false, assignee_ids: [2], assigned_to_user_id: 2,
    next_due_date: '2000-01-01T08:00:00Z', is_active: true, frequency_type: 'daily'}},
};
const card = document.createElement('hopla-family-card');
card.setConfig({todo_open: true});
card.hass = {user: {id: 'tablet'}, language: 'fr', locale: {language: 'fr'}, states, callService: async () => ({response: {}})};
document.body.append(card);
const rows = [...card.shadowRoot.querySelectorAll('.row')];
const tagged = rows.filter(row => row.querySelector('.pts-wait'));
assert.equal(tagged.length, 1, 'only the task with waiting hops is tagged');
assert.match(tagged[0].textContent, /Brosser les dents/);
assert.match(tagged[0].querySelector('.pts-wait').textContent, /Hops (à valider|to approve)/);
// A member with hops waiting wears an amber pastille with the count; none, no pastille.
const holds = [...card.shadowRoot.querySelectorAll('.podium-member')].filter(m => m.querySelector('.hold'));
assert.equal(holds.length, 1, 'only the member with waiting hops has the pastille');
assert.match(holds[0].textContent, /Elena/);
assert.equal(holds[0].querySelector('.hold').textContent.trim(), '12');
assert.match(holds[0].querySelector('.hold').title, /12 hops (à valider|to approve)/, "parent: to approve");
console.log('ok');
process.exit(0);
