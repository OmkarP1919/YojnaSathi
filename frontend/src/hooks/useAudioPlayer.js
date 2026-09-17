import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Decode a base64 string into an ArrayBuffer. decodeAudioData detaches the
 * buffer, so a fresh copy is returned each time.
 */
function base64ToArrayBuffer(base64) {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer.slice(0);
}

/**
 * Tiny WAV playback helper for the assistant's TTS output.
 *
 * @returns {{
 *   isSpeaking: boolean,
 *   playbackFailed: boolean,
 *   ensureUnlocked: () => void,
 *   play: (base64Audio: string, mimeType?: string) => Promise<boolean>,
 *   stop: () => void,
 * }}
 */
export function useAudioPlayer() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [playbackFailed, setPlaybackFailed] = useState(false);

  const audioContextRef = useRef(null);
  const sourceRef = useRef(null);

  const stop = useCallback(() => {
    if (sourceRef.current) {
      try {
        sourceRef.current.onended = null;
        sourceRef.current.stop();
      } catch (e) {
        // ignore already-stopped sources
      }
      try {
        sourceRef.current.disconnect();
      } catch (e) {
        // ignore teardown errors
      }
      sourceRef.current = null;
    }
    setIsSpeaking(false);
  }, []);

  const getContext = useCallback(() => {
    if (!audioContextRef.current) {
      audioContextRef.current = new window.AudioContext();
    }
    return audioContextRef.current;
  }, []);

  // Unlocking the AudioContext is best done inside a user gesture (the push).
  const ensureUnlocked = useCallback(() => {
    const ctx = getContext();
    if (ctx.state === 'suspended') {
      ctx.resume();
    }
  }, [getContext]);

  // Reuse one context for the lifetime of the view and always tear it down
  // on unmount so no mic/speaker resources leak.
  useEffect(
    () => () => {
      if (audioContextRef.current) {
        try {
          if (audioContextRef.current.state !== 'closed') {
            audioContextRef.current.close();
          }
        } catch (e) {
          // ignore teardown errors
        }
        audioContextRef.current = null;
      }
    },
    [],
  );

  const play = useCallback(
    async (base64Audio, mimeType = 'audio/wav') => {
      if (!base64Audio) {
        return false;
      }
      stop();

      setPlaybackFailed(false);

      // The backend mock TTS returns UTF-8 text bytes, not audio; skip playback.
      if (!mimeType || !mimeType.startsWith('audio/')) {
        return false;
      }

      let ctx;
      try {
        ctx = getContext();
        if (ctx.state === 'suspended') {
          await ctx.resume();
        }
        const arrayBuffer = base64ToArrayBuffer(base64Audio);
        const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);

        source.onended = () => {
          sourceRef.current = null;
          setIsSpeaking(false);
        };

        // Stop any prior source before starting the new one.
        sourceRef.current = source;
        setIsSpeaking(true);
        source.start(0);
        return true;
      } catch (err) {
        setPlaybackFailed(true);
        setIsSpeaking(false);
        return false;
      }
    },
    [getContext, stop],
  );

  return { isSpeaking, playbackFailed, ensureUnlocked, play, stop };
}

export default useAudioPlayer;