import React from 'react';
import { t } from '../constants/strings';

export function Header({ onReset, hasConversation }) {
  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="brand-badge" aria-hidden="true">
          🏛️
        </div>
        <div className="brand-text">
          <h1 className="app-title">{t('appTitle')}</h1>
          <p className="app-subtitle">{t('appSubtitle')}</p>
        </div>
      </div>
      {hasConversation && (
        <button
          type="button"
          onClick={onReset}
          className="btn-new-chat"
          aria-label={t('resetAriaLabel')}
          title={t('resetAriaLabel')}
        >
          <span aria-hidden="true">🔄</span> {t('newConversation')}
        </button>
      )}
    </header>
  );
}

export default Header;
