import React, { useState } from 'react';
import { getLocaleString } from '../constants/strings';
import { getLocalizedField } from '../utils/localization';

/**
 * Determine display badge and styling for the location's office_type.
 * Recognizes citizen service centers (CSC, Setu, Maha e-Seva) vs government offices.
 * Never invents a center type if not provided by backend.
 */
export function getCenterTypeInfo(officeType, applicationMethod, lang = 'en') {
  const rawType = officeType ? String(officeType).trim().toLowerCase() : '';
  const rawMethod = applicationMethod ? String(applicationMethod).trim().toLowerCase() : '';

  // 1. Citizen Service Centers (CSC, Maha e-Seva, Setu Kendra)
  if (
    rawType === 'citizen_service_center' ||
    rawType.includes('csc') ||
    rawType.includes('setu') ||
    rawType.includes('seva') ||
    rawType.includes('sewa') ||
    rawType.includes('citizen center') ||
    rawType.includes('common service') ||
    rawMethod === 'scheme_designated_application_center'
  ) {
    return {
      isCSC: true,
      badgeText: getLocaleString(lang, 'officeTypeCSC'),
      typeClass: 'center-type-csc',
    };
  }

  // If no officeType provided, do not invent one
  if (!rawType) {
    return null;
  }

  // 2. Specific Government Offices
  if (rawType.includes('tahsil') || rawType.includes('tehsil')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeTahsil'),
      typeClass: 'center-type-gov',
    };
  }
  if (rawType.includes('collector')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeCollectorate'),
      typeClass: 'center-type-gov',
    };
  }
  if (rawType.includes('agri') || rawType.includes('krishi')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeAgri'),
      typeClass: 'center-type-gov',
    };
  }
  if (rawType.includes('hospital')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeHospital'),
      typeClass: 'center-type-gov',
    };
  }
  if (rawType.includes('anganwadi') || rawType.includes('cdpo') || rawType.includes('icds')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeAnganwadi'),
      typeClass: 'center-type-gov',
    };
  }
  if (rawType.includes('commissionerate') || rawType.includes('state_office')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeCommissionerate'),
      typeClass: 'center-type-gov',
    };
  }
  if (rawType.includes('district_office')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeDistrict'),
      typeClass: 'center-type-gov',
    };
  }
  if (rawType.includes('gov') || rawType.includes('government')) {
    return {
      isCSC: false,
      badgeText: getLocaleString(lang, 'officeTypeGov'),
      typeClass: 'center-type-gov',
    };
  }

  // 3. Fallback to readable label of backend office_type without inventing CSC
  const formatted = rawType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  return {
    isCSC: false,
    badgeText: formatted,
    typeClass: 'center-type-gov',
  };
}

/**
 * Extract 6-digit PIN code if present in data or address.
 */
export function extractPinCode(address, loc = {}) {
  if (loc.pincode) return String(loc.pincode).trim();
  if (loc.pin_code) return String(loc.pin_code).trim();
  if (!address || typeof address !== 'string') return null;
  const match = address.match(/(?:pin(?:\s*code)?[:\s-]*)?(\b\d{6}\b)/i);
  return match ? match[1] : null;
}

/**
 * Validate and clean phone number for tel: link.
 */
export function formatPhoneNumber(phone) {
  if (!phone || typeof phone !== 'string') return null;
  const trimmed = phone.trim();
  if (!trimmed || trimmed.length < 5) return null;
  const cleanTel = trimmed.replace(/[^\d+]/g, '');
  if (!cleanTel || cleanTel.length < 5) return null;
  return { display: trimmed, tel: cleanTel };
}

