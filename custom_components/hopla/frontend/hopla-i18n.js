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

export function browserLanguage() {
  return globalThis.navigator?.language || 'en';
}

// A card defines its elements only once English and the browser's language
// are ready, so the first render never shows a key.
await Promise.all([loadLanguage('en'), loadLanguage(browserLanguage())]);
