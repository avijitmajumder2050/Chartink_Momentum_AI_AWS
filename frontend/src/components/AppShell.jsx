import { Outlet } from "react-router-dom";
import Header from "./Header";
import Footer from "./Footer";

// Replaces templates/base.html + _header.html + _footer.html. The push
// opt-in banner (_push_banner.html) isn't ported yet — that's Phase 5
// (service worker + push notifications) in the rewrite plan.
export default function AppShell() {
  return (
    <>
      <Header />
      <main>
        <Outlet />
      </main>
      <Footer />
    </>
  );
}
