import React from 'react'

function Skeleton({ width, height, variant = 'text', style, className = '' }) {
  const variantClass = `skeleton--${variant}`
  return (
    <div
      className={`skeleton ${variantClass} ${className}`}
      style={{ width, height, ...style }}
    />
  )
}

function SkeletonCard() {
  return (
    <div className="stat-card" style={{ pointerEvents: 'none' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <Skeleton variant="rect" width={40} height={40} />
        <div>
          <Skeleton variant="text" width={60} height={24} />
          <Skeleton variant="text" width={100} height={14} style={{ marginTop: 6 }} />
        </div>
      </div>
    </div>
  )
}

function SkeletonTable({ rows = 4, cols = 5 }) {
  return (
    <div className="skeleton-table">
      <div className="skeleton-table-header">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} variant="text" width="80%" height={16} />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="skeleton-table-row">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} variant="text" width="70%" height={14} />
          ))}
        </div>
      ))}
    </div>
  )
}

export { Skeleton, SkeletonCard, SkeletonTable }
