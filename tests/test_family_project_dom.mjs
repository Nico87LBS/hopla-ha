import assert from 'node:assert/strict';
// A project on the family tablet: how far it got and the tasks to do now.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
const {projectBlocks} = await import('../custom_components/hopla/frontend/hopla-family-card.js');

const task = (id, name, users) => ({state: name, attributes: {task_id: id, is_active: true, assignee_ids: users,
  assigned_to_user_id: users.length === 1 ? users[0] : null, assign_strategy: users.length > 1 ? 'together' : 'keep_last_assigned',
  points: 3, frequency_type: 'once'}});
const projects = [{id: 4, name: 'Cabane', bonus: 10, due_on: '2026-11-20', late: false, done: 1, total: 3, tasks: [
  {chore_id: 1, name: 'Poncer', assignee_ids: [2], done: true, locked: false},
  {chore_id: 2, name: 'Peindre', assignee_ids: [2, 3], done: false, locked: false},
  {chore_id: 3, name: 'Toit', assignee_ids: [3], done: false, locked: true}]}];
const states = {
  'sensor.hopla_points_elena': {state: '0', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member'}},
  'sensor.hopla_points_anna': {state: '0', attributes: {hopla_member_id: 3, display_name: 'Anna', role: 'member'}},
  // The roof waits for the painting: the server keeps it archived, so it has no active task here.
  'sensor.peindre': task(2, 'Peindre', [2, 3]),
  'sensor.hopla_games': {state: '', attributes: {hopla_games: true, routines: [], projects}},
};
const hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states, callService: async () => ({response: {}})};
const card = document.createElement('hopla-family-card');
card.setConfig({show_points: false});
card.hass = hass;
document.body.append(card);
const root = card.shadowRoot;
const blocks = root.querySelectorAll('.routine-block.project');
assert.equal(blocks.length, 1, 'one block for the project');
assert.match(blocks[0].querySelector('.rb-title').textContent, /Cabane/);
assert.equal(blocks[0].querySelector('.rb-count').textContent, '1/3', 'how far it got');
assert.equal(blocks[0].querySelector('.rb-bar i').style.width, '33%');
assert.match(blocks[0].querySelector('.rb-next').textContent, /À finir avant|Finish by/);
assert.deepEqual([...blocks[0].querySelectorAll('.rb-step')].map(el => el.textContent), ['Peindre'], 'only the task to do now');
const taps = [...blocks[0].querySelectorAll('.faces button.slot.tap[data-action="complete"]')];
assert.deepEqual(taps.map(tap => [tap.dataset.task, tap.dataset.member]), [['2', '2'], ['2', '3']],
  'a face to touch for each of who it is for');
assert.equal(root.querySelectorAll('.row').length, 0, 'the task leaves the list meanwhile, as a routine step');
card.remove();

// Waiting for a parent: the clock on the face, and the buttons to approve for a parent.
const pendingStates = {...states, 'sensor.peindre': {...states['sensor.peindre'],
  attributes: {...states['sensor.peindre'].attributes, pending_approval: true}}};
const parentCard = document.createElement('hopla-family-card');
parentCard.setConfig({show_points: false, show_approval: true});
parentCard.hass = {...hass, user: {id: 'parent', is_admin: true}, states: pendingStates};
document.body.append(parentCard);
const pendingBlock = parentCard.shadowRoot.querySelector('.routine-block.project');
assert.equal(pendingBlock.querySelectorAll('.faces .slot.waiting').length, 1, 'the clock on the face');
assert.equal(pendingBlock.querySelectorAll('.faces button.slot.tap').length, 0, 'nothing to tick while it waits');
parentCard.remove();

// A task filtered out of the list keeps its line, its faces to look at only.
const filtered = document.createElement('hopla-family-card');
filtered.setConfig({show_points: false, labels: ['Jardin']});
filtered.hass = hass;
document.body.append(filtered);
const filteredBlock = filtered.shadowRoot.querySelector('.routine-block.project');
assert.deepEqual([...filteredBlock.querySelectorAll('.rb-step')].map(el => el.textContent), ['Peindre']);
assert.equal(filteredBlock.querySelectorAll('.faces button').length, 0, 'no face to touch');
filtered.remove();

// A project late shows orange; one with nothing for the children shown stays out.
assert.equal(projectBlocks([{...projects[0], late: true}], [{id: 2}]).length, 1);
assert.equal(projectBlocks(projects, [{id: 9}]).length, 0, 'nothing for this child');
const waiting = projectBlocks([{...projects[0], tasks: [projects[0].tasks[0], projects[0].tasks[2]]}], [{id: 3}]);
assert.deepEqual(waiting[0].open, [], 'nothing to do now while the rest waits');
console.log('family project dom ok');
