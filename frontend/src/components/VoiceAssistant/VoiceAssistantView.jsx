import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { processVoiceAudio, processVoiceMessage, resetVoiceSession, startVoiceSession } from '../../api';
import { getLocaleString } from '../../constants/strings';
import { useAudioRecorder } from '../../hooks/useAudioRecorder';
import { useAudioPlayer } from '../../hooks/useAudioPlayer';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import FloatingRobot from './FloatingRobot';
import VoicePanel from './VoicePanel';

const VALID_LANGS = ['en', 'hi', 'mr'];
const MIN_RECORDING_MS = 400;

const STARTER_KEYS = ['voiceStarterFarmer', 'voiceStarterScholarship', 'voiceStarterHousing'];

let turnCounter = 0;
function nextTurnId() {
  turnCounter += 1;
  return `vt-${Date.now()}-${turnCounter}`;
}

function createSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `voice-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const MIC_ERROR_KEYS = {
  permission: 'voiceErrorMicPermission',
  'no-microphone': 'voiceErrorNoMicrophone',
  'mic-unavailable': 'voiceErrorMicUnavailable',
  unsupported: 'voiceErrorUnsupported',
};

/**
 * Site-wide floating YojnaSathi voice agent.
 * Owns the real voice state (recording, agent round-trips, TTS playback) and
 * renders the floating robot plus the expanded voice panel around it. The
 * microphone remains the primary interaction; the transcript is supporting.
 */
export function VoiceAssistantView({ lang, openSignal = 0, onViewDetails, onLanguageChange }) {
  const [panelOpen, setPanelOpen] = useState(false);
  const [turns, setTurns] = useState([]);
  const [status, setStatus] = useState('idle'); // 'idle' | 'listening' | 'processing' | 'speaking' | 'error'
  const [sessionLang, setSessionLang] = useState(null); // null = language-selection screen, string = active session language
  const [micErrorKey, setMicErrorKey] = useState(null);
  const [flowError, setFlowError] = useState(null); // { kind: 'network'|'server'|'playback'|'empty', message? }
  const [typing, setTyping] = useState(false);
  const scrollRef = useRef(null);
  const robotFocusRef = useRef(null);
  const closeButtonRef = useRef(null);
  const startingRef = useRef(false);
  const startedSessionRef = useRef(null);

  // Mobile (< <=768px) opens the voice assistant as a dedicated full-screen
  // focused mode instead of the floating desktop card. No portrait/landscape
  // magic - just one mobile breakpoint, mirroring the existing @media rules.
  const isMobile = useMediaQuery('(max-width: 768px)');
  const focusMode = isMobile && panelOpen;

  const sessionRef = useRef(createSessionId());
  const recorder = useAudioRecorder();
  const player = useAudioPlayer();

  const statusRef = useRef(status);
  const micHeldRef = useRef(false);
  const recordingStartRef = useRef(0);

  // Effective panel language: the selected voice-session language once chosen,
  // otherwise the current site language.
  const effectiveLang = sessionLang || lang;

  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  // Lock background scroll while the mobile full-screen voice mode is open;
  // the homepage stays behind an opaque overlay so nothing is clickable.
  useEffect(() => {
    if (!focusMode) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [focusMode]);

  // Surface recorder errors (permission, no mic, unsupported browser, etc.)
  useEffect(() => {
    if (recorder.error) {
      setMicErrorKey(MIC_ERROR_KEYS[recorder.error] || 'voiceErrorMicUnavailable');
    }
  }, [recorder.error]);

  // Open the voice panel when the homepage "Speak with YojnaSathi" gateway fires.
  useEffect(() => {
    if (openSignal > 0) {
      setPanelOpen(true);
    }
  }, [openSignal]);

  // When audio finishes playing, return to idle.
  useEffect(() => {
    if (player.isSpeaking) {
      setStatus((prev) => (prev === 'processing' ? prev : 'speaking'));
    } else {
      setStatus((prev) => (prev === 'speaking' ? 'idle' : prev));
    }
  }, [player.isSpeaking]);

  // Safety: cancel any active recording if the tab/window loses focus.
  useEffect(() => {
    const cancelOnBlur = () => {
      if (micHeldRef.current && recorder.isRecording) {
        micHeldRef.current = false;
        recorder.stopRecording();
      }
    };
    window.addEventListener('blur', cancelOnBlur);
    document.addEventListener('visibilitychange', cancelOnBlur);
    return () => {
      window.removeEventListener('blur', cancelOnBlur);
      document.removeEventListener('visibilitychange', cancelOnBlur);
    };
  }, [recorder]);

  // Close with Escape and hand focus back to the robot.
  useEffect(() => {
    if (!panelOpen) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setPanelOpen(false);
        robotFocusRef.current?.focus();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [panelOpen]);

  // Auto-scroll the panel conversation to the newest message.
  const scrollToBottom = useCallback(() => {
    scrollRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, []);

  useEffect(() => {
    if (!panelOpen) return;
    scrollToBottom();
  }, [turns, typing, status, panelOpen, scrollToBottom]);

  // Restore focus when the panel opens.
  useEffect(() => {
    if (panelOpen) {
      closeButtonRef.current?.focus();
    }
  }, [panelOpen]);

  const starters = useMemo(
    () => STARTER_KEYS.map((key) => ({ key, text: getLocaleString(effectiveLang, key) })),
    [effectiveLang],
  );

  const handleSelectLanguage = useCallback(
    (code) => {
      setSessionLang(code);
      onLanguageChange(code);
    },
    [onLanguageChange],
  );

  const appendTurn = useCallback((turn) => {
    setTurns((prev) => [...prev, turn]);
  }, []);

  // Agent-initiated conversation: fetch the localized greeting + first question
  // (with TTS audio) and present it as the opening assistant turn.
  const startSession = useCallback(
    async (language) => {
      const currentSession = sessionRef.current;
      try {
        const data = await startVoiceSession({ sessionId: currentSession, language });
        if (sessionRef.current !== currentSession) {
          setStatus('idle');
          return;
        }

        const responseLang = VALID_LANGS.includes(data?.language) ? data.language : language;
        const turn = {
          id: nextTurnId(),
          userText: '',
          assistantText: (data && data.response_text) || '',
          language: responseLang,
          schemes: Array.isArray(data?.schemes) ? data.schemes : [],
          audioB64: (data && data.audio_b64) || '',
          audioContentType: (data && data.audio_content_type) || 'audio/wav',
          ttsError: (data && data.tts_error) || null,
        };

        appendTurn(turn);
        setTyping(false);

        if (turn.audioB64) {
          const ok = await player.play(turn.audioB64, turn.audioContentType);
          if (ok) {
            setStatus('speaking');
          } else {
            setStatus('idle');
          }
        } else {
          setStatus('idle');
        }
      } catch (err) {
        if (sessionRef.current !== currentSession) {
          setStatus('idle');
          setTyping(false);
          return;
        }
        setFlowError(
          err.request && !err.response ? { kind: 'network' } : { kind: 'server' },
        );
        setStatus('idle');
        setTyping(false);
      }
    },
    [appendTurn, player.play],
  );

  // Auto-start the conversation once the panel is open AND the user has
  // explicitly selected a language. `startedSessionRef` fires exactly ONCE
  // per session so failures do not loop and re-renders do not re-greet.
  useEffect(() => {
    if (!panelOpen || sessionLang === null) {
      return;
    }
    if (startingRef.current) {
      return;
    }
    if (startedSessionRef.current === sessionRef.current) {
      return;
    }
    startedSessionRef.current = sessionRef.current;
    startingRef.current = true;
    setStatus('processing');
    setTyping(true);
    startSession(sessionLang).finally(() => {
      startingRef.current = false;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [panelOpen, sessionLang, startSession, sessionRef.current]);

  const sendAudio = useCallback(
    async (audioBlob) => {
      const currentSession = sessionRef.current;
      setStatus('processing');
      setFlowError(null);
      setMicErrorKey(null);

      try {
        const data = await processVoiceAudio({
          sessionId: currentSession,
          audioBlob,
          language: sessionLang,
        });

        // Ignore responses that arrive after the user reset the conversation.
        if (sessionRef.current !== currentSession) {
          setStatus('idle');
          return;
        }

        const responseLang = VALID_LANGS.includes(data?.language) ? data.language : lang;
        const turn = {
          id: nextTurnId(),
          userText: (data && data.transcript) || '',
          assistantText: (data && data.response_text) || '',
          language: responseLang,
          schemes: Array.isArray(data?.schemes) ? data.schemes : [],
          audioB64: (data && data.audio_b64) || '',
          audioContentType: (data && data.audio_content_type) || 'audio/wav',
          ttsError: (data && data.tts_error) || null,
        };

        appendTurn(turn);

        if (!turn.userText.trim()) {
          setFlowError({ kind: 'empty' });
          setStatus('idle');
          return;
        }

        if (turn.audioB64) {
          const ok = await player.play(turn.audioB64, turn.audioContentType);
          if (ok) {
            setStatus('speaking');
          } else {
            setFlowError(player.playbackFailed ? { kind: 'playback' } : { kind: 'server' });
            setStatus('idle');
          }
        } else {
          setStatus('idle');
        }
      } catch (err) {
        if (sessionRef.current !== currentSession) {
          setStatus('idle');
          return;
        }
        if (err.response && err.response.data && err.response.data.detail) {
          setFlowError({ kind: 'server', message: String(err.response.data.detail) });
        } else if (err.request && !err.response) {
          setFlowError({ kind: 'network' });
        } else {
          setFlowError({ kind: 'server' });
        }
        setStatus('idle');
      }
    },
    [appendTurn, sessionLang, player],
  );

  const sendText = useCallback(
    async (text, language = sessionLang) => {
      const trimmed = (text || '').trim();
      if (!trimmed) return;
      const currentSession = sessionRef.current;
      setStatus('processing');
      setFlowError(null);
      setMicErrorKey(null);
      setTyping(true);

      try {
        const data = await processVoiceMessage({
          sessionId: currentSession,
          message: trimmed,
          language,
        });
        if (sessionRef.current !== currentSession) {
          setStatus('idle');
          return;
        }
        const responseLang = VALID_LANGS.includes(data?.language) ? data.language : language;
        appendTurn({
          id: nextTurnId(),
          userText: trimmed,
          assistantText: (data && data.response_text) || '',
          language: responseLang,
          schemes: Array.isArray(data?.schemes) ? data.schemes : [],
          audioB64: '',
          audioContentType: 'audio/wav',
          ttsError: null,
        });
        setStatus('idle');
        setTyping(false);
      } catch (err) {
        if (sessionRef.current !== currentSession) {
          setStatus('idle');
          setTyping(false);
          return;
        }
        setFlowError(
          err.request && !err.response ? { kind: 'network' } : { kind: 'server' },
        );
        setStatus('idle');
        setTyping(false);
      }
    },
    [appendTurn, sessionLang],
  );

  const handleMicPress = useCallback(async () => {
    if (statusRef.current === 'processing' || statusRef.current === 'speaking' || recorder.isRecording) {
      return;
    }
    setMicErrorKey(null);
    setFlowError(null);
    recordingStartRef.current = Date.now();
    micHeldRef.current = true;
    player.ensureUnlocked();
    // Enter "listening" immediately so the press gives instant feedback even
    // while getUserMedia/AudioContext are still settling.
    setStatus('listening');
    await recorder.startRecording();
    // The user released before the stream was ready, or the mic failed to
    // start: discard the latched capture and settle back to idle instead of
    // leaving the panel stuck in "listening".
    if (recorder.error || !micHeldRef.current) {
      await recorder.stopRecording();
      setStatus('idle');
    }
  }, [player, recorder]);

  const handleMicRelease = useCallback(async () => {
    if (!micHeldRef.current) return;
    micHeldRef.current = false;
    const blob = await recorder.stopRecording();

    // Discard accidental taps (< 400ms) silently instead of erroring.
    if (!blob || Date.now() - recordingStartRef.current < MIN_RECORDING_MS) {
      setStatus('idle');
      return;
    }
    sendAudio(blob);
  }, [recorder, sendAudio]);

  const handlePlayTurnAudio = useCallback(
    async (turn) => {
      if (!turn.audioB64) return;
      const ok = await player.play(turn.audioB64, turn.audioContentType);
      if (ok) {
        setStatus('speaking');
      } else if (player.playbackFailed) {
        setFlowError({ kind: 'playback' });
      }
    },
    [player],
  );

  const handleReset = useCallback(async () => {
    const oldSession = sessionRef.current;
    try {
      await resetVoiceSession(oldSession);
    } catch (e) {
      // Best-effort backend reset; the local conversation resets regardless.
    }
    player.stop();
    recorder.stopRecording();
    micHeldRef.current = false;
    startingRef.current = false;
    sessionRef.current = createSessionId();
    setSessionLang(null);
    setTurns([]);
    setStatus('idle');
    setMicErrorKey(null);
    setFlowError(null);
    setTyping(false);
  }, [player, recorder]);

  const handleToggle = useCallback(async () => {
    if (panelOpen) {
      if (micHeldRef.current && recorder.isRecording) {
        micHeldRef.current = false;
        await recorder.stopRecording();
        setStatus('idle');
      }
      setPanelOpen(false);
      robotFocusRef.current?.focus();
    } else {
      setPanelOpen(true);
    }
  }, [panelOpen, recorder]);

  const flowErrorMessage = useMemo(() => {
    if (!flowError) return null;
    if (flowError.kind === 'network') return getLocaleString(effectiveLang, 'voiceErrorNetwork');
    if (flowError.kind === 'playback') return getLocaleString(effectiveLang, 'voicePlayBackFailed');
    if (flowError.kind === 'empty') return getLocaleString(effectiveLang, 'voiceErrorEmptyRecording');
    return flowError.message || getLocaleString(effectiveLang, 'voiceErrorGeneric');
  }, [flowError, effectiveLang]);

  return (
    <div className={`voice-launcher${focusMode ? ' voice-focus-mode' : ''}`}>
      <VoicePanel
        open={panelOpen}
        focusMode={focusMode}
        lang={effectiveLang}
        sessionActive={sessionLang !== null}
        onLanguageChange={onLanguageChange}
        onSelectLanguage={handleSelectLanguage}
        status={status}
        playerIsSpeaking={player.isSpeaking}
        recorder={recorder}
        turns={turns}
        typing={typing}
        starters={starters}
        micErrorKey={micErrorKey}
        flowErrorMessage={flowErrorMessage}
        onMicPress={handleMicPress}
        onMicRelease={handleMicRelease}
        onSendText={sendText}
        onPlayTurnAudio={handlePlayTurnAudio}
        onReset={handleReset}
        onClose={handleToggle}
        onViewDetails={onViewDetails}
        scrollRef={scrollRef}
        closeButtonRef={closeButtonRef}
      />
      <div ref={robotFocusRef}>
        <FloatingRobot open={panelOpen} status={status} lang={lang} onToggle={handleToggle} />
      </div>
    </div>
  );
}

export default VoiceAssistantView;