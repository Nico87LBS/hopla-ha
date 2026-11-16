import assert from 'node:assert/strict';
// A rated challenge on the family card: the scale with the level reached, the
// face on the right. A touch on a face opens a small dialog to give the
// result; once given the face waits and only a parent can validate.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
await import('../custom_components/hopla/frontend/hopla-family-card.js');

const levels = [{key: 'jaune', name: 'Jaune', color: '#E0B000', position: 0}, {key: 'vert', name: 'Vert', color: '#17A34A', position: 1}];
const rated = [
  {id: 7, name: 'Dictées', kind: 'levels', unit: '', ends_at: '2099-01-01T00:00:00Z', levels,
    members: [{id: 2, state: 'todo', best: 0, result_id: null}, {id: 3, state: 'pending', best: 0, result_id: 41, result_text: 'Vert'}]},
  {id: 8, name: 'Calcul mental', kind: 'value', unit: '/20', ends_at: null, levels: [],
    members: [{id: 2, state: 'todo', best: null, result_id: null}]},
];
const states = {
  'sensor.hopla_points_elena': {state: '4', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member', total_points: 4}},
  'sensor.hopla_points_anna': {state: '2', attributes: {hopla_member_id: 3, display_name: 'Anna', role: 'member', total_points: 2}},
  'sensor.hopla_games_today': {state: 'unknown', attributes: {hopla_games: true, rated_challenges: rated, challenges: []}},
  'binary_sensor.hopla_parent_mode': {state: 'off', attributes: {hopla_parent_mode: true, config_entry_id: 'entry', enabled: true,
    has_pin: true, parent_users: ['nico'], unlocked_until: null}},
};
const calls = [];
const hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states,
  callService: async (...args) => { calls.push(args); return {response: {}}; }};
const card = document.createElement('hopla-family-card');
card.setConfig({});
card.hass = hass;
document.body.append(card);
const root = card.shadowRoot;
const click = selector => root.querySelector(selector).dispatchEvent(new window.MouseEvent('click', {bubbles: true, composed: true}));
const settle = () => new Promise(resolve => setTimeout(resolve, 0));

assert.equal(root.querySelectorAll('.goal').length, 2, 'both challenges show');
assert.equal(root.querySelectorAll('.scale i').length, 4, 'a dot per level, for each child');
assert.equal(root.querySelectorAll('.scale i.now').length, 2, 'the level reached is marked');
assert.ok(root.querySelector('.scale-n').textContent.includes('—'), 'a number challenge with no result yet');
assert.ok(!root.textContent.includes('validé'), 'no wording about the state: the face says it');

// The pending face is not a button for a child on the tablet.
assert.equal(root.querySelector('[data-action="result-open"][data-member="3"]'), null);
assert.ok(root.querySelector('.slot.waiting'));

// A level: a touch on the face, then on the level.
click('[data-action="result-open"][data-challenge="7"][data-member="2"]');
assert.ok(root.querySelector('.sheet [data-action="result-level"][data-key="vert"]'));
click('[data-action="result-level"][data-key="vert"]');
await settle();
assert.deepEqual(calls.at(-1).slice(1, 3), ['submit_challenge_result', {challenge_id: 7, user_id: 2, level_key: 'vert'}]);
assert.equal(root.querySelector('.sheet'), null, 'the dialog closes once saved');

// A number.
click('[data-action="result-open"][data-challenge="8"][data-member="2"]');
const send = root.querySelector('[data-action="result-send"]');
assert.ok(send.disabled, 'a number is needed first');
const input = root.querySelector('[data-field="result-value"]');
input.value = '15,5';
input.dispatchEvent(new window.Event('input', {bubbles: true, composed: true}));
assert.equal(root.querySelector('[data-action="result-send"]').disabled, false);
click('[data-action="result-send"]');
await settle();
assert.deepEqual(calls.at(-1).slice(1, 3), ['submit_challenge_result', {challenge_id: 8, user_id: 2, value: 15.5}]);

// A parent validates the waiting face.
card.hass = {...hass, user: {id: 'nico'}, states: {...states, 'binary_sensor.hopla_parent_mode': {state: 'on', attributes: {
  ...states['binary_sensor.hopla_parent_mode'].attributes, unlocked_until: new Date(Date.now() + 600000).toISOString()}}}};
click('[data-action="result-open"][data-member="3"]');
assert.ok(root.querySelector('.sheet').textContent.includes('Vert'));
click('[data-action="result-approve"]');
await settle();
assert.deepEqual(calls.at(-1).slice(1, 3), ['approve_challenge_result', {result_id: 41}]);
card.remove();
