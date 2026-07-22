"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

export function HeaderNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, isAuthenticated, isStaff } = useAuth();

  // Hide global header on the home page — the home page renders its own header
  if (pathname === "/") return null;

  // Dynamic SQL link based on user role
  const sqlLink = isAuthenticated
    ? isStaff
      ? "/admin/questions"
      : "/student"
    : "/login";

  const links = [
    { label: "Home", href: "/" },
    { label: "SQL", href: sqlLink },
    { label: "ER Diagram", href: "/er-diagram" },
  ];

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="topbar">
      <Link href="/" className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <span>Database Assist</span>
      </Link>

      <nav className="app-nav" aria-label="Main navigation">
        {links.map((link) => {
          const isActive =
            link.href === "/"
              ? pathname === "/"
              : pathname === link.href || pathname.startsWith(link.href + "/");
          return (
            <Link
              key={link.href}
              href={link.href}
              className={isActive ? "active-link" : undefined}
              aria-current={isActive ? "page" : undefined}
            >
              {link.label}
            </Link>
          );
        })}
      </nav>

      <div className="user-tools">
        {isAuthenticated ? (
          <>
            <span>{user?.email}</span>
            <button
              className="btn btn-ghost"
              onClick={handleLogout}
              style={{ minHeight: 36, padding: "0 12px", fontSize: 13 }}
            >
              Logout
            </button>
          </>
        ) : (
          <Link href="/login" className="active-link" style={{ fontWeight: 600 }}>
            Login
          </Link>
        )}
      </div>
    </header>
  );
}
