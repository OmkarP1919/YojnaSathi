import React from 'react';
import SchemeCard from '../SchemeCard';
import { getLocaleString } from '../../constants/strings';
import RobotAvatar from './RobotAvatar';

/**
 * Convert a flattened voice scheme item returned by the VoiceAgent API into the
 * `matchResult` shape consumed by the existing SchemeCard component.
 */
function toSchemeMatchResult(voiceScheme) {
  return {
    scheme: voiceScheme,
    relevance_score: voiceScheme.relevance_score,
    matched_reasons: voiceScheme.matched_reasons || [],
    reason_codes: voiceScheme.reason_codes || [],
    missing_information: [],
  };
}

/**
 * One voice-agent turn rendered as chat bubbles:
 * - user transcript: right aligned
 * - assistant reply: left aligned with a robot avatar
 * Scheme results render inside the assistant bubble using the existing SchemeCard.
 */
export function MessageBubble({ turn, onViewDetails, onPlayAudio, isCurrentlySpeaking, lang }) {
  const turnLang = turn.language && ['en', 'hi', 'mr'].includes(turn.language) ? turn.language : lang;
  const schemes = Array.isArray(turn.schemes) ? turn.schemes : [];
  const hasAudio = Boolean(turn.audioB64);
  const userText = (turn.userText || '').trim();

  return (
    <article className="voice-turn">
      {userText && (
        <div className="voice-message-row voice-message-user">
          <div className="voice-bubble voice-bubble-user">
            <p className="voice-bubble-label">{getLocaleString(turnLang, 'voiceUserLabel')}</p>
            <p className="voice-bubble-text">{userText}</p>
          </div>
        </div>
      )}

      <div className="voice-message-row voice-message-assistant">
        <RobotAvatar
          size={30}
          state={isCurrentlySpeaking ? 'speaking' : 'idle'}
          className="voice-avatar-assistant"
        />
        <div className="voice-bubble voice-bubble-assistant">
          <p className="voice-bubble-label">
            {isCurrentlySpeaking
              ? getLocaleString(turnLang, 'voiceMicSpeaking')
              : getLocaleString(turnLang, 'voiceAssistantSaid')}
          </p>

          {turn.assistantText && (
            <p className="voice-bubble-text">{turn.assistantText}</p>
          )}

          {schemes.length > 0 && (
            <div className="voice-scheme-block">
              <p className="voice-schemes-intro">
                {getLocaleString(turnLang, 'voiceSchemesIntro')}
              </p>
              <div className="voice-schemes-list">
                {schemes.map((schemeItem) => (
                  <SchemeCard
                    key={schemeItem.id}
                    matchResult={toSchemeMatchResult(schemeItem)}
                    onViewDetails={onViewDetails}
                    lang={turnLang}
                  />
                ))}
              </div>
              <p className="voice-schemes-note">{getLocaleString(turnLang, 'disclaimerText')}</p>
            </div>
          )}

          {hasAudio && (
            <button
              type="button"
              className="btn-play-response"
              onClick={() => onPlayAudio(turn)}
              aria-label={getLocaleString(turnLang, isCurrentlySpeaking ? 'voiceReplayResponse' : 'voicePlayResponse')}
            >
              {isCurrentlySpeaking ? '⏹' : '▶'} {getLocaleString(turnLang, isCurrentlySpeaking ? 'voiceStopSpeaking' : 'voicePlayResponse')}
            </button>
          )}

          {turn.ttsError && (
            <p className="voice-tts-note" role="note">
              {getLocaleString(turnLang, 'voiceErrorTts')}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

export default MessageBubble;