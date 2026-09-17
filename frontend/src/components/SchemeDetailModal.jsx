import React, { useEffect, useState, useRef } from 'react';
import { fetchSchemeDetails } from '../api';
import { getLocaleString } from '../constants/strings';
import { getLocalizedField, getLocalizedList } from '../utils/localization';

export function SchemeDetailModal({ schemeId, schemeName, onClose, lang }) {
  const [details, setDetails] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const modalRef = useRef(null);

  useEffect(() => {
    let isMounted = true;
    async function loadData() {
      if (!schemeId) return;
      setLoading(true);
      setError(null);
      try {
        const data = await fetchSchemeDetails(schemeId);
        if (isMounted) {
          setDetails(data);
        }
      } catch (err) {
        if (isMounted) {
          setError(getLocaleString(lang, 'errorGeneric'));
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }
    loadData();

    return () => {
      isMounted = false;
    };
  }, [schemeId, lang]);

  // Handle ESC key press
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Focus modal on open
  useEffect(() => {
    modalRef.current?.focus();
  }, []);

  const displayName = (details && getLocalizedField(details.name, lang)) || schemeName;
  const department = details ? getLocalizedField(details.department, lang) : '';
  const description = details ? getLocalizedField(details.description, lang) : '';
  const benefits = details ? getLocalizedList(details.benefits, lang) : [];
  const requiredInfo = details ? getLocalizedList(details.required_information, lang) : [];

  const guidance = details && details.application_guidance ? details.application_guidance : null;
  const detailOnline = guidance && guidance.online_application ? guidance.online_application : null;
  const detailOffline = guidance && guidance.offline_application ? guidance.offline_application : null;
  const detailOnlineUrl = detailOnline && detailOnline.available && detailOnline.portal_url
    ? detailOnline.portal_url
    : (details && details.application_url ? details.application_url : null);
  const detailPortalName = detailOnline && detailOnline.portal_name ? detailOnline.portal_name : null;
  const detailOfflineChannel = detailOffline && detailOffline.available && detailOffline.authorized_channel
    ? detailOffline.authorized_channel
    : null;
  const detailOfflineInstructions = detailOffline && detailOffline.available && detailOffline.instructions
    ? detailOffline.instructions
    : null;

  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="presentation"
    >
      <div
        className="scheme-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-scheme-title"
        ref={modalRef}
        tabIndex="-1"
      >
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-badge">{getLocaleString(lang, 'modalTitle')}</span>
            <h3 id="modal-scheme-title" className="modal-scheme-name">
              {displayName}
            </h3>
          </div>
          <button
            type="button"
            className="btn-modal-close"
            onClick={onClose}
            aria-label={getLocaleString(lang, 'closeModal')}
          >
            ✕
          </button>
        </div>

        <div className="modal-body">
          {loading && (
            <div className="modal-loading" role="status">
              <span className="loading-spinner" aria-hidden="true" />
              <p>{getLocaleString(lang, 'loadingDetails')}</p>
            </div>
          )}

          {error && (
            <div className="modal-error" role="alert">
              <p>{error}</p>
              <button
                type="button"
                className="btn-step-back"
                onClick={onClose}
              >
                {getLocaleString(lang, 'closeModal')}
              </button>
            </div>
          )}

          {details && !loading && (
            <div className="modal-content">
              {/* Department */}
              {department && (
                <div className="detail-section">
                  <h4 className="detail-section-title">
                    {getLocaleString(lang, 'departmentLabel')}
                  </h4>
                  <p className="detail-dept-text">{department}</p>
                </div>
              )}

              {/* Description */}
              {description && (
                <div className="detail-section">
                  <h4 className="detail-section-title">
                    {getLocaleString(lang, 'aboutLabel')}
                  </h4>
                  <p className="detail-desc-text">{description}</p>
                </div>
              )}

              {/* Key Benefits */}
              {benefits && benefits.length > 0 && (
                <div className="detail-section">
                  <h4 className="detail-section-title">
                    {getLocaleString(lang, 'benefitsLabel')}
                  </h4>
                  <ul className="detail-benefits-list">
                    {benefits.map((b, i) => (
                      <li key={i} className="detail-benefit-item">
                        <span className="bullet-icon" aria-hidden="true">✓</span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Required Documents / Information */}
              {requiredInfo && requiredInfo.length > 0 && (
                <div className="detail-section">
                  <h4 className="detail-section-title">
                    {getLocaleString(lang, 'documentsLabel')}
                  </h4>
                  <ul className="detail-docs-list">
                    {requiredInfo.map((doc, i) => (
                      <li key={i} className="detail-doc-item">
                        <span className="bullet-icon" aria-hidden="true">•</span>
                        <span>{doc}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* How to Apply / What do I do next? */}
              {guidance && (
                <div className="detail-section">
                  <h4 className="detail-section-title">
                    {getLocaleString(lang, 'nextStepsTitle')}
                  </h4>
                  <ol className="guidance-steps-list">
                    <li className="guidance-step-item">{getLocaleString(lang, 'stepCheckEligibility')}</li>
                    <li className="guidance-step-item">{getLocaleString(lang, 'stepPrepareDocuments')}</li>
                    {detailOnlineUrl && (
                      <li className="guidance-step-item">{getLocaleString(lang, 'stepApplyOnline')}</li>
                    )}
                    {detailOnlineUrl && (
                      <li className="guidance-step-item">{getLocaleString(lang, 'stepTrackStatus')}</li>
                    )}
                  </ol>
                  <div className="guidance-actions">
                    {detailOnlineUrl && (
                      <p className="detail-apply-online-text">
                        <span className="bullet-icon-check" aria-hidden="true">✓</span>
                        <span>
                          {getLocaleString(lang, 'portalLabel')}{' '}
                          <a
                            href={detailOnlineUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="detail-portal-link"
                          >
                            {detailPortalName || detailOnlineUrl}
                          </a>
                        </span>
                      </p>
                    )}
                    {detailOfflineChannel && (
                      <p className="guidance-offline-note">
                        <strong>{getLocaleString(lang, 'applyOfflineLabel')}:</strong> {detailOfflineChannel}
                        {detailOfflineInstructions ? ` — ${detailOfflineInstructions}` : ''}
                      </p>
                    )}
                    {!detailOnlineUrl && !detailOfflineChannel && (
                      <p className="guidance-offline-note">{getLocaleString(lang, 'schemeDataInfoMissing')}</p>
                    )}
                  </div>
                </div>
              )}

              {/* External Official Links */}
              <div className="modal-links-row">
                {details.application_url && (
                  <a
                    href={details.application_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-link-apply"
                  >
                    {getLocaleString(lang, 'applyButton')}
                  </a>
                )}
                {details.source_url && (
                  <a
                    href={details.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-link-source"
                  >
                    {getLocaleString(lang, 'sourceButton')}
                  </a>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="btn-step-back"
            onClick={onClose}
          >
            {getLocaleString(lang, 'closeModal')}
          </button>
        </div>
      </div>
    </div>
  );
}

export default SchemeDetailModal;
