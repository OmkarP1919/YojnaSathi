import React, { useRef } from 'react';
import { getLocaleString } from '../constants/strings';
import { CALL_TEL_HREF, PHONE_GATEWAY_ENABLED } from '../constants/config';
import CategoryGrid from './CategoryGrid';

/**
 * Voice-first YojnaSathi homepage.
 *
 * The PRIMARY gateway is a large, animated YojnaSathi robot with a clear
 * microphone affordance. It is the visually dominant interaction so that
 * users who cannot read can still discover the voice assistant without
 * relying on text. Website and Phone remain as visually subordinate
 * secondary cards, and the existing quick-topic finder stays below.
 *
 * All three gateways reuse the existing product flows - no duplicate
 * matching or separate voice/phone systems.
 */
export function GatewayHero({ onOpenVoice, onSelectCategory, lang }) {
  const quickTopicsRef = useRef(null);

  const handleOpenFinder = () => {
    quickTopicsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const phoneCta = PHONE_GATEWAY_ENABLED
    ? (
      <a
        className="gateway-cta"
        href={CALL_TEL_HREF}
        aria-label={getLocaleString(lang, 'gatewayPhoneCta')}
      >
        {getLocaleString(lang, 'gatewayPhoneCta')}
      </a>
    )
    : (
      <div className="gateway-phone-actions">
        <span className="gateway-phone-status">
          {getLocaleString(lang, 'gatewayPhoneNote')}
        </span>
        <button
          type="button"
          className="gateway-cta gateway-cta-disabled"
          disabled
          aria-disabled="true"
        >
          {getLocaleString(lang, 'gatewayPhoneCta')}
        </button>
        <p className="gateway-phone-judge-note">
          {getLocaleString(lang, 'gatewayPhoneJudgeNote')}
        </p>
      </div>
    );

  return (
    <section className="gateway-hero" aria-label={getLocaleString(lang, 'homeHeroTitle')}>
      <div className="home-hero">
        <h2 className="home-hero-title">{getLocaleString(lang, 'homeHeroTitle')}</h2>
        <p className="home-hero-subtitle">{getLocaleString(lang, 'homeHeroSubtitle')}</p>
      </div>

      {/* PRIMARY gateway: the voice assistant. Voice-first, iconography-first. */}
      <div className="gateway-voice-primary-wrap">
        <button
          type="button"
          className="gateway-voice-primary"
          onClick={onOpenVoice}
          aria-label={getLocaleString(lang, 'gatewayVoicePrimaryAria')}
        >
          <span className="gateway-voice-mic" aria-hidden="true">
            <span className="gateway-voice-rings" />
            <span className="gateway-voice-rings gateway-voice-ring-second" />
            🎙️
          </span>
          <span className="gateway-voice-label">{getLocaleString(lang, 'gatewayVoicePrimaryLabel')}</span>
          <span className="gateway-voice-hint">{getLocaleString(lang, 'gatewayVoicePrimaryHint')}</span>
        </button>
      </div>

      {/* SECONDARY gateways: Website + Phone, visually subordinate. */}
      <div className="gateway-secondary-heading" aria-hidden="true">
        <span />
        <h3>{getLocaleString(lang, 'gatewaySecondaryHeading')}</h3>
        <span />
      </div>

      <div className="gateway-secondary-grid" role="list" aria-label={getLocaleString(lang, 'gatewaySecondaryHeading')}>
        {/* Website / Online Finder */}
        <article className="gateway-card gateway-card-secondary" role="listitem">
          <span className="gateway-icon" aria-hidden="true">🌐</span>
          <h4 className="gateway-title">{getLocaleString(lang, 'gatewayWebsiteTitle')}</h4>
          <p className="gateway-desc">{getLocaleString(lang, 'gatewayWebsiteDesc')}</p>
          <button
            type="button"
            className="gateway-cta"
            onClick={handleOpenFinder}
            aria-label={getLocaleString(lang, 'gatewayWebsiteCta')}
          >
            {getLocaleString(lang, 'gatewayWebsiteCta')}
          </button>
        </article>

        {/* Phone / CALL-E */}
        <article className="gateway-card gateway-card-secondary gateway-card-phone" role="listitem">
          <span className="gateway-icon" aria-hidden="true">☎️</span>
          <h4 className="gateway-title">{getLocaleString(lang, 'gatewayPhoneTitle')}</h4>
          <p className="gateway-desc">{getLocaleString(lang, 'gatewayPhoneDesc')}</p>
          {phoneCta}
        </article>
      </div>

      {/* Secondary quick-topic shortcuts (existing category finder flow) */}
      <div ref={quickTopicsRef} className="quick-topics" tabIndex={-1}>
        <CategoryGrid compact onSelectCategory={onSelectCategory} lang={lang} />
      </div>
    </section>
  );
}

export default GatewayHero;