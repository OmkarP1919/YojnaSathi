import { useCallback, useEffect, useRef, useState } from 'react';

const TARGET_SAMPLE_RATE = 16000;

/**
 * Mix all channels down to a single mono Float32 frame.
 */
function toMono(inputBuffer) {
  if (inputBuffer.numberOfChannels <= 1) {
    return new Float32Array(inputBuffer.getChannelData(0));
  }
  const first = inputBuffer.getChannelData(0);
  const mono = new Float32Array(first.length);
  for (let ch = 0; ch < inputBuffer.numberOfChannels; ch += 1) {
    const channel = inputBuffer.getChannelData(ch);
    for (let i = 0; i < first.length; i += 1) {
      mono[i] += channel[i];
    }
  }
  for (let i = 0; i < first.length; i += 1) {
    mono[i] /= inputBuffer.numberOfChannels;
  }
  return mono;
}

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i += 1) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

/**
 * Encode PCM Float32 frames as a 16-bit mono WAV Blob.
 * @param {Float32Array[]} chunks - List of captured frames
 * @param {number} sampleRate - Actual sample rate of the captured frames
 * @returns {Blob} - WAV Blob (type: 'audio/wav')
 */
function encodeWav(chunks, sampleRate) {
  const totalFrames = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const dataSize = totalFrames * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  writeString(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(view, 8, 'WAVE');
  writeString(view, 12, 'fmt ');
  view.setUint32(16, 16, true); // fmt chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono channel count
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeString(view, 36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, chunk[i]));
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
      offset += 2;
    }
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

/**
 * Browser microphone recorder that produces 16-bit mono PCM WAV Blobs.
 *
 * Flow: getUserMedia → Web Audio API → PCM frames → 16-bit WAV at ~16kHz.
 * Does not rely on MediaRecorder/webm so the output is directly consumable
 * by the backend Gemini STT pipeline.
 *
 * @returns {{
 *   isRecording: boolean,
 *   error: string | null,
 *   startRecording: () => Promise<void>,
 *   stopRecording: () => Promise<Blob | null>,
 *   getLevel: () => number,
 * }}
 */
export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [error, setError] = useState(null);

  const recordingRef = useRef(false);
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const chunksRef = useRef([]);
  const sampleRateRef = useRef(TARGET_SAMPLE_RATE);
  const levelRef = useRef(0);

  const getLevel = useCallback(() => levelRef.current, []);

  const cleanup = useCallback(() => {
    if (processorRef.current) {
      try {
        processorRef.current.disconnect();
      } catch (e) {
        // ignore teardown errors
      }
      processorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
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
    chunksRef.current = [];
    levelRef.current = 0;
  }, []);

  // Ensure tracks/context are released if the component unmounts mid-recording.
  useEffect(() => () => cleanup(), [cleanup]);

  const startRecording = useCallback(async () => {
    if (recordingRef.current) {
      return;
    }

    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices ||
      typeof navigator.mediaDevices.getUserMedia !== 'function'
    ) {
      setError('unsupported');
      return;
    }

    setError(null);

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
        video: false,
      });
    } catch (err) {
      if (err && err.name === 'NotAllowedError') {
        setError('permission');
      } else if (err && err.name === 'NotFoundError') {
        setError('no-microphone');
      } else {
        setError('mic-unavailable');
      }
      return;
    }

    let audioContext;
    try {
      // Attempt to create the context at 16kHz so no post-hoc resampling is
      // needed. Fall back to the platform default rate if unsupported.
      audioContext = new window.AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
      if (audioContext.state === 'suspended') {
        await audioContext.resume();
      }
    } catch (e) {
      try {
        audioContext = new window.AudioContext();
        if (audioContext.state === 'suspended') {
          await audioContext.resume();
        }
      } catch (err2) {
        stream.getTracks().forEach((track) => track.stop());
        setError('mic-unavailable');
        return;
      }
    }

    sampleRateRef.current = audioContext.sampleRate || TARGET_SAMPLE_RATE;
    chunksRef.current = [];
    recordingRef.current = true;

    try {
      const source = audioContext.createMediaStreamSource(stream);
      // ScriptProcessorNode is the widely supported native capture mechanism
      // and needs no additional module loading in a hackathon context.
      const processor = audioContext.createScriptProcessor(4096, 1, 1);

      processor.onaudioprocess = (event) => {
        if (!recordingRef.current) return;
        const samples = toMono(event.inputBuffer);
        chunksRef.current.push(samples);

        // RMS of this frame drives the live recording waveform. Scale it so
        // normal speech sits comfortably in the middle of the range.
        let sumSquares = 0;
        for (let i = 0; i < samples.length; i += 1) {
          sumSquares += samples[i] * samples[i];
        }
        const rms = Math.sqrt(sumSquares / samples.length);
        levelRef.current = Math.max(0.04, Math.min(1, rms * 4));
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      mediaStreamRef.current = stream;
      audioContextRef.current = audioContext;
      processorRef.current = processor;

      setIsRecording(true);
    } catch (err) {
      recordingRef.current = false;
      stream.getTracks().forEach((track) => track.stop());
      if (audioContext.state !== 'closed') {
        audioContext.close();
      }
      setError('mic-unavailable');
    }
  }, []);

  const stopRecording = useCallback(async () => {
    if (!recordingRef.current) {
      return null;
    }
    recordingRef.current = false;

    const captureChunks = chunksRef.current;
    const captureRate = sampleRateRef.current;

    // Tear down stream + context before encoding so the mic light goes off
    // immediately and encodeWav work is uninterrupted.
    if (processorRef.current) {
      try {
        processorRef.current.onaudioprocess = null;
      } catch (e) {
        // ignore
      }
    }
    cleanup();

    if (!captureChunks.length) {
      setIsRecording(false);
      return null;
    }

    const blob = encodeWav(captureChunks, captureRate);
    setIsRecording(false);
    return blob;
  }, [cleanup]);

  return { isRecording, error, startRecording, stopRecording, getLevel };
}

export default useAudioRecorder;