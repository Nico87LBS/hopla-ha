import assert from 'node:assert/strict';
// A slot missed on the family tablet: the child's face carries a turning arrow,
// and a parent catches it up with a touch, without opening the grid.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
await import('../custom_components/hopla/frontend/hopla-family-card.js');

const now = new Date();
if (now.getHours() < 2) {
  console.log('family card missed slot test skipped: too close to midnight');
  process.exit(0);
}
const at = minutes => new Date(now.getTime() + minutes * 60000).toISOString();
const missedSlot = {index: 0, name: '', time: '07:00', at: at(-110), opens_at: at(-170), closes_at: at(-60), state: 'missed'};
const states = {
  'sensor.hopla_points_elena': {state: '0', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member'}},
  'sensor.hopla_points_anna': {state: '0', attributes: {hopla_member_id: 3, display_name: 'Anna', role: 'member'}},
  'sensor.cartable_elena': {state: 'Cartable', attributes: {task_id: 5, is_active: true, assignee_ids: [2], assigned_to_user_id: 2, points: 1,
    next_due_date: at(60 * 20), slots_today: [missedSlot]}},
  'sensor.cartable_anna': {state: 'Cartable', attributes: {task_id: 6, is_active: true, assignee_ids: [3], assigned_to_user_id: 3, points: 1,
    next_due_date: at(60 * 20), slots_today: [missedSlot]}},
};
const calls = [];
const card = document.createElement('hopla-family-card');
card.setConfig({show_points: false, show_approval: true, due: 'today'});
card.hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states, callService: async (...args) => { calls.push(args); return {response: {}}; }};
document.body.append(card);
const root = card.shadowRoot;
assert.equal(root.querySelectorAll('.open-grid').length, 0, 'a slot missed alone does not open the grid');
const faces = [...root.querySelectorAll('.row.slotted button.ringbtn')];
assert.equal(faces.length, 2, 'the task stays on the board, one face per child');
assert.ok(faces.every(button => button.querySelector('.badge.orange')), 'a turning arrow on each face');
assert.deepEqual(faces.map(button => [button.dataset.action, button.dataset.task, button.dataset.slot, button.dataset.member]),
  [['slot-catchup', '5', '0', '2'], ['slot-catchup', '6', '0', '3']], 'a touch catches the slot up');
assert.ok(faces.every(button => !button.disabled), 'a parent can touch it');
card.remove();
console.log('family card missed slot tests passed');
