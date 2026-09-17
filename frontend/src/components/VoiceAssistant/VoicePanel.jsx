import React, { useEffect, useRef, useState } from 'react';
import { LANGUAGES } from '../../constants/languages';
import { getLocaleString } from '../../constants/strings';
import MessageBubble from './MessageBubble';
import ConversationInputDock from './ConversationInputDock';
import ThinkingIndicator from './ThinkingIndicator';
import RobotAvatar from './RobotAvatar';

const BAR_COUNT = 5;

/**
 * Expanded voice-assistant panel (fixed bottom-right card).
 * Voice is the primary interaction: a dominant central microphone with a
 * live waveform; the conversation transcript and scheme cards are supporting.
 */
export function VoicePanel({
  open,
  focusMode = false,
  lang,
  onLanguageChange,
  status,
  playerIsSpeaking,
  recorder,
  turns,
  typing,
  starters,
  micErrorKey,
  flowErrorMessage,
  onMicPress,
  onMicRelease,
  onSendText,
  onPlayTurnAudio,
  onReset,
  onClose,
  onViewDetails,
  scrollRef,
  closeButtonRef,
}) {
  const [micLevel, setMicLevel] = useState(0);
  const lastLevelRef = useRef(0);

  // Live waveform: read the recorder RMS level per animation frame while
  // listening so the equalizer responds to real microphone activity.
  useEffect(() => {
    if (status !== 'listening') return;
    let rafId;
    const tick = () => {
      const lvl = recorder.getLevel ? recorder.getLevel() : 0;
      if (Math.abs(lvl - lastLevelRef.current) >= 0.02) {
        lastLevelRef.current = lvl;
        setMicLevel(lvl);
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [status, recorder]);

  useEffect(() => {
    if (status !== 'listening') {
      lastLevelRef.current = 0;
      setMicLevel(0);
    }
  }, [status]);

  const statusTextKey = {
    idle: 'voiceMicIdleHint',
    listening: 'voiceMicListening',
    processing: 'voiceMicProcessing',
    speaking: 'voiceMicSpeaking',
    error: 'voiceMicIdleHint',
  }[status];

  const micAriaLabel =
    status === 'listening'
      ? getLocaleString(lang, 'voiceMicHoldHint')
      : getLocaleString(lang, 'voiceTapToSpeak');

  const micDisabled = status === 'processing' || status === 'speaking';
  const showWaveform = status === 'listening' || status === 'speaking';

  const barStyle = (index) => {
    if (status === 'listening') {
      const lvl = Math.max(0.18, micLevel);
      return { transform: `scaleY(${0.28 + lvl * 0.72 * (0.75 + index * 0.06)})` };
    }
    // Speaking: gentle passive bars without fabricating mic input.
    return null;
  };

  return (
    <div
      id="voice-panel"
      className={`voice-panel${open ? ' voice-panel-open' : ''}${focusMode ? ' voice-panel-fullscreen' : ''}`}
      role="dialog"
      aria-label={getLocaleString(lang, 'voicePanelTitle')}
      aria-modal={focusMode || undefined}
      aria-hidden={!open}
    >
      {/* Header */}
      <header className="voice-panel-header">
        <div className="voice-panel-identity">
          <RobotAvatar size={34} state={status} className="voice-panel-avatar" />
          <div className="voice-panel-titles">
            <h2 className="voice-panel-title">{getLocaleString(lang, 'voicePanelTitle')}</h2>
            <p className="voice-panel-status-text" role="status" aria-live="polite">
              {getLocaleString(lang, statusTextKey)}
            </p>
          </div>
        </div>

        <div className="voice-panel-actions">
          <nav className="voice-panel-lang" aria-label={getLocaleString(lang, 'languageSelect')}>
            {LANGUAGES.map((l) => (
              <button
                key={l.code}
                type="button"
                className={`voice-panel-lang-btn${lang === l.code ? ' active' : ''}`}
                onClick={() => onLanguageChange(l.code)}
                aria-pressed={lang === l.code}
              >
                {l.nativeLabel}
              </button>
            ))}
          </nav>
          <button
            type="button"
            className="voice-panel-icon-btn voice-panel-reset"
            onClick={onReset}
            aria-label={getLocaleString(lang, 'voiceNewConversation')}
            title={getLocaleString(lang, 'voiceNewConversation')}
          >
            ↺
          </button>
          <button
            type="button"
            className="voice-panel-icon-btn voice-panel-close"
            onClick={onClose}
            ref={closeButtonRef}
            aria-label={getLocaleString(lang, 'voiceClosePanel')}
          >
            ✕
          </button>
        </div>
      </header>

      {/* Conversation transcript */}
      <div
        className="voice-conversation"
        role="log"
        aria-live="polite"
        aria-label={getLocaleString(lang, 'voiceTranscriptLabel')}
      >
        {!turns.length && !typing && (
          <div className="voice-welcome">
            <RobotAvatar size={64} state="idle" className="voice-welcome-avatar" />
            <p className="voice-welcome-greeting">{getLocaleString(lang, 'voiceWelcomeGreeting')}</p>
            <p className="voice-welcome-intro">{getLocaleString(lang, 'voiceRobotGreeting')}</p>
            <div className="voice-starters">
              <p className="voice-starters-heading">{getLocaleString(lang, 'voiceStarterHeading')}</p>
              <div className="voice-starter-chips">
                {starters.map((starter) => (
                  <button
                    key={starter.key}
                    type="button"
                    className="voice-starter-chip"
                    onClick={() => onSendText(starter.text)}
                  >
                    {starter.text}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {turns.map((turn) => (
          <MessageBubble
            key={turn.id}
            turn={turn}
            onViewDetails={onViewDetails}
            onPlayAudio={onPlayTurnAudio}
            isCurrentlySpeaking={playerIsSpeaking}
            lang={lang}
          />
        ))}

        {typing && <ThinkingIndicator lang={lang} />}

        <div ref={scrollRef} className="voice-scroll-sentinel" aria-hidden="true" />
      </div>

      {/* Voice-first input area */}
      <footer className="voice-input-area">
        {(micErrorKey || flowErrorMessage) && (
          <div className="voice-errors">
            {micErrorKey && (
              <div className="voice-error" role="alert">
                <p className="voice-error-text">{getLocaleString(lang, micErrorKey)}</p>
              </div>
            )}
            {flowErrorMessage && (
              <div className="voice-error" role="alert">
                <p className="voice-error-text">{flowErrorMessage}</p>
              </div>
            )}
          </div>
        )}

        <div className={`voice-mic-center voice-mic-${status}`}>
          <div className={`voice-waveform${showWaveform ? ' is-visible' : ''}`} aria-hidden="true">
            {Array.from({ length: BAR_COUNT }, (_, i) => (
              <span
                key={i}
                className="voice-wave-bar"
                style={barStyle(i)}
              />
            ))}
          </div>

          <button
            type="button"
            className="voice-mic-button"
            onPointerDown={onMicPress}
            onPointerUp={onMicRelease}
            onPointerCancel={onMicRelease}
            onKeyDown={(e) => {
              if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) {
                e.preventDefault();
                onMicPress(e);
              }
            }}
            onKeyUp={(e) => {
              if (e.key === ' ' || e.key === 'Enter') {
                e.preventDefault();
                onMicRelease(e);
              }
            }}
            aria-label={micAriaLabel}
            aria-pressed={status === 'listening'}
            disabled={micDisabled}
          >
            <span className="voice-mic-rings" aria-hidden="true" />
            <span className="voice-mic-icon" aria-hidden="true">🎙️</span>
          </button>
          <p className="voice-mic-hint" role="status" aria-live="polite">
            {status === 'listening'
              ? getLocaleString(lang, 'voiceMicHoldHint')
              : getLocaleString(lang, 'voiceTapToSpeak')}
          </p>
        </div>

        <ConversationInputDock
          onSend={onSendText}
          disabled={status === 'processing' || status === 'speaking' || status === 'listening'}
          lang={lang}
        />
      </footer>
    </div>
  );
}

export default VoicePanel;