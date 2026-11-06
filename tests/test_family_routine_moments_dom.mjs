import assert from 'node:assert/strict';
// A routine step about one moment of a task, a routine with hours coming up,
// and a routine over with steps left for a parent to catch up.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
const {stepMoment, waitsInRoutine} = await import('../custom_components/hopla/frontend/hopla-family-card.js');

const at = minutes => new Date(Date.now() + minutes * 60000).toISOString();
// The morning moment's time is past but it is still open: late. The evening
// one is to come.
const morning = {index: 0, slot_id: 'matin', name: 'Matin', time: '07:30', at: at(-10), opens_at: at(-70), closes_at: at(20), state: 'open'};
const evening = {index: 1, slot_id: 'soir', name: 'Soir', time: '20:00', at: at(600), opens_at: at(540), closes_at: at(900), state: 'upcoming'};
const teeth = (slots, due = at(-10)) => ({state: 'Dents', attributes: {task_id: 3, is_active: true, assignee_ids: [2],
  assigned_to_user_id: 2, points: 2, next_due_date: due, slots_today: slots}});
const bag = {state: 'Cartable', attributes: {task_id: 5, is_active: true, assignee_ids: [2], assigned_to_user_id: 2, points: 1, next_due_date: at(30)}};
const step = (missed = false) => ({chore_id: 3, slot_id: 'matin', name: 'Dents', position: 0, missed});
const states = routines => ({
  'sensor.hopla_points_elena': {state: '0', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member'}},
  'sensor.dents': teeth([morning, evening]),
  'sensor.cartable': bag,
  'sensor.hopla_games': {state: '', attributes: {hopla_games: true, routines}},
});
const mount = async (routines, extra = {}) => {
  const card = document.createElement('hopla-family-card');
  card.setConfig({show_points: false, show_approval: true});
  card.hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states: {...states(routines), ...extra}, callService: async () => ({response: {}})};
  document.body.append(card);
  // The French texts load once.
  await new Promise(resolve => setTimeout(resolve, 50));
  return card;
};

// Late: only the routine's moment shows, in orange, and the face ticks the task.
let card = await mount([{id: 1, name: 'Matin', task_ids: [3, 5], chore_ids: [3, 5], window: 'open', closes_at: at(60),
  members: [{user_id: 2, current: 3, available: [3], step: 1, done: 0, total: 2, finished: false, missed: [], steps: [step(), {chore_id: 5, slot_id: '', position: 1}]}]}]);
let block = card.shadowRoot.querySelector('.routine-block');
assert.equal(block.querySelectorAll('.rb-moment').length, 1, 'one pill: the moment of the routine');
assert.equal(block.querySelector('.rb-moment').textContent, 'Matin · en retard');
assert.ok(block.querySelector('.rb-moment').classList.contains('late'));
assert.equal(block.querySelectorAll('.slot-pills').length, 0, 'not every moment of the task');
assert.equal(block.querySelector('button.slot.tap').dataset.task, '3');
card.remove();

// Before its time, the pill is not orange.
assert.equal(stepMoment(step(), [{...morning, at: at(10)}]).tone, 'neutral');

// Missed: the child goes on with the bag; the teeth stay greyed, with a turning
// arrow a parent touches to catch the morning moment up.
const missedMorning = {...morning, closes_at: at(-5), state: 'missed'};
card = await mount([{id: 1, name: 'Matin', task_ids: [3, 5], chore_ids: [3, 5], window: 'open', closes_at: at(60),
  members: [{user_id: 2, current: 5, available: [5], step: 2, done: 0, total: 2, finished: false, missed: [3],
    steps: [step(true), {chore_id: 5, slot_id: '', position: 1}]}]}], {'sensor.dents': teeth([missedMorning, evening], at(600))});
block = card.shadowRoot.querySelector('.routine-block');
const missedLine = block.querySelector('.rb-stepline.missed');
assert.equal(missedLine.querySelector('.rb-step').textContent, 'Dents');
assert.equal(missedLine.querySelector('.rb-moment').textContent, 'Matin · manquée');
const catchUp = missedLine.querySelector('button.slot.missed');
assert.equal(catchUp.dataset.action, 'slot-catchup');
assert.equal(catchUp.dataset.slot, '0');
const ticks = [...block.querySelectorAll('.rb-stepline:not(.missed) button.slot.tap')].map(el => el.dataset.task);
assert.deepEqual(ticks, ['5'], 'the next step is the one to tick');
card.remove();

