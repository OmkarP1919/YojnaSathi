import React from 'react';
import SchemeCard from './SchemeCard';

export function ChatMessage({ message }) {
  const isUser = message.sender === 'user';

  if (isUser) {
    return (
      <div className="message-wrapper user">
        <div className="message-bubble user-bubble">
          <p className="message-text">{message.text}</p>
        </div>
        <div className="avatar user-avatar" aria-hidden="true">
          👤
        </div>
      </div>
    );
  }

  return (
    <div className="message-wrapper assistant">
      <div className="avatar assistant-avatar" aria-hidden="true">
        🏛️
      </div>
      <div className="message-content-group">
        <div className="message-bubble assistant-bubble">
          <div className="message-text formatted-text">
            {message.text.split('\n').map((paragraph, pIdx) => (
              paragraph.trim() ? (
                <p key={pIdx}>{paragraph}</p>
              ) : (
                <br key={pIdx} />
              )
            ))}
          </div>
        </div>

        {message.schemes && message.schemes.length > 0 && (
          <div className="schemes-list" aria-label="Potentially relevant government schemes">
            {message.schemes.map((scheme) => (
              <SchemeCard key={scheme.id} scheme={scheme} />
            ))}
          </div>
        )}

        {message.disclaimer && (
          <aside className="disclaimer-banner" role="note">
            <span className="disclaimer-icon" aria-hidden="true">ℹ️</span>
            <span className="disclaimer-text">{message.disclaimer}</span>
          </aside>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
