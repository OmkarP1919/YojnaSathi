import React, { useState } from 'react';
import { searchWebSchemes } from '../api';
import { getLocaleString } from '../constants/strings';

/**
 * User-initiated web scheme discovery card.
 *
 * Renders below the local (curated) results and calls the independent
 * POST /api/web-schemes/search pipeline only when the citizen taps the
 * button — local recommendations always render instantly without it.
 * Web-found schemes are explicitly labeled and link to their sources.
 * Any backend/Tavily failure degrades to a friendly note; the local
 * results above are never affected.
 */
function WebSchemesCard({ profile, lang }) {
  const [state, setState] = useState('idle'); // idle | loading | done | error
  const [data, setData] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const handleSearch = async () => {
    setState('loading');
    setErrorMessage(null);
    try {
      const result = await searchWebSchemes(profile || {});
      setData(result);
      setState('done');
    } catch (err) {
      if (err.request && !err.response) {
        setErrorMessage(getLocaleString(lang, 'webSearchNetworkError'));
      } else {
        setErrorMessage(getLocaleString(lang, 'webSearchGenericError'));
      }
      setState('error');
    }
  };

  const validated = (data && data.validated_schemes) || [];
  const rejectedCount = (data && data.rejected_candidates && data.rejected_candidates.length) || 0;
  const unavailable =
    state === 'done' && (data?.status === 'partial' || data?.status === 'empty') && validated.length === 0;

  return (
    <section className="web-schemes-card" aria-label={getLocaleString(lang, 'webSearchTitle')} style={{ marginTop: '1.5rem' }}>
      <h3>{getLocaleString(lang, 'webSearchTitle')}</h3>
      <p>{getLocaleString(lang, 'webSearchDesc')}</p>

      {state === 'idle' && (
        <button type="button" className="btn-step-continue" onClick={handleSearch}>
          {getLocaleString(lang, 'webSearchCta')}
        </button>
      )}

      {state === 'loading' && (
        <div className="loading-container" role="status">
          <span className="loading-spinner-large" aria-hidden="true" />
          <p>{getLocaleString(lang, 'webSearchLoading')}</p>
        </div>
      )}

      {state === 'error' && (
        <div className="error-card" role="alert">
          <p>{errorMessage}</p>
          <button type="button" className="btn-step-continue" onClick={handleSearch}>
            {getLocaleString(lang, 'tryAgain')}
          </button>
        </div>
      )}

      {state === 'done' && !unavailable && (
        <div className="results-list" role="feed" aria-label={getLocaleString(lang, 'webSearchTitle')}>
          {validated.map((scheme) => (
            <article className="scheme-card" key={scheme.normalized_name || scheme.scheme_name}>
              <div className="scheme-card-header">
                <h4>{scheme.scheme_name}</h4>
                <span className="web-scheme-badge">{getLocaleString(lang, 'webSearchBadge')}</span>
              </div>
              {scheme.description && <p>{scheme.description}</p>}
              {scheme.benefits && scheme.benefits.length > 0 && (
                <ul>
                  {scheme.benefits.slice(0, 3).map((benefit, idx) => (
                    <li key={idx}>{benefit}</li>
                  ))}
                </ul>
              )}
              <div className="scheme-card-actions">
                {(scheme.application_url || scheme.source_url) && (
                  <a
                    href={scheme.application_url || scheme.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {getLocaleString(lang, 'webSearchVerifyLink')}
                  </a>
                )}
              </div>
            </article>
          ))}
        </div>
      )}

      {state === 'done' && !unavailable && (
        <div className="disclaimer-banner" role="note">
          <span className="disclaimer-icon" aria-hidden="true">ℹ️</span>
          <div className="disclaimer-content">
            <span>
              {getLocaleString(lang, 'webSearchDisclaimer')}
              {rejectedCount > 0 && ` ${getLocaleString(lang, 'webSearchRejectedNote')}: ${rejectedCount}`}
            </span>
          </div>
        </div>
      )}

      {unavailable && (
        <div className="empty-results-card" role="status">
          <p>{getLocaleString(lang, 'webSearchUnavailable')}</p>
          <button type="button" className="btn-step-back" onClick={handleSearch}>
            {getLocaleString(lang, 'tryAgain')}
          </button>
        </div>
      )}
    </section>
  );
}

export default WebSchemesCard;
