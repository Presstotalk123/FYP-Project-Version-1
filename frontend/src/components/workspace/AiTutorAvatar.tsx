'use client';

import React from 'react';

interface AiTutorAvatarProps {
  /** Diameter of the circular avatar in pixels. */
  size?: number;
}

/** Circular cougar mascot avatar for the AI Tutor. */
export function AiTutorAvatar({ size = 18 }: AiTutorAvatarProps) {
  return (
    <img
      src="/cougar.png"
      alt="AI Tutor"
      width={size}
      height={size}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        objectFit: 'cover',
        border: '1px solid var(--border)',
        flexShrink: 0,
        display: 'block',
      }}
    />
  );
}
