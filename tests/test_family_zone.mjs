import assert from 'node:assert/strict';
// Nico's iPad is in UTC, the family in Paris.
process.env.TZ = 'UTC';
globalThis.HTMLElement = class {};
globalThis.customElements = {define() {}, get() {}, whenDefined() { return Promise.resolve(); }};
globalThis.window = {};
const {boardData, historyDays, zoneCity, zoneProposal} = await import('../custom_components/hopla/frontend/hopla-family-card.js');
const {setFamilyZone, familyZoneOf, wallClock, fromWallClock} = await import('../custom_components/hopla/frontend/hopla-i18n.js');

const member = (id, name, extra = {}) => ({state: '0', attributes: {hopla_member_id: id, display_name: name, role: 'member', ...extra}});
const hass = {states: {
  'sensor.hopla_points_elena': member(2, 'Elena', {family_timezone: 'Europe/Paris', home_timezone: 'Europe/Paris', config_entry_id: 'entry'}),
  // 07:00 in Paris on the 24th.
  'sensor.chambre': {state: 'Chambre', attributes: {task_id: 10, friendly_name: 'Chambre', is_active: true, assignee_ids: [2],
    next_due_date: '2026-10-24T05:00:00Z'}},
}};
// 00:20 in Paris, still the 23rd on the iPad.
const now = new Date('2026-10-23T22:20:00Z');

setFamilyZone(null);
assert.deepEqual(boardData(hass, {due: 'today'}, now).tasks.map(t => t.name), [], 'the iPad alone thinks it is still the 23rd');

assert.deepEqual(familyZoneOf(hass), {zone: 'Europe/Paris', home: 'Europe/Paris'});
setFamilyZone(familyZoneOf(hass).zone);
assert.deepEqual(boardData(hass, {due: 'today'}, now).tasks.map(t => t.name), ['Chambre'], "the family's day is the 24th");

const wall = wallClock(now);
assert.deepEqual([wall.getDate(), wall.getHours(), wall.getMinutes()], [24, 0, 20]);
assert.equal(fromWallClock(wall).toISOString(), now.toISOString());
// Summer time too.
assert.equal(wallClock(new Date('2026-07-01T05:00:00Z')).getHours(), 7);

const days = historyDays([{created_at: '2026-10-23T22:30:00Z'}, {created_at: '2026-10-23T21:30:00Z'}, {created_at: '2026-10-23T08:00:00Z'}]);
assert.deepEqual(days.map(d => d.entries.length), [1, 2], "11:30 pm in UTC is already the next day in Paris");

assert.equal(zoneCity('America/Los_Angeles'), 'Los Angeles');
assert.equal(zoneProposal(hass, 'Europe/Paris'), null, 'the tablet is on the family time');
assert.deepEqual(zoneProposal(hass, 'Europe/Lisbon'), {device: 'Europe/Lisbon', family: 'Europe/Paris', ignored: 'hoplaZoneIgnored:Europe/Lisbon:Europe/Paris'});
assert.equal(zoneProposal({states: {}}, 'Europe/Lisbon'), null, 'no proposal from an older server');

// On a device on the family time, dates stay as they are.
setFamilyZone(Intl.DateTimeFormat().resolvedOptions().timeZone);
assert.equal(wallClock(now).getTime(), now.getTime());
console.log('ok');
