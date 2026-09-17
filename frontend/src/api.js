import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

/**
 * Fetch scheme recommendations for a structured citizen profile via POST /api/recommend.
 * @param {object} profile - CitizenProfile object
 * @param {string|null} category - Selected website domain category (e.g., 'farmers', 'education')
 * @returns {Promise<object>} - RecommendationResponse data { success, count, disclaimer, results }
 */
export async function getRecommendations(profile, category = null) {
  const payload = {
    profile: profile || {},
  };
  if (category) {
    payload.category = category;
  }
  const response = await apiClient.post('/api/recommend', payload);
  return response.data;
}

/**
 * Send citizen natural language message with profile continuation to /api/chat.
 * Preserved for conversational use.
 * @param {string} message - Citizen message
 * @param {object} profile - Current citizen profile object
 * @returns {Promise<object>} - Backend chat response data
 */
export async function sendChatMessage(message, profile = {}) {
  const response = await apiClient.post('/api/chat', {
    message,
    profile: profile || {},
  });
  return response.data;
}

/**
 * Send a text message to the shared VoiceAgent via POST /api/voice/process.
 * Backend maintains conversation state keyed by session_id.
 * @param {object} params - { sessionId, message, language }
 * @param {string} params.sessionId - Unique conversation session id
 * @param {string} params.message - User text message
 * @param {string} [params.language] - Optional language hint ('en' | 'hi' | 'mr')
 * @returns {Promise<object>} - VoiceAgent response { response_text, language, next_action, schemes, profile }
 */
export async function processVoiceMessage({ sessionId, message, language = null }) {
  const payload = {
    session_id: sessionId,
    message: message || '',
  };
  if (language) {
    payload.language = language;
  }
  const response = await apiClient.post('/api/voice/process', payload);
  return response.data;
}

/**
 * Begin a new agent-initiated conversation via POST /api/voice/start.
 * The backend greets the user with a localized message plus the first
 * discovery question (TTS audio included), so no user input is required.
 * @param {object} params - { sessionId, language }
 * @param {string} params.sessionId - Unique conversation session id
 * @param {string} [params.language] - Optional language hint ('en' | 'hi' | 'mr')
 * @returns {Promise<object>} - { session_id, response_text, language, stage, next_action, audio_b64, schemes }
 */
export async function startVoiceSession({ sessionId, language = null }) {
  const payload = {
    session_id: sessionId,
  };
  if (language) {
    payload.language = language;
  }
  const response = await apiClient.post('/api/voice/start', payload);
  return response.data;
}

/**
 * Reset a VoiceAgent conversation session via POST /api/voice/reset.
 * @param {string} sessionId - Unique conversation session id
 * @returns {Promise<object>} - { success, session_id }
 */
export async function resetVoiceSession(sessionId) {
  const response = await apiClient.post('/api/voice/reset', { session_id: sessionId });
  return response.data;
}

/**
 * Send raw audio to the voice pipeline via POST /api/voice/process/audio.
 * Backend chains STT → VoiceAgent → TTS and returns transcript + audio.
 * @param {object} params - { sessionId, audioBlob, language }
 * @param {string} params.sessionId - Unique conversation session id
 * @param {Blob} params.audioBlob - WAV audio blob from the browser recorder
 * @param {string} [params.language] - UI language hint ('en' | 'hi' | 'mr')
 * @returns {Promise<object>} - { session_id, transcript, response_text, language, next_action, schemes, audio_b64, tts_error }
 */
export async function processVoiceAudio({ sessionId, audioBlob, language = null }) {
  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.wav');
  formData.append('session_id', sessionId);
  if (language) {
    formData.append('language', language);
  }
  const response = await apiClient.post('/api/voice/process/audio', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  });
  return response.data;
}

/**
 * Fetch full scheme details by ID from /api/schemes/{scheme_id}, with optional location-filtering.
 * @param {string} schemeId - Scheme unique identifier
 * @param {object} [locationParams] - Optional { state, district, taluka }
 * @returns {Promise<object>} - Scheme object
 */
export async function fetchSchemeDetails(schemeId, { state, district, taluka } = {}) {
  const params = {};
  if (state) params.state = state;
  if (district) params.district = district;
  if (taluka) params.taluka = taluka;
  const response = await apiClient.get(`/api/schemes/${encodeURIComponent(schemeId)}`, { params });
  return response.data.scheme;
}

/**
 * Fetch application locations from GET /api/locations.
 * @param {object} [filters] - Optional { schemeId, state, district, taluka }
 * @returns {Promise<object>} - { success, count, locations }
 */
export async function fetchLocations({ schemeId, state, district, taluka } = {}) {
  const params = {};
  if (schemeId) params.scheme_id = schemeId;
  if (state) params.state = state;
  if (district) params.district = district;
  if (taluka) params.taluka = taluka;
  const response = await apiClient.get('/api/locations', { params });
  return response.data;
}

/**
 * Verify backend health via /api/health.
 * @returns {Promise<object>} - Health status data
 */
export async function checkBackendHealth() {
  const response = await apiClient.get('/api/health');
  return response.data;
}

export default apiClient;
