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

export function SchemeCard({ matchResult, profile = {}, onViewDetails, lang }) {
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

  // Resolved physical application locations from backend
  const locations = (matchResult.locations && matchResult.locations.length > 0)
    ? matchResult.locations
    : (offline && offline.locations && offline.locations.length > 0 ? offline.locations : []);

  const isLocationSearch = profile?.state === 'maharashtra' && profile?.district && profile?.district !== 'other';

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
          <div className="scheme-badge-row">
            <span className="scheme-category-badge">{categoryBadge}</span>
            {matchResult.is_web_discovered && (
              <span
                className="scheme-live-badge"
                title={getLocaleString(lang, 'liveGovSourceDesc')}
              >
                <span className="live-pulse-dot" aria-hidden="true" />
                {getLocaleString(lang, 'liveGovSource')}
              </span>
            )}
          </div>
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
          onClick={() => {
            const schemeDataForModal = {
              ...scheme,
              is_web_discovered: matchResult.is_web_discovered,
              locations: locations,
            };
            onViewDetails(scheme.id, schemeName, schemeDataForModal);
          }}
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

          {/* Location-Aware Physical Application Guidance */}
          {locations.length > 0 && (
            <div className="location-guidance-container">
              <h6 className="location-guidance-title">
                🏛️ {getLocaleString(lang, 'whereToApplyTitle')}
              </h6>
              <div className="location-cards-list">
                {locations.map((loc) => {
                  const officeName = getLocalizedField(loc.office_name, lang);
                  const address = getLocalizedField(loc.address, lang);
                  const hours = loc.working_hours ? getLocalizedField(loc.working_hours, lang) : null;
                  return (
                    <div key={loc.id} className="location-card-item">
                      <div className="location-card-header">
                        <strong className="location-office-name">{officeName}</strong>
                        <div className="location-badge-group">
                          {loc.district && (
                            <span className="location-jurisdiction-badge">
                              {loc.district.charAt(0).toUpperCase() + loc.district.slice(1)}
                            </span>
                          )}
                          {loc.taluka && (
                            <span className="location-jurisdiction-badge">
                              {loc.taluka.charAt(0).toUpperCase() + loc.taluka.slice(1)}
                            </span>
                          )}
                        </div>
                      </div>
                      {address && (
                        <p className="location-address-text">
                          📍 {address}
                        </p>
                      )}
                      <div className="location-meta-row">
                        {loc.contact_phone && (
                          <a href={`tel:${loc.contact_phone}`} className="location-phone-link">
                            📞 {loc.contact_phone}
                          </a>
                        )}
                        {hours && (
                          <span className="location-hours-text">
                            🕒 {hours}
                          </span>
                        )}
                        {loc.source_url && (
                          <a
                            href={loc.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="location-source-link"
                          >
                            {getLocaleString(lang, 'officeOfficialSource')} ↗
                          </a>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* If citizen selected a jurisdiction but no physical centers match */}
          {locations.length === 0 && isLocationSearch && (
            <div className="location-guidance-container">
              <h6 className="location-guidance-title">
                🏛️ {getLocaleString(lang, 'whereToApplyTitle')}
              </h6>
              <p className="location-empty-note">
                ℹ️ {getLocaleString(lang, 'noLocationsFound')}
              </p>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default SchemeCard;
