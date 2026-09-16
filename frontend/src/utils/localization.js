import { INDIAN_STATES } from '../constants/questionnaires';
import { getLocaleString } from '../constants/strings';

/**
 * Extract localized text from a string or { en, hi, mr } object.
 * @param {string|object} field - Value to localize
 * @param {string} lang - 'en' | 'hi' | 'mr'
 * @returns {string} - Localized text
 */
export function getLocalizedField(field, lang = 'en') {
  if (!field) return '';
  if (typeof field === 'object' && !Array.isArray(field)) {
    return field[lang] || field.en || field.hi || field.mr || '';
  }
  return String(field);
}

/**
 * Extract localized list of strings from an array or { en: [...], hi: [...], mr: [...] } object.
 * @param {Array|object} listField - Array or localized map of arrays
 * @param {string} lang - 'en' | 'hi' | 'mr'
 * @returns {Array<string>} - Localized list of strings
 */
export function getLocalizedList(listField, lang = 'en') {
  if (!listField) return [];
  if (typeof listField === 'object' && !Array.isArray(listField)) {
    return listField[lang] || listField.en || listField.hi || listField.mr || [];
  }
  if (Array.isArray(listField)) {
    return listField;
  }
  return [String(listField)];
}

/**
 * Resolve localized Indian state display name.
 * @param {string} stateVal - Canonical state value (e.g. 'maharashtra')
 * @param {string} lang - 'en' | 'hi' | 'mr'
 * @returns {string} - Localized state name
 */
export function getLocalizedStateName(stateVal, lang = 'en') {
  if (!stateVal) return '';
  const normalized = stateVal.trim().toLowerCase();
  const found = INDIAN_STATES.find((s) => s.value === normalized);
  if (found && found.labels) {
    return found.labels[lang] || found.labels.en || stateVal;
  }
  return stateVal.charAt(0).toUpperCase() + stateVal.slice(1);
}

/**
 * Format semantic reason code into a natural localized sentence.
 * @param {object} reasonItem - { code: string, params: object }
 * @param {string} lang - 'en' | 'hi' | 'mr'
 * @returns {string} - Localized reason text
 */
export function getLocalizedReason(reasonItem, lang = 'en') {
  if (!reasonItem) return '';
  // Fallback if backend returned plain string
  if (typeof reasonItem === 'string') {
    return reasonItem;
  }

  const code = reasonItem.code;
  const params = { ...(reasonItem.params || {}) };

  // Translate state param if present
  if (params.state) {
    params.state = getLocalizedStateName(params.state, lang);
  }

  // Translate category or area params if present
  if (params.area) {
    if (params.area === 'rural') {
      params.area = lang === 'hi' ? 'ग्रामीण' : (lang === 'mr' ? 'ग्रामीण' : 'rural');
    } else if (params.area === 'urban') {
      params.area = lang === 'hi' ? 'शहरी' : (lang === 'mr' ? 'शहरी' : 'urban');
    }
  }

  const stringKey = `reason_${code}`;
  const translated = getLocaleString(lang, stringKey, params);

  // If key not found, fallback to graceful readable text
  if (translated === stringKey) {
    return code.replace(/_/g, ' ').toLowerCase();
  }

  return translated;
}
