import { createContext, useCallback, useContext, useState } from "react";
import ChartPreviewModal from "./ChartPreviewModal";

// Single implementation replacing both static/js/chart-preview.js and the
// byte-for-byte duplicated copy that used to live inside static/js/
// scanner.js (see the rewrite plan's note on that duplication) — any page
// wrapped in this provider gets "click a symbol, see its chart" via
// useChartPreview().openPreview(symbol), same as the old window.
// openChartPreview(symbol) global did.
const ChartPreviewContext = createContext(null);

export function ChartPreviewProvider({ children }) {
  const [symbol, setSymbol] = useState(null); // null = closed

  const openPreview = useCallback((sym) => setSymbol(sym), []);
  const closePreview = useCallback(() => setSymbol(null), []);

  return (
    <ChartPreviewContext.Provider value={{ openPreview }}>
      {children}
      {symbol && <ChartPreviewModal symbol={symbol} onClose={closePreview} />}
    </ChartPreviewContext.Provider>
  );
}

export function useChartPreview() {
  const ctx = useContext(ChartPreviewContext);
  if (!ctx) throw new Error("useChartPreview must be used within a ChartPreviewProvider");
  return ctx;
}
