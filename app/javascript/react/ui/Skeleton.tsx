interface SkeletonProps {
  // Size/shape classes (width, height, rounding); the primitive owns only the shimmer.
  className?: string
}

// Shimmer placeholder primitive. Per-resource skeletons compose this so every
// loading state across the app shares one animation, color, and radius.
export function Skeleton({ className = "" }: SkeletonProps) {
  return <div className={`animate-pulse rounded bg-base-300 ${className}`} />
}
