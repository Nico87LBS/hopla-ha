import assert from 'node:assert/strict';
// The tablet is on holiday time in Lisbon, the family still on Paris time.
process.env.TZ = 'Europe/Lisbon';
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
await import('../custom_components/hopla/frontend/hopla-family-card.js');

const calls = [];
const parentMode = state => ({state, attributes: {hopla_parent_mode: true, config_entry_id: 'entry', enabled: true, has_pin: true,
  parent_users: ['nico'], unlocked_until: state === 'on' ? new Date(Date.now() + 120000).toISOString() : null}});
const states = {
  'sensor.hopla_points_elena': {state: '0', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member',
    family_timezone: 'Europe/Paris', home_timezone: 'Europe/Paris', config_entry_id: 'entry'}},
  'binary_sensor.hopla_parent_mode': parentMode('off'),
};
const hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states,
  callService: async (...args) => { calls.push(args); return {response: {}}; }};
const card = document.createElement('hopla-family-card');
card.setConfig({});
card.hass = hass;
document.body.append(card);
const root = card.shadowRoot;
const banner = () => root.querySelector('.zone-banner');
const click = selector => root.querySelector(selector).dispatchEvent(new window.MouseEvent('click', {bubbles: true, composed: true}));
const settle = () => new Promise(resolve => setTimeout(resolve, 0));

assert.ok(banner(), 'the tablet offers its own time');
assert.match(banner().textContent, /Lisbon/);
assert.match(banner().textContent, /Paris/);

// Only a parent moves the family: the code first.
click('.zone-move');
await settle();
assert.ok(root.querySelector('.pin-pad'));
assert.equal(calls.length, 0);
for (const digit of '1234') {
  click(`.key[data-digit="${digit}"]`);
  await settle();
}
await settle();
assert.deepEqual(calls.map(call => call[1]), ['unlock_parent_mode', 'set_family_timezone']);
assert.deepEqual(calls[1][2], {timezone: 'Europe/Lisbon', config_entry_id: 'entry'});

// Ignored on this tablet, for this pair of zones only.
card.hass = {...hass, states: {...states, 'binary_sensor.hopla_parent_mode': parentMode('on')}};
click('.zone-ignore');
await settle();
assert.equal(banner(), null);
assert.equal(localStorage.getItem('hoplaZoneIgnored:Europe/Lisbon:Europe/Paris'), '1');
// Removed, so no timer keeps the test running.
card.remove();
console.log('ok');
