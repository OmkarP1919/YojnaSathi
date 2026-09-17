import React from 'react';
import { getLocaleString } from '../../constants/strings';
import RobotAvatar from './RobotAvatar';

export function ThinkingIndicator({ lang }) {
  return (
    <div className="voice-message-row voice-message-assistant" role="status" aria-live="polite">
      <RobotAvatar size={30} state="processing" className="voice-avatar-assistant" ariaHidden />
      <div className="voice-bubble voice-bubble-assistant voice-bubble-thinking">
        <span className="thinking-dots" aria-hidden="true">
          <span className="thinking-dot" />
          <span className="thinking-dot" />
          <span className="thinking-dot" />
        </span>
        <span className="thinking-label">{getLocaleString(lang, 'voiceMicProcessing')}</span>
      </div>
    </div>
  );
}

export default ThinkingIndicator;