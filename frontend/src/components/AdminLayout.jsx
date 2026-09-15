import { Outlet } from "react-router-dom";
import AdminSidebar from "./AdminSidebar";
import useIsMobile from "../hooks/useIsMobile";

// Every admin page's `<div style="display:flex">{sidebar}{content}</div>`
// wrapper, factored out once instead of repeated per page. A 232px
// fixed sidebar next to content works fine down to tablet width, but
// on a phone it leaves almost nothing for the page itself — stack
// instead (AdminSidebar collapses to a horizontal scrollable bar in
// that mode, see its own useIsMobile check).
export default function AdminLayout() {
  const isMobile = useIsMobile();
  return (
    <div style={{ width: "100%", display: "flex", flexDirection: isMobile ? "column" : "row" }}>
      <AdminSidebar />
      <div style={{ flex: 1, minWidth: 0 }}>
        <Outlet />
      </div>
    </div>
  );
}
