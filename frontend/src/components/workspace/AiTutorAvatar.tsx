'use client';

import React from 'react';

interface AiTutorAvatarProps {
  /** Diameter of the circular avatar in pixels. */
  size?: number;
  /** Mascot image to show. Defaults to the SQL tutor's cougar. */
  src?: string;
  /** Accessible name for the tutor this avatar represents. */
  alt?: string;
}

/** Circular mascot avatar for an AI tutor — cougar for SQL, bear for Baloo. */
export function AiTutorAvatar({
  size = 18,
  src = '/cougar.png',
  alt = 'AI Tutor',
}: AiTutorAvatarProps) {
  return (
    <img
      src={src}
      alt={alt}
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

/** Baloo, the ER-diagram tutor. Thin wrapper so call sites don't repeat the asset path.
 *
 * Decorative by design: every use sits directly beside the visible name "Baloo",
 * so alt text here would make the accessible name read "Baloo Baloo". Pass an
 * explicit `alt` if it ever appears without an accompanying label. */
export function BalooAvatar({ size = 18, alt = '' }: { size?: number; alt?: string }) {
  return <AiTutorAvatar size={size} src="/bear.png" alt={alt} />;
}