export function ApplicationLocationsList({
  locations = [],
  isLocationSearch = false,
  loading = false,
  error = false,
  lang = 'en',
  maxInitial = 5,
  hideTitle = false,
}) {
  const [expanded, setExpanded] = useState(false);

  const locList = Array.isArray(locations) ? locations : [];
  const hasLocations = locList.length > 0;

  // Nothing to show: no data yet and no location search requested (and not in an explicitly opened panel).
  if (!hasLocations && !isLocationSearch && !hideTitle) {
    return null;
  }

  // Awaiting the on-demand location request, or it failed: never claim there
  // are no centers until the request has actually resolved with an empty list.
  if (!hasLocations && (loading || error)) {
    return (
      <div className="location-guidance-container">
        {!hideTitle && (
          <h6 className="location-guidance-title">
            📍 {getLocaleString(lang, 'whereToApplyTitle')}
          </h6>
        )}
        <p className="location-empty-note" role="status">
          {loading && <span className="loading-spinner location-inline-spinner" aria-hidden="true" />}
          {!loading && error && <span aria-hidden="true">⚠️ </span>}
          {loading
            ? getLocaleString(lang, 'loadingApplicationCenters')
            : getLocaleString(lang, 'applicationCentersError')}
        </p>
      </div>
    );
  }

  // If no locations found for a location search or explicitly opened panel
  if (!hasLocations && (isLocationSearch || hideTitle)) {
    return (
      <div className="location-guidance-container">
        {!hideTitle && (
          <h6 className="location-guidance-title">
            📍 {getLocaleString(lang, 'whereToApplyTitle')}
          </h6>
        )}
        <p className="location-empty-note">
          ℹ️ {getLocaleString(lang, 'noLocationsFound')}
        </p>
      </div>
    );
  }

  const visibleLocations = expanded ? locList : locList.slice(0, maxInitial);
  const hasMore = locList.length > maxInitial;

  return (
    <div className="location-guidance-container">
      {!hideTitle && (
        <div className="location-guidance-header-row">
          <h6 className="location-guidance-title">
            📍 {getLocaleString(lang, 'whereToApplyTitle')}
          </h6>
          {hasMore && (
            <span className="location-count-badge">
              {locList.length}
            </span>
          )}
        </div>
      )}

      <div className="location-cards-list">
        {visibleLocations.map((loc, idx) => {
          const officeName = getLocalizedField(loc.office_name, lang);
          const address = getLocalizedField(loc.address, lang);
          const hours = loc.working_hours ? getLocalizedField(loc.working_hours, lang) : null;
          const centerInfo = getCenterTypeInfo(loc.office_type, loc.application_method, lang);
          const pinCode = extractPinCode(address, loc);
          const phoneObj = formatPhoneNumber(loc.contact_phone);

          return (
            <div
              key={loc.id || `loc-${idx}`}
              className={`location-card-item ${centerInfo?.isCSC ? 'is-csc-center' : 'is-gov-office'}`}
            >
              <div className="location-card-header">
                <div className="location-title-badges-col">
                  <div className="location-badges-row">
                    {centerInfo && (
                      <span className={`center-type-badge ${centerInfo.typeClass}`}>
                        {centerInfo.isCSC ? '🏪 ' : '🏛️ '}
                        {centerInfo.badgeText}
                      </span>
                    )}
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
                    {pinCode && (
                      <span className="location-pin-badge">
                        {getLocaleString(lang, 'pinCodeLabel')}: {pinCode}
                      </span>
                    )}
                  </div>
                  <strong className="location-office-name">{officeName}</strong>
                </div>
              </div>

              {centerInfo?.isCSC && (
                <div className="center-service-note">
                  <span className="center-service-icon" aria-hidden="true">✓</span>
                  <span>{getLocaleString(lang, 'centerVisitAssistance')}</span>
                </div>
              )}

              {address && (
                <p className="location-address-text">
                  📍 {address}
                </p>
              )}

              <div className="location-meta-row">
                {phoneObj && (
                  <a
                    href={`tel:${phoneObj.tel}`}
                    className="location-phone-link"
                    title={`Call ${phoneObj.display}`}
                  >
                    📞 {phoneObj.display}
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

      {hasMore && (
        <div className="location-expand-action">
          <button
            type="button"
            className="btn-toggle-centers"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
          >
            {expanded
              ? getLocaleString(lang, 'showFewerCenters')
              : getLocaleString(lang, 'viewAllCenters', { count: locList.length })}
          </button>
        </div>
      )}
    </div>
  );
}

export default ApplicationLocationsList;
