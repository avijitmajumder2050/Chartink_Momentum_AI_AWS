import { useEffect, useState } from "react";

// Pages here build their layout with inline style objects, not CSS
// classes — a stylesheet media query can't reach those, so the few
// places that genuinely need to restructure (a sidebar moving below
// the content, a fixed-width side panel becoming full-width) check
// this instead. Simple spacing/padding tweaks use CSS clamp() in the
// inline style directly and don't need this at all.
export default function useIsMobile(breakpoint = 768) {
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.innerWidth <= breakpoint
  );

  useEffect(() => {
    function onResize() {
      setIsMobile(window.innerWidth <= breakpoint);
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [breakpoint]);

  return isMobile;
}
