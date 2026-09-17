import React from 'react';

/**
 * Friendly YojnaSathi robot head rendered as a lightweight inline SVG.
 *
 * State-driven face:
 * - idle:      open eyes + smile
 * - listening: open eyes + gentle smile + mic dot (rings live in the parent)
 * - processing: "thinking" eyes + small animated dots beside the head
 * - speaking:  open eyes + animated open mouth
 * - when no state is given the face is idle.
 *
 * The SVG intentionally has no external asset/dependency requirements.
 */
export function RobotAvatar({ size = 48, state = 'idle', className = '', ariaHidden = true }) {
  const thinking = state === 'processing';
  const speaking = state === 'speaking';
  const listening = state === 'listening';

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      className={`robot-avatar${className ? ` ${className}` : ''}`}
      role="img"
      aria-hidden={ariaHidden}
    >
      {/* Antenna */}
      <line x1="32" y1="10" x2="32" y2="4" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      <circle cx="32" cy="2.5" r="2.5" fill="currentColor" />

      {/* Head */}
      <rect x="12" y="12" width="40" height="40" rx="12" fill="#ffffff" stroke="currentColor" strokeWidth="2.5" />

      {/* Ears / side panels */}
      <rect x="7" y="24" width="6" height="12" rx="3" fill="#ffffff" stroke="currentColor" strokeWidth="2" />
      <rect x="51" y="24" width="6" height="12" rx="3" fill="#ffffff" stroke="currentColor" strokeWidth="2" />

      {/* Eyes */}
      <g className="robot-eye robot-eye-open" style={{ opacity: thinking || listening ? 0 : 1 }}>
        <circle cx="24" cy="27" r="3.6" fill="currentColor" />
        <circle cx="40" cy="27" r="3.6" fill="currentColor" />
      </g>
      {/* Thinking eyes (half-lidded) */}
      <g className="robot-eye robot-eye-thinking" style={{ opacity: thinking ? 1 : 0 }}>
        <line x1="20.5" y1="27" x2="27.5" y2="27" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
        <line x1="36.5" y1="27" x2="43.5" y2="27" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" />
      </g>

      {/* Face lower half */}
      <g style={{ opacity: listening ? 0 : 1 }}>
        {/* Speaking: animated open mouth */}
        <rect
          className="robot-mouth robot-mouth-speaking"
          x="29"
          y="38"
          width="6"
          height="8"
          rx="3"
          fill="currentColor"
          style={{ opacity: speaking ? 1 : 0, transform: speaking ? '' : 'scaleY(0.2)' }}
        />
        {/* Idle / processing: friendly smile */}
        <path
          className="robot-mouth robot-mouth-smile"
          d="M26 40 Q32 46 38 40"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.4"
          strokeLinecap="round"
          style={{ opacity: speaking ? 0 : 1 }}
        />
      </g>

      {/* Listening: microphone dot replaces the mouth centre */}
      <g className="robot-mouth robot-mouth-listening" style={{ opacity: listening ? 1 : 0 }}>
        <circle cx="32" cy="40" r="3" fill="currentColor" />
        <rect x="30.6" y="34" width="2.8" height="5" rx="1.4" fill="currentColor" />
      </g>

      {/* Cheeks */}
      <circle cx="20" cy="36" r="2.4" fill="currentColor" opacity="0.18" />
      <circle cx="44" cy="36" r="2.4" fill="currentColor" opacity="0.18" />
    </svg>
  );
}

export default RobotAvatar;