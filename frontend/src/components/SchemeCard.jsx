import React, { useState } from 'react';
import { fetchSchemeDetails } from '../api';
import { t } from '../constants/strings';

export function SchemeCard({ scheme }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [details, setDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [detailsError, setDetailsError] = useState(null);

  const toggleDetails = async () => {
    if (!isExpanded && !details && !loadingDetails) {
      setLoadingDetails(true);
      setDetailsError(null);
      try {
        const data = await fetchSchemeDetails(scheme.id);
        setDetails(data);
      } catch (err) {
        setDetailsError(t('errorGeneric'));
      } finally {
        setLoadingDetails(false);
      }
    }
    setIsExpanded(!isExpanded);
  };

  return (
    <article className="scheme-card" aria-label={`Scheme: ${scheme.name}`}>
      <div className="scheme-card-header">
        <h4 className="scheme-name">{scheme.name}</h4>
        <span className="relevance-badge" title="Matching score based on provided profile details">
          {t('matchRelevance')} <strong>{scheme.relevance_score}</strong>
        </span>
      </div>

      {scheme.matched_reasons && scheme.matched_reasons.length > 0 && (
        <div className="scheme-section">
          <h5 className="section-title">{t('whyRelevant')}</h5>
          <ul className="reasons-list">
            {scheme.matched_reasons.map((reason, idx) => (
              <li key={idx} className="reason-item">
                <span className="bullet-icon" aria-hidden="true">✓</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {scheme.missing_information && scheme.missing_information.length > 0 && (
        <div className="scheme-section">
          <h5 className="section-title">{t('infoNeeded')}</h5>
          <ul className="missing-list">
            {scheme.missing_information.map((item, idx) => (
              <li key={idx} className="missing-item">
                <span className="bullet-icon" aria-hidden="true">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="scheme-card-actions">
        <button
          type="button"
          onClick={toggleDetails}
          className="btn-toggle-details"
          aria-expanded={isExpanded}
        >
          {isExpanded ? `▲ ${t('hideDetails')}` : `▼ ${t('viewDetails')}`}
        </button>
      </div>

      {isExpanded && (
        <div className="scheme-expanded-details">
          {loadingDetails && (
            <p className="details-loading">{t('loadingDetails')}</p>
          )}

          {detailsError && (
            <p className="details-error">{detailsError}</p>
          )}

          {details && (
            <div className="details-content">
              {details.department && (
                <div className="details-field">
                  <strong>{t('departmentLabel')}</strong> {details.department}
                </div>
              )}

              {details.benefits && details.benefits.length > 0 && (
                <div className="details-field">
                  <strong>{t('benefitsLabel')}</strong>
                  <ul className="benefits-list">
                    {details.benefits.map((benefit, bIdx) => (
                      <li key={bIdx}>{benefit}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="external-links">
                {details.application_url && (
                  <a
                    href={details.application_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-link-apply"
                  >
                    {t('applyButton')} ↗
                  </a>
                )}

                {details.source_url && (
                  <a
                    href={details.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-link-source"
                  >
                    {t('sourceButton')} ↗
                  </a>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default SchemeCard;
