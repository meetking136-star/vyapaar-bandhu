"use client";

import { useEffect, useRef, useState } from "react";

interface AnimatedCounterProps {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  formatter?: (n: number) => string;
  className?: string;
}

export default function AnimatedCounter({
  value,
  duration = 1000,
  prefix = "",
  suffix = "",
  formatter,
  className = "",
}: AnimatedCounterProps) {
  const [display, setDisplay] = useState(0);
  const startRef = useRef<number>(0);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    const start = startRef.current;
    const startTime = performance.now();

    function animate(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = start + (value - start) * eased;
      setDisplay(current);

      if (progress < 1) {
        frameRef.current = requestAnimationFrame(animate);
      } else {
        startRef.current = value;
      }
    }

    frameRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frameRef.current);
  }, [value, duration]);

  const formatted = formatter
    ? formatter(display)
    : Math.round(display).toLocaleString("en-IN");

  return (
    <span className={`font-mono ${className}`}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
