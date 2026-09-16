import React from 'react';
import { STRINGS, CURRENT_LANG, t } from '../constants/strings';

export function WelcomeScreen({ onSelectSuggestion }) {
  const suggestions = STRINGS[CURRENT_LANG].suggestions;

  return (
    <section className="welcome-screen" aria-label="Welcome and topic suggestions">
      <div className="welcome-hero">
        <div className="welcome-emblem" aria-hidden="true">
          🇮🇳
        </div>
        <h2 className="welcome-title">{t('welcomeTitle')}</h2>
        <p className="welcome-subtitle">{t('welcomeSubtitle')}</p>
      </div>

      <div className="suggestions-container">
        <h3 className="suggestions-label">{t('suggestionsLabel')}</h3>
        <div className="suggestions-grid">
          {suggestions.map((item) => (
            <button
              key={item.id}
              type="button"
              className="suggestion-chip"
              onClick={() => onSelectSuggestion(item.message)}
            >
              <span className="suggestion-icon" aria-hidden="true">
                {item.icon}
              </span>
              <span className="suggestion-text">{item.label}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

export default WelcomeScreen;
