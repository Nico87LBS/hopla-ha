import assert from 'node:assert/strict';
globalThis.HTMLElement = class {};
globalThis.customElements = {define() {}, get() {}, whenDefined() { return Promise.resolve(); }};
globalThis.window = {};
const {default: en} = await import('../custom_components/hopla/frontend/locales/en.js');
const {default: fr} = await import('../custom_components/hopla/frontend/locales/fr.js');
const {translator, loadLanguage, baseLanguage} = await import('../custom_components/hopla/frontend/hopla-i18n.js');
const {recurrenceText, dueText, emptyMessage} = await import('../custom_components/hopla/frontend/hopla-user-todo-card.js');

// Every language file has exactly the English keys, and the same {placeholders}.
const flatten = (node, prefix = '') => Object.entries(node).flatMap(([key, value]) =>
  typeof value === 'string' ? [[prefix + key, value]] : flatten(value, `${prefix}${key}.`));
const english = new Map(flatten(en));
const french = new Map(flatten(fr));
const placeholders = text => [...text.matchAll(/\{(\w+)\}/g)].map(match => match[1]).filter(name => name !== 'count').sort();
assert.deepEqual([...french.keys()].sort(), [...english.keys()].sort());
for (const [key, text] of english) assert.deepEqual(placeholders(french.get(key)), placeholders(text), key);

assert.equal(baseLanguage('fr-FR'), 'fr');
assert.equal(baseLanguage('de'), 'en', 'unsupported languages fall back to English');
await loadLanguage('fr');
const t = translator('fr');
assert.equal(t('todo.complete'), 'Terminer');
assert.equal(t('common.points', {count: 1}), '1 point');
assert.equal(t('common.points', {count: 3}), '3 points');
assert.equal(t('missing.key'), 'missing.key');

assert.equal(recurrenceText({frequency_type: 'weekly'}, t), 'Toutes les semaines');
assert.equal(recurrenceText({frequency_type: 'interval', interval_type: 'days', frequency: 1}, t), 'Tous les jours');
assert.equal(recurrenceText({frequency_type: 'interval', interval_type: 'days', frequency: 3}, t), 'Tous les 3 jours');
assert.equal(recurrenceText({frequency_type: 'interval', interval_type: 'days', frequency: 3}), 'Every 3 days');
const now = new Date('2026-10-20T12:00:00');
assert.equal(dueText('2026-10-18', 'fr', now), 'En retard · 2 jours');
assert.equal(dueText('2026-10-20', 'fr', now), "Aujourd'hui");
assert.equal(dueText(null, 'fr', now), "Pas d'échéance");
assert.equal(emptyMessage({display_filter: 'today'}, 'Elena', t), "Aucune tâche pour Elena · Filtre : Aujourd'hui");
assert.equal(emptyMessage({display_filter: 'upcoming', upcoming_days: 2, labels: ['a', 'b'], label_match: 'all'}, 'Anna', t),
  'Aucune tâche pour Anna · Filtre : Prochainement (2 jours à l’avance) · Étiquettes : a ET b');
console.log('Card translations passed');
