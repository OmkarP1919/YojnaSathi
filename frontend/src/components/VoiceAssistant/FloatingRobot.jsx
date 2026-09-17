import React from 'react';
import { getLocaleString } from '../../constants/strings';
import RobotAvatar from './RobotAvatar';

/**
 * Floating YojnaSathi robot assistant button.
 * Reflects the real voice-agent state (idle/listening/processing/speaking)
 * and opens the expanded voice panel. Shows a subtle greeting bubble when idle.
 */
export function FloatingRobot({ open, status, lang, onToggle }) {
  const bubbleLabel = getLocaleString(lang, 'voiceRobotGreeting');
  const openLabel = getLocaleString(lang, 'voiceOpenRobot');
  const closeLabel = getLocaleString(lang, 'voiceClosePanel');

  return (
    <div className={`voice-robot-wrap voice-robot-${status}${open ? ' is-open' : ''}`}>
      {!open && status === 'idle' && (
        <div className="voice-robot-bubble" aria-hidden="true">
          {bubbleLabel}
        </div>
      )}

      <button
        type="button"
        className="voice-robot-button"
        onClick={onToggle}
        aria-label={open ? closeLabel : openLabel}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls="voice-panel"
      >
        <span className="voice-robot-rings" aria-hidden="true" />
        <span className="voice-robot-rings voice-robot-ring-second" aria-hidden="true" />
        <RobotAvatar size={40} state={status} className="voice-robot-face" />
        <span className="voice-robot-open-badge" aria-hidden="true">
          {open ? '✕' : '+'}
        </span>
      </button>
    </div>
  );
}

export default FloatingRobot;