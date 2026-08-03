'use client';

import React from 'react';

interface IconBearProps {
  /** Rendered width/height in pixels. Matches @tabler/icons-react's `size`. */
  size?: number;
  /** Stroke width on the 24x24 grid. Matches @tabler/icons-react's `stroke`. */
  stroke?: number;
  color?: string;
  className?: string;
}

/**
 * Bear head for Baloo, the ER-diagram tutor.
 *
 * Tabler has no bear (only IconPaw), so this is hand-drawn to their outline
 * conventions — 24x24 grid, fill none, currentColor stroke, round caps and
 * joins — so it sits beside IconFolder / IconNotebook without looking foreign.
 * Dots use Tabler's `h.01` idiom, which a round linecap renders as a point.
 */
export function IconBear({ size = 24, stroke = 2, color = 'currentColor', className }: IconBearProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {/* ears */}
      <path d="M9.5 6.2a2.6 2.6 0 1 0 -3.1 3.4" />
      <path d="M14.5 6.2a2.6 2.6 0 1 1 3.1 3.4" />
      {/* head */}
      <path d="M12 20.5a7 7 0 1 1 0 -14a7 7 0 0 1 0 14z" />
      {/* muzzle */}
      <path d="M12 18.6a2.7 2.7 0 1 1 0 -5.4a2.7 2.7 0 0 1 0 5.4z" />
      {/* nose */}
      <path d="M12 15h.01" />
      {/* eyes */}
      <path d="M9.3 11.6h.01" />
      <path d="M14.7 11.6h.01" />
    </svg>
  );
}
