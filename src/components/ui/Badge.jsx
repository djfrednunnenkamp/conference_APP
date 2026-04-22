export default function Badge({ children, variant = 'blue', className = '' }) {
  const variants = {
    blue:   'bg-brand-blue-100 text-brand-blue-700',
    green:  'bg-brand-green-100 text-brand-green-700',
    gray:   'bg-gray-100 text-gray-600',
    red:    'bg-red-100 text-red-600',
    yellow: 'bg-yellow-100 text-yellow-700',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${variants[variant]} ${className}`}>
      {children}
    </span>
  )
}
