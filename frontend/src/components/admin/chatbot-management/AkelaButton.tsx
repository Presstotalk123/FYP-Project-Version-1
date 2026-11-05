import type { ButtonHTMLAttributes, ReactNode } from 'react';

interface AkelaButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  loading?: boolean;
  leftSection?: ReactNode;
  variant?: 'default' | 'light' | 'subtle' | 'filled';
  size?: 'xs';
}

/** Use the same shared button classes as Akela's Problems page. */
export function AkelaButton({
  loading = false, leftSection, variant = 'filled', size,
  children, disabled, className = '', style, type = 'button', ...props
}: AkelaButtonProps) {
  const appearance = variant === 'default' || variant === 'light'
    ? 'btn-secondary' : variant === 'subtle' ? 'btn-ghost' : 'btn-brand';
  return (
    <button
      {...props}
      type={type}
      className={`btn ${appearance} ${className}`}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      style={{
        ...(size === 'xs' ? { minHeight: 32, padding: '0 12px', fontSize: 13 } : {}),
        ...(disabled || loading ? { opacity: 0.55, cursor: 'not-allowed' } : {}),
        ...style,
      }}
    >
      {loading ? <span className="spinner" style={{ width: 15, height: 15, borderWidth: 2 }} aria-hidden="true" /> : leftSection}
      {children}
    </button>
  );
}
