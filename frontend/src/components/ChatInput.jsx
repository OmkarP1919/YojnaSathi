import React, { useState, useRef, useEffect } from 'react';
import { t } from '../constants/strings';

export function ChatInput({ onSendMessage, isLoading }) {
  const [inputValue, setInputValue] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    if (!isLoading && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isLoading]);

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = inputValue.trim();
    if (!trimmed || isLoading) return;
    onSendMessage(trimmed);
    setInputValue('');
  };

  return (
    <form className="chat-input-form" onSubmit={handleSubmit}>
      <div className="input-container">
        <textarea
          ref={inputRef}
          className="chat-textarea"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t('inputPlaceholder')}
          rows="2"
          disabled={isLoading}
          aria-label="Describe your situation to find schemes"
        />
        <button
          type="submit"
          className="btn-send"
          disabled={isLoading || !inputValue.trim()}
          aria-label={t('sendButtonAriaLabel')}
        >
          <span className="send-text">{t('sendButtonLabel')}</span>
          <span className="send-icon" aria-hidden="true">➤</span>
        </button>
      </div>
    </form>
  );
}

export default ChatInput;
