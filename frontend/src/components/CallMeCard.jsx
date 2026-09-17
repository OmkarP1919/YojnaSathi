import React, { useState } from 'react';
import { requestSchemeCall } from '../api';

/**
 * Minimal outbound-call card for the YojnaSathi MVP.
 * Posts only to our own backend (POST /api/calle/call);
 * the browser never talks to CALL-E directly.
 */
function CallMeCard({ lang }) {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const handleCall = async () => {
    setStatus(null);
    setError(null);
    setBusy(true);
    try {
      const result = await requestSchemeCall(phoneNumber.trim(), lang || 'en');
      setStatus(result);
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not start the call. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="call-me-card" aria-label="Talk to YojnaSathi" style={{ marginTop: '1.5rem' }}>
      <h3>Talk to YojnaSathi</h3>
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
        <label htmlFor="call-me-phone">+91</label>
        <input
          id="call-me-phone"
          type="tel"
          placeholder="XXXXXXXXXX"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
          disabled={busy}
        />
        <button type="button" className="btn-step-continue" onClick={handleCall} disabled={busy}>
          {busy ? 'Calling…' : 'Call Me'}
        </button>
      </div>
      {status && (
        <p role="status">
          Call requested. ID: {status.call_id} ({status.status})
        </p>
      )}
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}

export default CallMeCard;
