/**
 * Frontend configuration for YojnaSathi.
 *
 * Phone / CALL-E gateway:
 * The "Call YojnaSathi" homepage card only becomes a real tel: link once a
 * CALL-E phone number has been configured. Set VITE_CALL_PHONE_NUMBER in
 * frontend/.env (see frontend/.env.example) to the E.164 international number
 * used by the CALL-E service (e.g. +919876543210). Do NOT hardcode a
 * production number in this file, and do NOT commit real numbers to git.
 */
const RAW_PHONE_NUMBER = (import.meta.env.VITE_CALL_PHONE_NUMBER || '').trim().replace(/[^0-9+]/g, '');

const VALID_E164_PATTERN = /^\+[0-9]{8,15}$/;

/** Configured CALL-E phone number in E.164 form, or '' when not configured. */
export const CALL_PHONE_NUMBER = VALID_E164_PATTERN.test(RAW_PHONE_NUMBER) ? RAW_PHONE_NUMBER : '';

/** Whether a valid phone number is configured (safe to render a tel: link). */
export const PHONE_GATEWAY_ENABLED = CALL_PHONE_NUMBER.length > 0;

/** tel: href for the configured phone number, or null when not configured. */
export const CALL_TEL_HREF = PHONE_GATEWAY_ENABLED ? `tel:${CALL_PHONE_NUMBER}` : null;