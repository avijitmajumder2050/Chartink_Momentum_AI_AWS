import { Routes, Route } from "react-router-dom";
import AppShell from "./components/AppShell";
import Home from "./pages/Home";
import Capabilities from "./pages/Capabilities";
import Scanner from "./pages/Scanner";
import Callback from "./auth/Callback";

export default function App() {
  return (
    <Routes>
      {/* Outside AppShell — Cognito's redirect lands here directly, no
          header/footer needed while the code exchange is in flight. */}
      <Route path="/auth/callback" element={<Callback />} />

      <Route element={<AppShell />}>
        <Route path="/" element={<Home />} />
        <Route path="/capabilities" element={<Capabilities />} />
        <Route path="/scanner" element={<Scanner />} />
        {/* Every other route from the original app (News, Markets/*,
            Education, Pricing, Dashboard, Admin/*, ...) gets added here
            page-by-page in later phases of the rewrite plan. */}
      </Route>
    </Routes>
  );
}
