import React from 'react';
import { LANGUAGES } from '../constants/languages';
import { getLocaleString } from '../constants/strings';

export function Header({ currentView, onReset, lang, onLanguageChange }) {
  const isInsideSearch = currentView !== 'home';

  return (
    <header className="app-header" role="banner">
      <div className="header-container">
        <div className="brand-section">
          <button
            type="button"
            className="brand-link"
            onClick={onReset}
            aria-label={`${getLocaleString(lang, 'appTitle')} - ${getLocaleString(lang, 'homeNav')}`}
          >
            <span className="brand-emblem" aria-hidden="true">🏛️</span>
            <div className="brand-text">
              <h1 className="brand-title">{getLocaleString(lang, 'appTitle')}</h1>
              <p className="brand-tagline">{getLocaleString(lang, 'appTagline')}</p>
            </div>
          </button>
        </div>

        <div className="header-actions">
          {/* Language Switcher */}
          <nav className="lang-switcher" aria-label={getLocaleString(lang, 'languageSelect')}>
            <span className="lang-label" aria-hidden="true">🌐</span>
            <div className="lang-buttons" role="radiogroup" aria-label={getLocaleString(lang, 'languageSelect')}>
              {LANGUAGES.map((l) => (
                <button
                  key={l.code}
                  type="button"
                  role="radio"
                  aria-checked={lang === l.code}
                  className={`btn-lang ${lang === l.code ? 'active' : ''}`}
                  onClick={() => onLanguageChange(l.code)}
                >
                  {l.nativeLabel}
                </button>
              ))}
            </div>
          </nav>

          {/* New Search Action */}
          {isInsideSearch && (
            <button
              type="button"
              className="btn-new-search"
              onClick={onReset}
              aria-label={getLocaleString(lang, 'newSearch')}
            >
              <span aria-hidden="true">↺</span> {getLocaleString(lang, 'newSearch')}
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

export default Header;
