import { Outlet } from "react-router-dom";
import Header from "./Header";
import Footer from "./Footer";
import PushBanner from "./PushBanner";

// Replaces templates/base.html + _header.html + _footer.html + the push
// opt-in banner (_push_banner.html).
export default function AppShell() {
  return (
    <>
      <Header />
      <main>
        <Outlet />
      </main>
      <Footer />
      <PushBanner />
    </>
  );
}
