export function CardSkeleton() {
  return (
    <div className="glass-card p-6 space-y-3">
      <div className="skeleton h-4 w-24" />
      <div className="skeleton h-8 w-32" />
      <div className="skeleton h-3 w-16" />
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="glass-card p-6 space-y-4">
      <div className="skeleton h-6 w-48 mb-4" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-4">
          <div className="skeleton h-4 w-32" />
          <div className="skeleton h-4 w-24" />
          <div className="skeleton h-4 w-20" />
          <div className="skeleton h-4 w-28" />
        </div>
      ))}
    </div>
  );
}
