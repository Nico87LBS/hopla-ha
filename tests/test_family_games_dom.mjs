import assert from 'node:assert/strict';
// A child opens her learning games from the family card: no parent code, the
// games fill the screen and closing them goes back to the card.
const {Window} = await import(process.env.DOM_TEST_MODULE || 'happy-dom');
const window = new Window();
Object.assign(globalThis, {window, document: window.document, HTMLElement: window.HTMLElement,
  customElements: window.customElements, CustomEvent: window.CustomEvent, localStorage: window.localStorage});
customElements.define('home-assistant', class extends HTMLElement {});
await import('../custom_components/hopla/frontend/hopla-family-card.js');

const calls = [];
const states = {
  'sensor.hopla_points_elena': {state: '4', attributes: {hopla_member_id: 2, display_name: 'Elena', role: 'member', total_points: 4}},
  'binary_sensor.hopla_parent_mode': {state: 'off', attributes: {hopla_parent_mode: true, config_entry_id: 'entry', enabled: true,
    has_pin: true, parent_users: ['nico'], unlocked_until: null}},
};
const hass = {user: {id: 'tablet'}, locale: {language: 'fr'}, states,
  callService: async (...args) => {
    calls.push(args);
    return {response: {url: 'https://hopla.example/play/abc', expires_at: '2026-10-30T10:00:00Z'}};
  }};
const card = document.createElement('hopla-family-card');
card.setConfig({});
card.hass = hass;
document.body.append(card);
const root = card.shadowRoot;
const click = (scope, selector) => scope.querySelector(selector).dispatchEvent(new window.MouseEvent('click', {bubbles: true, composed: true}));
const settle = () => new Promise(resolve => setTimeout(resolve, 0));

click(root, '[data-action="sheet-history"][data-member="2"]');
await settle();
const button = root.querySelector('[data-action="games-open"][data-member="2"]');
assert.ok(button, 'the child sheet offers the games');
assert.equal(button.getAttribute('aria-label'), 'Jeux de Elena');

click(root, '[data-action="games-open"]');
await settle();
assert.deepEqual(calls.at(-1).slice(1, 3), ['open_games', {user_id: 2}]);
assert.equal(calls.at(-1)[5], true, 'the service answers with the address');
assert.equal(root.querySelector('.sheet'), null, 'the sheet closes');
const overlay = document.getElementById('hopla-games');
assert.ok(overlay, 'the games open over the dashboard');
assert.equal(overlay.shadowRoot.querySelector('iframe').getAttribute('src'), 'https://hopla.example/play/abc');

// A redraw of the card keeps the game going.
card.hass = {...hass, states: {...states}};
assert.equal(document.getElementById('hopla-games'), overlay);

click(overlay.shadowRoot, 'button');
assert.equal(document.getElementById('hopla-games'), null, 'closing goes back to the card');
card.remove();
