"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { homeHeaderOwner } from "@/components/nav/home-header-owner";
import { useEffect, useRef, useState } from "react";

export function HeaderNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, loading, isAuthenticated, isStaff, isAdmin } = useAuth();
  
  const [pillStyle, setPillStyle] = useState({ width: 0, left: 0, opacity: 0 });
  const segmentedRef = useRef<HTMLDivElement>(null);

  const isStaffMember = isStaff || isAdmin;

  const staffLinks = [
    { label: "Dashboard", href: "/admin", exact: true },
    { label: "Problems", href: "/admin/problems" },
    { label: "Labs", href: "/admin/labs" },
    { label: "Assessments", href: "/admin/assessments" },
    // Per-student platform-time usage. Staff + admin (both can view).
    { label: "Usage", href: "/admin/usage" },
    // Staff + admin (deliberately outside the isAdmin gate below): the
    // /admin/settings prompt editor is editable by both roles.
    { label: "Settings", href: "/admin/settings" },
  ];

  if (isAdmin) {
    staffLinks.push({ label: "Users", href: "/admin/users" });
  }

  const studentLinks = [
    { label: "Course Info", href: "/student/course" },
    { label: "Questions", href: "/student", exact: true },
    { label: "SQL Labs", href: "/student/labs" },
    { label: "Assessments", href: "/student/assessments" },
  ];
  
  const unauthLinks = [
    { label: "Home", href: "/", exact: true },
    { label: "SQL", href: "/login" },
    { label: "ER Diagram", href: "/login" },
  ];

  const currentLinks = isStaffMember 
    ? staffLinks 
    : isAuthenticated 
      ? studentLinks 
      : unauthLinks;

  useEffect(() => {
    if (segmentedRef.current) {
      // Find the active link inside the segmented control
      const activeEl = segmentedRef.current.querySelector('.active-seg') as HTMLElement;
      if (activeEl) {
        setPillStyle({
          width: activeEl.offsetWidth,
          left: activeEl.offsetLeft,
          opacity: 1
        });
      } else {
        setPillStyle(prev => ({ ...prev, opacity: 0 }));
      }
    }
  }, [pathname, isStaffMember, isAuthenticated]);

  // Hidden on the login page so nav buttons don't appear there.
  //
  // On the home page this header IS the logged-in header: a known user gets the
  // same brand / role nav / account controls they see everywhere else, and the
  // page's own marketing header stands down. A visitor gets the marketing one
  // instead, so this returns null for them. See home-header-owner.
  if (pathname === "/login") return null;
  if (pathname === "/" && homeHeaderOwner(loading, isAuthenticated) !== "app") {
    return null;
  }

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="topbar">
      <Link href="/" className="brand">
        <span className="brand-mark" aria-hidden="true" />
        <span>Akela</span>
      </Link>

      <nav className="app-nav" aria-label="Main navigation">
        <div className="segmented-control" ref={segmentedRef}>
          <div className="segmented-pill" style={{ 
            width: `${pillStyle.width}px`, 
            transform: `translateX(${pillStyle.left}px)`,
            opacity: pillStyle.opacity
          }} />
          {currentLinks.map((link) => {
            const isActive = link.exact
              ? pathname === link.href
              : pathname === link.href || pathname.startsWith(link.href + "/");
            return (
              <Link
                key={link.label}
                href={link.href}
                className={`seg-item ${isActive ? "active-seg" : ""}`}
                aria-current={isActive ? "page" : undefined}
              >
                {link.label}
              </Link>
            );
          })}
        </div>
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
