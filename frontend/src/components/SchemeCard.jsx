import React from 'react';
import { getLocaleString } from '../constants/strings';
import { getLocalizedField, getLocalizedList, getLocalizedReason } from '../utils/localization';

const CATEGORY_LABELS = {
  agriculture: { en: "Agriculture", hi: "कृषि", mr: "शेती" },
  education: { en: "Education", hi: "शिक्षा", mr: "शिक्षण" },
  women: { en: "Women Welfare", hi: "महिला कल्याण", mr: "महिला कल्याण" },
  healthcare: { en: "Healthcare", hi: "स्वास्थ्य", mr: "आरोग्य" },
  housing: { en: "Housing", hi: "आवास", mr: "गृहनिर्माण" },
  employment: { en: "Employment", hi: "रोजगार", mr: "रोजगार" },
  business: { en: "Business", hi: "व्यवसाय", mr: "व्यवसाय" },
  social_welfare: { en: "Social Welfare", hi: "सामाजिक कल्याण", mr: "सामाजिक कल्याण" },
  financial_services: { en: "Financial Services", hi: "वित्तीय सेवाएं", mr: "वित्तीय सेवा" },
};

export function SchemeCard({ matchResult, onViewDetails, lang }) {
  const { scheme, relevance_score, matched_reasons, reason_codes, missing_information } = matchResult;

  const schemeName = getLocalizedField(scheme.name, lang);
  const catObj = CATEGORY_LABELS[scheme.category];
  const categoryBadge = catObj ? (catObj[lang] || catObj.en) : scheme.category;

  const reasons = (reason_codes && reason_codes.length > 0)
    ? reason_codes.map((rc) => getLocalizedReason(rc, lang))
    : (matched_reasons || []);

  const guidance = scheme.application_guidance || null;
  const online = guidance && guidance.online_application ? guidance.online_application : null;
  const offline = guidance && guidance.offline_application ? guidance.offline_application : null;
  const portalUrl = online && online.available && online.portal_url
    ? online.portal_url
    : (scheme.application_url || null);
  const offlineChannel = offline && offline.available && offline.authorized_channel
    ? offline.authorized_channel
    : null;
  const offlineInstructions = offline && offline.available && offline.instructions
    ? offline.instructions
    : null;

  // Documents: the match result carries `missing_information`; for voice items it
  // is empty, so fall back to the verified guidance documents when available.
  const guidanceDocs = guidance && guidance.documents_required ? guidance.documents_required : null;
  const missing = getLocalizedList(
    (missing_information && missing_information.length > 0) ? missing_information : guidanceDocs,
    lang
  );

  return (
    <article className="scheme-result-card" aria-label={`${getLocaleString(lang, 'modalTitle')}: ${schemeName}`}>
      <div className="scheme-card-header">
        <div className="scheme-title-wrap">
          <span className="scheme-category-badge">{categoryBadge}</span>
          <h4 className="scheme-title">{schemeName}</h4>
        </div>
        <div className="relevance-score-box">
          <span className="relevance-score-label">{getLocaleString(lang, 'matchRelevance')}</span>
          <span className="relevance-score-value">{relevance_score}/10</span>
        </div>
      </div>

      {/* Why this may be relevant */}
      {reasons && reasons.length > 0 && (
        <div className="scheme-info-block">
          <h5 className="info-block-title">{getLocaleString(lang, 'whyRelevant')}</h5>
          <ul className="reasons-list">
            {reasons.map((reason, idx) => (
              <li key={idx} className="reason-item">
                <span className="bullet-icon-check" aria-hidden="true">✓</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Information you may need */}
      {missing && missing.length > 0 && (
        <div className="scheme-info-block">
          <h5 className="info-block-title">{getLocaleString(lang, 'infoNeeded')}</h5>
          <ul className="missing-list">
            {missing.map((item, idx) => (
              <li key={idx} className="missing-item">
                <span className="bullet-icon-doc" aria-hidden="true">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action button to view details */}
      <div className="scheme-card-actions">
        <button
          type="button"
          className="btn-view-scheme"
          onClick={() => onViewDetails(scheme.id, schemeName)}
          aria-label={`${getLocaleString(lang, 'viewDetails')} for ${schemeName}`}
        >
          {getLocaleString(lang, 'viewDetails')} →
        </button>
      </div>

      {/* What do I do next? - application guidance from the verified scheme data */}
      {(guidance || scheme.application_url) && (
        <div className="scheme-info-block guidance-block">
          <h5 className="info-block-title">{getLocaleString(lang, 'nextStepsTitle')}</h5>
          <ol className="guidance-steps-list">
            <li className="guidance-step-item">{getLocaleString(lang, 'stepCheckEligibility')}</li>
            <li className="guidance-step-item">{getLocaleString(lang, 'stepPrepareDocuments')}</li>
            {portalUrl && (
              <li className="guidance-step-item">{getLocaleString(lang, 'stepApplyOnline')}</li>
            )}
            {portalUrl && (
              <li className="guidance-step-item">{getLocaleString(lang, 'stepTrackStatus')}</li>
            )}
          </ol>
          <div className="guidance-actions">
            {portalUrl && (
              <a
                href={portalUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-link-apply guidance-apply-link"
              >
                {getLocaleString(lang, 'applyOnlineButton')}
              </a>
            )}
            {offlineChannel && (
              <p className="guidance-offline-note">
                <strong>{getLocaleString(lang, 'applyOfflineLabel')}:</strong> {offlineChannel}
                {offlineInstructions ? ` — ${offlineInstructions}` : ''}
              </p>
            )}
            {!portalUrl && !offlineChannel && (
              <p className="guidance-offline-note">{getLocaleString(lang, 'schemeDataInfoMissing')}</p>
            )}
          </div>
        </div>
      )}
    </article>
  );
}

export default SchemeCard;
