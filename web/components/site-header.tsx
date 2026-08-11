"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { NAV, REPO_URL } from "@/lib/site-content";

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);
  const [condensed, setCondensed] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Collapse the bar once the hero is behind us.
  useEffect(() => {
    const onScroll = () => setCondensed(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Any route change closes whatever was open.
  useEffect(() => {
    setOpen(null);
    setMenu(false);
  }, [pathname]);

  useEffect(() => {
    if (!menu && !open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(null);
      setMenu(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menu, open]);

  useEffect(() => {
    document.body.style.overflow = menu ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menu]);

  // Small grace period so the pointer can cross the gap into the panel.
  const scheduleClose = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = setTimeout(() => setOpen(null), 130);
  };

  const cancelClose = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  };

  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <header className="nav" data-condensed={condensed || undefined} data-open={open ? "" : undefined}>
      <div className="shell nav-inner">
        <Link className="brand" href="/" aria-label="Aiur home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
          </span>
          AIUR
        </Link>

        <nav className="nav-menu" aria-label="Primary" onMouseLeave={scheduleClose}>
          {NAV.map((item) => (
            <div className="nav-item" key={item.label} onMouseEnter={() => { cancelClose(); setOpen(item.label); }}>
              <Link
                href={item.href}
                className={isActive(item.href) ? "active" : undefined}
                aria-current={isActive(item.href) ? "page" : undefined}
                aria-expanded={open === item.label}
                onFocus={() => setOpen(item.label)}
              >
                {item.label}
              </Link>

              <div className="nav-panel" hidden={open !== item.label} onMouseEnter={cancelClose}>
                <div className="shell nav-panel-inner">
                  <div className="nav-panel-lead">
                    <span>{item.label}</span>
                    <p>{item.blurb}</p>
                    <Link href={item.href} className="nav-panel-all">
                      Overview <span aria-hidden="true">→</span>
                    </Link>
                  </div>
                  <div className="nav-panel-links">
                    {item.links.map(([label, href, copy]) =>
                      href.startsWith("http") ? (
                        <a key={label} href={href} target="_blank" rel="noreferrer">
                          <strong>{label}</strong>
                          <span>{copy}</span>
                        </a>
                      ) : (
                        <Link key={label} href={href}>
                          <strong>{label}</strong>
                          <span>{copy}</span>
                        </Link>
                      ),
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </nav>

        <div className="nav-end">
          <span className="nav-status" aria-label="Programme status">
            <span className="status-dot" />
            P0-A / ACTIVE
          </span>
          <a className="nav-cta" href={REPO_URL} target="_blank" rel="noreferrer">
            Engineering log <span aria-hidden="true">↗</span>
          </a>
          <button
            type="button"
            className="nav-toggle"
            aria-expanded={menu}
            aria-controls="mobile-menu"
            onClick={() => setMenu((value) => !value)}
          >
            <span className="nav-toggle-bars" aria-hidden="true">
              <i />
              <i />
            </span>
            {menu ? "Close" : "Menu"}
          </button>
        </div>
      </div>

      <div className="nav-drawer" id="mobile-menu" hidden={!menu}>
        <div className="shell">
          {NAV.map((item) => (
            <div className="nav-drawer-group" key={item.label}>
              <Link href={item.href} className={isActive(item.href) ? "active" : undefined}>
                {item.label}
              </Link>
              <p>{item.blurb}</p>
            </div>
          ))}
          <a className="button" href={REPO_URL} target="_blank" rel="noreferrer">
            Engineering repository <span aria-hidden="true">↗</span>
          </a>
        </div>
      </div>
    </header>
  );
}
