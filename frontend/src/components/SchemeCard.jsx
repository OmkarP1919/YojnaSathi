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

  const missing = getLocalizedList(missing_information, lang);

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
    </article>
  );
}

export default SchemeCard;
