export default function Select({ label, error, children, className = '', ...props }) {
  return (
    <div className="flex flex-col gap-1.5">
      {label && (
        <label className="text-sm font-medium text-gray-700">{label}</label>
      )}
      <select
        className={`w-full px-4 py-2.5 rounded-xl border bg-white text-gray-900
          text-sm transition focus:outline-none focus:ring-2 focus:ring-brand-blue-500
          ${error ? 'border-red-400 focus:ring-red-400' : 'border-gray-200 focus:border-brand-blue-400'}
          ${className}`}
        {...props}
      >
        {children}
      </select>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}