// The evening moment of a task whose morning one was the routine's comes back
// to the list once the morning one is missed.
const routines = [{task_ids: [3], members: [{user_id: 2, current: 5, steps: [step(true)]}]}];
const task = {id: 3, due: new Date(Date.now() + 600 * 60000), slots: [missedMorning, evening], assignees: [2], assignedTo: 2};
assert.equal(waitsInRoutine(routines, task, new Date(Date.now() + 1440 * 60000)), false);
assert.equal(waitsInRoutine(routines, {...task, slots: [morning, evening]}, new Date(Date.now() + 1440 * 60000)), true);

// Coming up: a dashed block with when it starts and the first step, nothing to tick.
card = await mount([{id: 1, name: 'Matin', task_ids: [3, 5], chore_ids: [3, 5], window: 'upcoming', opens_at: at(30), closes_at: at(120),
  members: [{user_id: 2, current: null, available: [], step: 0, done: 0, total: 2, finished: false, missed: [], steps: []}]}]);
block = card.shadowRoot.querySelector('.routine-block');
assert.ok(block.classList.contains('coming'));
assert.match(block.querySelector('.rb-until').textContent, /^commence à /);
assert.equal(block.querySelector('.rb-count').textContent, '2 étapes');
assert.equal(block.querySelector('.rb-next').textContent, 'Première étape : Dents');
assert.equal(block.querySelectorAll('button').length, 0, 'nothing to tick before it opens');
card.remove();

// Over: nothing left to tick, so one red line; a touch opens the block with
// what was left, for a parent to catch up.
card = await mount([{id: 1, name: 'Matin', task_ids: [3, 5], chore_ids: [3, 5], window: 'over', closes_at: at(-10),
  members: [{user_id: 2, current: null, available: [], step: 0, done: 1, total: 2, finished: false, missed: [5],
    steps: [step(), {chore_id: 5, slot_id: '', name: 'Cartable', position: 1, missed: true}]}]}]);
block = card.shadowRoot.querySelector('.routine-block');
assert.ok(block.classList.contains('settled') && block.classList.contains('red'));
assert.equal(block.querySelector('.rb-until').textContent, '1 manquée');
assert.equal(card.shadowRoot.querySelectorAll('.rb-stepline').length, 0, 'collapsed: no steps shown');
block.click();
await new Promise(resolve => setTimeout(resolve, 10));
block = card.shadowRoot.querySelector('.routine-block');
assert.ok(block.classList.contains('red') && !block.classList.contains('settled'));
assert.match(block.querySelector('.rb-until').textContent, /^finie à /);
assert.equal(block.querySelector('.rb-count').textContent, '1 manquée');
const late = block.querySelector('.rb-stepline.missed button.slot.missed');
assert.equal(late.dataset.action, 'complete', 'a step that is the whole task is caught up by doing it');
assert.equal(late.dataset.task, '5');
card.remove();
// A moment ticked and waiting for a parent: the clock on the face, and the
// parent approves that moment, not the task.
const waitingMorning = {...morning, state: 'pending', completed_by: 2};
card = await mount([{id: 1, name: 'Matin', task_ids: [3, 5], chore_ids: [3, 5], window: 'open', closes_at: at(60),
  members: [{user_id: 2, current: 3, available: [3], step: 1, done: 0, total: 2, finished: false, missed: [], steps: [step(), {chore_id: 5, slot_id: '', position: 1}]}]}],
  {'sensor.dents': teeth([waitingMorning, evening])});
block = card.shadowRoot.querySelector('.routine-block');
// Only a step to approve is left: one orange line, opened by a touch.
assert.ok(block.classList.contains('settled') && block.classList.contains('orange'));
assert.equal(block.querySelector('.rb-until').textContent, '1 à valider');
block.click();
await new Promise(resolve => setTimeout(resolve, 10));
block = card.shadowRoot.querySelector('.routine-block');
assert.ok(block.querySelector('.slot.waiting'), 'the face shows the step waits for a parent');
assert.equal(block.querySelectorAll('button.slot.tap[data-task="3"]').length, 0, 'it cannot be ticked again');
const approve = block.querySelector('button[data-action="slot-approve"]');
assert.equal(approve.dataset.slot, '0');
assert.equal(approve.dataset.task, '3');
card.remove();
// A step still to tick keeps the block open; the helper decides.
const {settledRoutine} = await import('../custom_components/hopla/frontend/hopla-family-card.js');
assert.equal(settledRoutine([{finished: false, missed: 0, states: ['todo']}]), null);
assert.equal(settledRoutine([{finished: false, missed: 0, states: []}]), null);
assert.deepEqual(settledRoutine([{finished: true, missed: 0, states: []}]), {tone: 'green', pending: 0, missed: 0});
assert.equal(settledRoutine([{finished: false, missed: 1, states: ['pending']}]).tone, 'red');
console.log('ok');
