import { NavLink, Outlet, Link } from "react-router";
import { Logo, cx } from "./ui";
import { ThemeToggle } from "./ThemeToggle";
import { t } from "../i18n/uk";

function NavItem({ to, children }: { to: string; children: string }) {
  return (
    <NavLink
      to={to}
      end={to === "/"}
      className={({ isActive }) =>
        cx(
          "rounded-lg px-2.5 py-1.5 text-sm transition-colors",
          isActive ? "bg-surface-2 text-text" : "text-muted hover:text-text",
        )
      }
    >
      {children}
    </NavLink>
  );
}

export default function Layout() {
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b border-border bg-bg/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between gap-3 px-4">
          <Link to="/" className="shrink-0">
            <Logo className="text-[20px]" />
          </Link>
          <nav className="flex items-center gap-1">
            <NavItem to="/">{t.nav.topics}</NavItem>
            <NavItem to="/settings">{t.nav.settings}</NavItem>
            <ThemeToggle />
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 pt-8 pb-20 sm:pt-10">
        <Outlet />
      </main>
    </div>
  );
}
