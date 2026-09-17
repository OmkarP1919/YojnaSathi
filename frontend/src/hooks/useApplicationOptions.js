import { useEffect, useState } from 'react';
import { fetchApplicationOptions } from '../api';

/**
 * Lazy, on-demand loading of physical application centers for recommendation
 * results. `/api/recommend` intentionally omits locations for speed; this hook
 * fetches them afterwards from the existing GET /api/application-options
 * endpoint (which reuses the backend location resolver).
 *
 * Results are cached per (schemeId, state, district, taluka) and requests are
 * concurrency-limited so a long result list never floods the backend.
 */

const MAX_CONCURRENT_REQUESTS = 3;
const resultCache = new Map();
const inFlight = new Map();
let activeRequests = 0;
const pendingQueue = [];

function buildKey(schemeId, { state, district, taluka }) {
  return [schemeId, state || '', district || '', taluka || ''].join('|');
}

function runLimited(task) {
  return new Promise((resolve, reject) => {
    const execute = () => {
      activeRequests += 1;
      task()
        .then(resolve, reject)
        .finally(() => {
          activeRequests -= 1;
          const next = pendingQueue.shift();
          if (next) next();
        });
    };
    if (activeRequests < MAX_CONCURRENT_REQUESTS) {
      execute();
    } else {
      pendingQueue.push(execute);
    }
  });
}

/**
 * @param {string[]} schemeIds - Scheme IDs to load locations for
 * @param {object} location - { state, district, taluka } selected by the citizen
 * @param {boolean} enabled - Only fetch when the locations section will be shown
 * @returns {Object<string, {loading: boolean, error: boolean, locations: Array, online: object|null}>}
 */
export function useApplicationOptions(schemeIds, location = {}, enabled = false) {
  const [optionsById, setOptionsById] = useState({});
  const idsKey = Array.isArray(schemeIds) ? schemeIds.filter(Boolean).join('|') : '';
  const state = location?.state || '';
  const district = location?.district && location.district !== 'other' ? location.district : '';
  const taluka = location?.taluka && location.taluka !== 'other' ? location.taluka : '';

  useEffect(() => {
    let cancelled = false;
    const ids = idsKey ? idsKey.split('|') : [];
    if (!enabled || !state || ids.length === 0) {
      return undefined;
    }

    ids.forEach((schemeId) => {
      const query = { state, district, taluka };
      const key = buildKey(schemeId, query);
      const cached = resultCache.get(key);
      if (cached) {
        setOptionsById((prev) => (prev[schemeId] === cached ? prev : { ...prev, [schemeId]: cached }));
        return;
      }

      setOptionsById((prev) => (
        prev[schemeId]?.loading
          ? prev
          : { ...prev, [schemeId]: { loading: true, error: false, locations: [], online: null } }
      ));

      let pending = inFlight.get(key);
      if (!pending) {
        pending = runLimited(() => fetchApplicationOptions(schemeId, query))
          .then((data) => {
            const entry = {
              loading: false,
              error: false,
              locations: Array.isArray(data?.physical_locations) ? data.physical_locations : [],
              online: data?.online_application || null,
            };
            resultCache.set(key, entry);
            inFlight.delete(key);
            return entry;
          })
          .catch(() => {
            inFlight.delete(key);
            return { loading: false, error: true, locations: [], online: null };
          });
        inFlight.set(key, pending);
      }

      pending.then((entry) => {
        if (!cancelled) {
          setOptionsById((prev) => ({ ...prev, [schemeId]: entry }));
        }
      });
    });

    return () => {
      cancelled = true;
    };
  }, [idsKey, state, district, taluka, enabled]);

  return optionsById;
}

export default useApplicationOptions;
