export default function Button({
  children, variant = 'primary', size = 'md',
  className = '', loading = false, ...props
}) {
  const base = 'inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-offset-2'

  const variants = {
    primary:   'bg-brand-blue-600 text-white hover:bg-brand-blue-700 focus:ring-brand-blue-500 shadow-sm',
    secondary: 'bg-brand-green-600 text-white hover:bg-brand-green-700 focus:ring-brand-green-500 shadow-sm',
    outline:   'border-2 border-brand-blue-600 text-brand-blue-600 hover:bg-brand-blue-50 focus:ring-brand-blue-500',
    ghost:     'text-brand-blue-600 hover:bg-brand-blue-50 focus:ring-brand-blue-500',
    danger:    'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 shadow-sm',
    light:     'bg-white text-brand-blue-700 hover:bg-brand-blue-50 border border-brand-blue-200 shadow-sm',
  }

  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-5 py-2.5 text-sm',
    lg: 'px-7 py-3.5 text-base',
    xl: 'px-8 py-4 text-lg',
  }

  return (
    <button
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={loading || props.disabled}
      {...props}
    >
      {loading && (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
        </svg>
      )}
      {children}
    </button>
  )
}
