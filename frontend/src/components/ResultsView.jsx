import React from 'react';
import SchemeCard from './SchemeCard';
import WebSchemesCard from './WebSchemesCard';
import { getLocaleString } from '../constants/strings';
import { getLocalizedField } from '../utils/localization';

export function ResultsView({
  results,
  disclaimer,
  profile,
  onChangeAnswers,
  onReset,
  onViewDetails,
  lang,
}) {
  const count = results ? results.length : 0;
  const localizedDisclaimer = (disclaimer && getLocalizedField(disclaimer, lang)) || getLocaleString(lang, 'disclaimerText');

  return (
    <section className="results-container" aria-labelledby="results-title">
      {/* Results Header */}
      <div className="results-header">
        <div className="results-title-group">
          <h2 id="results-title" className="results-title">
            {getLocaleString(lang, 'resultsTitle')}
          </h2>
          <p className="results-subtitle">
            {getLocaleString(lang, 'resultsCountPrefix')} <strong>{count}</strong> {getLocaleString(lang, 'resultsCountSuffix')}
          </p>
        </div>

        <div className="results-actions-group">
          <button
            type="button"
            className="btn-change-answers"
            onClick={onChangeAnswers}
          >
            ← {getLocaleString(lang, 'changeAnswers')}
          </button>
          <button
            type="button"
            className="btn-new-search-outline"
            onClick={onReset}
          >
            ↺ {getLocaleString(lang, 'startNewSearch')}
          </button>
        </div>
      </div>

      {/* Official Backend Disclaimer Banner */}
      {localizedDisclaimer && (
        <div className="disclaimer-banner" role="note" aria-label={getLocaleString(lang, 'noticeLabel')}>
          <span className="disclaimer-icon" aria-hidden="true">ℹ️</span>
          <div className="disclaimer-content">
            <strong className="disclaimer-title">{getLocaleString(lang, 'noticeLabel')} </strong>
            <span>{localizedDisclaimer}</span>
          </div>
        </div>
      )}

      {/* Scheme Cards List */}
      {count > 0 ? (
        <div className="results-list" role="feed" aria-label={getLocaleString(lang, 'resultsTitle')}>
          {results.map((matchResult) => (
            <SchemeCard
              key={matchResult.scheme.id}
              matchResult={matchResult}
              profile={profile}
              onViewDetails={onViewDetails}
              lang={lang}
            />
          ))}
        </div>
      ) : (
        <div className="empty-results-card" role="status">
          <span className="empty-icon" aria-hidden="true">📋</span>
          <h3>{getLocaleString(lang, 'noResultsTitle')}</h3>
          <p>{getLocaleString(lang, 'noResultsText')}</p>
          <div className="empty-actions">
            <button
              type="button"
              className="btn-step-continue"
              onClick={onChangeAnswers}
            >
              ← {getLocaleString(lang, 'changeAnswers')}
            </button>
            <button
              type="button"
              className="btn-step-back"
              onClick={onReset}
            >
              ↺ {getLocaleString(lang, 'startNewSearch')}
            </button>
          </div>
        </div>
      )}

      {/* Independent web discovery (user-initiated; never blocks local results) */}
      <WebSchemesCard profile={profile} lang={lang} />
    </section>
  );
}

export default ResultsView;
