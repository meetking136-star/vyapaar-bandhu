"use client";

interface ReadinessRingProps {
  percentage: number;
  size?: number;
  strokeWidth?: number;
}

export default function ReadinessRing({
  percentage,
  size = 48,
  strokeWidth = 4,
}: ReadinessRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (percentage / 100) * circumference;

  const color =
    percentage >= 80
      ? "#22C55E"
      : percentage >= 50
        ? "#EAB308"
        : "#EF4444";

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={size} height={size} className="-rotate-90">
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.05)"
          strokeWidth={strokeWidth}
        />
        {/* Progress ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <span
        className="absolute text-xs font-mono font-medium"
        style={{ color }}
      >
        {Math.round(percentage)}
      </span>
    </div>
  );
}
