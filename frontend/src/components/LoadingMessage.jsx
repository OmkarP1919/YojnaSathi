import React from 'react';
import { t } from '../constants/strings';

export function LoadingMessage() {
  return (
    <div className="message-wrapper assistant" role="status" aria-live="polite">
      <div className="avatar assistant-avatar" aria-hidden="true">
        🏛️
      </div>
      <div className="message-bubble assistant-bubble loading-bubble">
        <div className="typing-indicator" aria-hidden="true">
          <span className="dot"></span>
          <span className="dot"></span>
          <span className="dot"></span>
        </div>
        <span className="loading-text">{t('loadingText')}</span>
      </div>
    </div>
  );
}

export default LoadingMessage;
