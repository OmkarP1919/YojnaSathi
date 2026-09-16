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
 * Fetch full scheme details by ID from /api/schemes/{scheme_id}.
 * @param {string} schemeId - Scheme unique identifier
 * @returns {Promise<object>} - Scheme object
 */
export async function fetchSchemeDetails(schemeId) {
  const response = await apiClient.get(`/api/schemes/${encodeURIComponent(schemeId)}`);
  return response.data.scheme;
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
