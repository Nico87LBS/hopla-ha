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
assert.equal(blocks[0].querySelectorAll('.faces img, .faces .face, .faces > *').length > 0, true, 'with the faces of who it is for');
const listed = [...root.querySelectorAll('.row')].map(row => row.querySelector('.name > span:first-child').textContent);
assert.deepEqual(listed, ['Peindre'], 'the task is ticked in the list, as any other');
card.remove();

// A project late shows orange; one with nothing for the children shown stays out.
assert.equal(projectBlocks([{...projects[0], late: true}], [{id: 2}]).length, 1);
assert.equal(projectBlocks(projects, [{id: 9}]).length, 0, 'nothing for this child');
const waiting = projectBlocks([{...projects[0], tasks: [projects[0].tasks[0], projects[0].tasks[2]]}], [{id: 3}]);
assert.deepEqual(waiting[0].open, [], 'nothing to do now while the rest waits');
console.log('family project dom ok');
