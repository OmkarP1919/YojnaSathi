import React, { useRef, useState } from 'react';
import { getLocaleString } from '../../constants/strings';

export function ConversationInputDock({ onSend, disabled, lang }) {
  const [value, setValue] = useState('');
  const inputRef = useRef(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue('');
    inputRef.current?.focus();
  };

  return (
    <form className="voice-input-dock" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="voice-conversation-input">
        {getLocaleString(lang, 'voicePlaceholder')}
      </label>
      <div className="voice-input-row">
        <input
          id="voice-conversation-input"
          ref={inputRef}
          type="text"
          className="input-text voice-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={getLocaleString(lang, 'voicePlaceholder')}
          disabled={disabled}
          autoComplete="off"
          enterKeyHint="send"
        />
        <button
          type="submit"
          className="btn-send-voice"
          disabled={disabled || !value.trim()}
          aria-label={getLocaleString(lang, 'voiceSendLabel')}
        >
          ➤
        </button>
      </div>
    </form>
  );
}

export default ConversationInputDock;