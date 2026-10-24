// Card texts live in one file per language under locales/. English is the
// fallback for any missing text. Other languages load on first use, and the
// card that asked renders again once they arrive.
const version = new URL(import.meta.url).search;
const strings = new Map();
const loading = new Map();

export const LANGUAGES = ['en', 'fr'];

export function baseLanguage(language) {
  const base = String(language || 'en').toLowerCase().split(/[-_]/)[0];
  return LANGUAGES.includes(base) ? base : 'en';
}

export function loadLanguage(language) {
  const base = baseLanguage(language);
  if (!loading.has(base)) {
    loading.set(base, import(new URL(`./locales/${base}.js${version}`, import.meta.url))
      .then(module => { strings.set(base, module.default); })
      .catch(() => { strings.set(base, {}); }));
  }
  return loading.get(base);
}

const lookup = (table, key) => key.split('.').reduce((node, part) => node?.[part], table);

// Returns t(key, values). A number in values.count picks the plural form
// key_one or key_other for the language, and {name} inserts values.name.
export function translator(language, onLoad) {
  const base = baseLanguage(language);
  if (!strings.has(base)) loadLanguage(base).then(() => onLoad?.());
  const plural = new Intl.PluralRules(base);
  return (key, values = {}) => {
    const find = table => {
      if (typeof values.count === 'number') {
        const form = lookup(table, `${key}_${plural.select(values.count)}`) ?? lookup(table, `${key}_other`);
        if (typeof form === 'string') return form;
      }
      const text = lookup(table, key);
      return typeof text === 'string' ? text : undefined;
    };
    const text = find(strings.get(base)) ?? find(strings.get('en')) ?? key;
    return text.replace(/\{(\w+)\}/g, (match, name) => values[name] ?? match);
  };
}

// An open dashboard keeps the cards it loaded, by the hash in their URL, until
// the page reloads: a wall tablet could show old cards for days after an
// update. When Home Assistant serves newer ones, reload the page, once per
// version so a cached page can never loop.
export function reloadIfOutdated(hass) {
  const mine = new URLSearchParams(version).get('v');
  if (!mine || typeof location === 'undefined') return false;
  const latest = Object.values(hass?.states || {}).find(state => state.attributes?.frontend_version)?.attributes.frontend_version;
  if (!latest || latest === mine) return false;
  try {
    if (sessionStorage.getItem('hopla-reloaded-for') === latest) return false;
    sessionStorage.setItem('hopla-reloaded-for', latest);
  } catch {
    return false;
  }
  location.reload();
  return true;
}

// Every date the cards show follows the family's time zone, whatever the
// zone of the tablet: one left in UTC shows the same day and times as the
// phones. wallClock(value) gives a Date whose local fields (day, hours…) are
// the family's at that instant, so the cards' day arithmetic keeps working;
// fromWallClock() turns such a Date back into the real instant. Without a
// known family zone both leave dates as they are.
let familyZone = null;

export function deviceZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch { return null; }
}

export function setFamilyZone(zone) {
  if (!zone) { familyZone = null; return; }
  try { new Intl.DateTimeFormat('en', {timeZone: zone}); familyZone = zone === deviceZone() ? null : zone; }
  catch { familyZone = null; }
}

// The family's zone as the integration publishes it, and the server's (home).
export function familyZoneOf(hass) {
  const state = Object.values(hass?.states || {}).find(item => item.attributes?.family_timezone);
  return state ? {zone: state.attributes.family_timezone, home: state.attributes.home_timezone || null} : null;
}

const zoneParts = (ms, zone) => {
  const parts = {};
  for (const {type, value} of new Intl.DateTimeFormat('en-US', {timeZone: zone, hourCycle: 'h23', year: 'numeric',
    month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric'}).formatToParts(new Date(ms))) {
    parts[type] = Number(value);
  }
  return parts;
};
const zoneOffset = (ms, zone) => {
  const p = zoneParts(ms, zone);
  return Date.UTC(p.year, p.month - 1, p.day, p.hour % 24, p.minute, p.second) - (ms - ms % 1000);
};

export function wallClock(value = new Date()) {
  const date = value instanceof Date ? new Date(value.getTime()) : new Date(value);
  if (!familyZone || isNaN(date)) return date;
  const p = zoneParts(date.getTime(), familyZone);
  return new Date(p.year, p.month - 1, p.day, p.hour % 24, p.minute, p.second, date.getMilliseconds());
}

export function fromWallClock(date) {
  if (!familyZone || !(date instanceof Date) || isNaN(date)) return date;
  const wall = Date.UTC(date.getFullYear(), date.getMonth(), date.getDate(), date.getHours(), date.getMinutes(),
    date.getSeconds(), date.getMilliseconds());
  let instant = wall - zoneOffset(wall, familyZone);
  instant = wall - zoneOffset(instant, familyZone);
  return new Date(instant);
}

export function browserLanguage() {
  return globalThis.navigator?.language || 'en';
}

// A card defines its elements only once English and the browser's language
// are ready, so the first render never shows a key.
await Promise.all([loadLanguage('en'), loadLanguage(browserLanguage())]);
