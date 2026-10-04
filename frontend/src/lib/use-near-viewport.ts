"use client";

import { useEffect, useRef, useState } from "react";

export function useNearViewport<T extends Element>(rootMargin = "200px") {
  const ref = useRef<T>(null);
  const [near, setNear] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    if (typeof IntersectionObserver === "undefined") {
      let active = true;
      queueMicrotask(() => { if (active) setNear(true); });
      return () => { active = false; };
    }
    const observer = new IntersectionObserver(
      entries => setNear(entries[0]?.isIntersecting ?? false),
      { rootMargin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [rootMargin]);

  return { ref, near };
}
