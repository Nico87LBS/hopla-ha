import assert from 'node:assert/strict';
// A morning routine on the family tablet: each child sees only the step to do now.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
const {routineStep, waitsInRoutine} = await import('../custom_components/hopla/frontend/hopla-family-card.js');

const soon = minutes => new Date(Date.now() + minutes * 60000).toISOString();
const task = (id, name, user, due = soon(30)) => ({state: name, attributes: {task_id: id, is_active: true, assignee_ids: [user],
  assigned_to_user_id: user, points: 2, next_due_date: due}});
const routines = [{id: 1, name: 'Matin', bonus: 5, task_ids: [1, 2, 3, 4, 5, 6], chore_ids: [2, 3, 5],
  members: [{user_id: 2, current: 3, step: 2, done: 1, total: 3, finished: false},
    {user_id: 3, current: 2, step: 1, done: 0, total: 3, finished: false}]}];
const states = {
  'sensor.hopla_points_elena': {state: '0', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member'}},
  'sensor.hopla_points_anna': {state: '0', attributes: {hopla_member_id: 3, display_name: 'Anna', role: 'member'}},
  'sensor.habiller_anna': task(2, "S'habiller", 3),
  'sensor.dents_elena': task(3, 'Dents', 2),
  'sensor.dents_anna': task(4, 'Dents', 3),
  'sensor.cartable_elena': task(5, 'Cartable', 2),
  'sensor.cartable_anna': task(6, 'Cartable', 3),
  'sensor.chambre': task(7, 'Chambre', 2),
  'sensor.hopla_games': {state: '', attributes: {hopla_games: true, routines}},
};
const hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states, callService: async () => ({response: {}})};
const card = document.createElement('hopla-family-card');
card.setConfig({show_points: false});
card.hass = hass;
document.body.append(card);
const root = card.shadowRoot;
const names = [...root.querySelectorAll('.row .name > span:first-child')].map(el => el.textContent);
assert.deepEqual(names.sort(), ['Chambre', 'Dents', "S'habiller"], 'only the steps to do now, and other tasks');
const chips = [...root.querySelectorAll('.routine')].map(el => el.textContent);
assert.deepEqual(chips.sort(), ['Matin2/3', 'Matin1/3'].sort(), 'each child’s own step and progress');
// The routine under way stands out in its own block, above the list: each
// child's progress, then the steps to do now, which leave the list.
const blocks = root.querySelectorAll('.routine-block');
assert.equal(blocks.length, 1, 'one block for the morning routine');
assert.match(blocks[0].querySelector('.rb-title').textContent, /Matin/);
assert.deepEqual([...blocks[0].querySelectorAll('.rb-name')].map(el => el.textContent), ['Elena', 'Anna']);
assert.deepEqual([...blocks[0].querySelectorAll('.rb-count')].map(el => el.textContent.replace(/^\D+/, '')), ['2/3', '1/3'],
  'the step each child is at, as on the step');
assert.deepEqual([...blocks[0].querySelectorAll('.rb-next')].map(el => el.textContent.replace(/^(Ensuite : |Next: )/, '')),
  ['Cartable', 'Dents'], 'the next step by name, from the order of the routine');
assert.deepEqual([...blocks[0].querySelectorAll('.row .name > span:first-child')].map(el => el.textContent).sort(), ['Dents', "S'habiller"]);
const listed = [...root.querySelectorAll('.row')].filter(row => !row.closest('.routine-block'))
  .map(row => row.querySelector('.name > span:first-child').textContent);
assert.deepEqual(listed, ['Chambre'], 'the steps show once, in the block');
card.remove();

// A step that can be done in any order shows with the current one, and the
// end of the run shows in the block.
const anyOrder = [{id: 1, name: 'Soir', task_ids: [2, 4, 6], chore_ids: [2, 4, 6],
  members: [{user_id: 3, current: 2, available: [2, 4], step: 1, done: 0, total: 3, finished: false,
    ends_at: soon(90), next: 'Cartable'}]}];
const card2 = document.createElement('hopla-family-card');
card2.setConfig({show_points: false});
card2.hass = {...hass, states: {...states, 'sensor.hopla_games': {state: '', attributes: {hopla_games: true, routines: anyOrder}}}};
document.body.append(card2);
const block = card2.shadowRoot.querySelector('.routine-block');
assert.deepEqual([...block.querySelectorAll('.row .name > span:first-child')].map(el => el.textContent).sort(), ['Dents', "S'habiller"]);
assert.match(block.querySelector('.rb-until').textContent, /^(jusqu’à|until) /);
assert.match(block.querySelector('.rb-next').textContent, /Cartable$/);
card2.remove();

// Once every child finished, the block goes.
const finished = [{...routines[0], members: routines[0].members.map(p => ({...p, current: null, finished: true}))}];
const card3 = document.createElement('hopla-family-card');
card3.setConfig({show_points: false});
card3.hass = {...hass, states: {...states, 'sensor.hopla_games': {state: '', attributes: {hopla_games: true, routines: finished}}}};
document.body.append(card3);
assert.equal(card3.shadowRoot.querySelectorAll('.routine-block').length, 0);
card3.remove();

// A step due another day shows as usual.
const endOfDay = new Date(Date.now() + 3600000);
const later = {id: 5, due: new Date(Date.now() + 2 * 86400000), assignees: [2], assignedTo: 2};
assert.equal(waitsInRoutine(routines, later, endOfDay), false);
assert.equal(waitsInRoutine(routines, {...later, due: new Date()}, endOfDay), true);
assert.equal(routineStep(routines, {id: 3, assignees: [2], assignedTo: 2}).progress.step, 2);
assert.equal(routineStep(routines, {id: 7, assignees: [2], assignedTo: 2}), null);
console.log('routine dom ok');
