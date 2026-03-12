'use client';

import ThemeToggle from '@/components/ThemeToggle';

/**
 * NCHeader — Sticky frosted-glass header with NC.gov branding.
 *
 * Redesigned to match the operations runbook aesthetic:
 * - Sticky top with backdrop-filter blur
 * - Gradient underline accent (sky → emerald → amber)
 * - Outfit font for all text
 * - ThemeToggle integrated on the right
 *
 * Accessibility:
 * - role="banner" on <header>
 * - Semantic navigation with aria-label
 * - Keyboard-navigable links and theme toggle
 * - Responsive layout
 */
export default function NCHeader() {
  return (
    <header role="banner" className="nc-header">
      <div className="header-container">
        <div className="header-inner">
          {/* Logo + Branding */}
          <div className="header-brand">
            <a
              href="https://www.nc.gov"
              className="header-logo"
              aria-label="NC.gov - State of North Carolina"
            >
              <span className="header-logo__mark" aria-hidden="true">NC</span>
              <span className="header-logo__dot">.gov</span>
            </a>

            <span className="header-divider" aria-hidden="true" />

            <div className="header-service">
              <span className="header-service__dept">NCDIT</span>
              <span className="header-service__name">Document Converter</span>
            </div>
          </div>

          {/* Navigation + Theme Toggle */}
          <div className="header-actions">
            <nav aria-label="Service navigation" className="header-nav">
              <a href="/" className="header-nav__link">Upload</a>
              <a href="/dashboard" className="header-nav__link">Dashboard</a>
            </nav>
            <ThemeToggle />
          </div>
        </div>
      </div>

      <style jsx>{`
        .header-container {
          width: 100%;
          padding-left: var(--space-lg, 1.5rem);
          padding-right: var(--space-lg, 1.5rem);
        }

        .header-inner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.75rem 0;
          gap: 1rem;
        }

        .header-brand {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          min-width: 0;
        }

        .header-logo {
          display: flex;
          align-items: center;
          text-decoration: none;
          flex-shrink: 0;
        }

        .header-logo__mark {
          font-family: var(--font-heading);
          font-size: 1.5rem;
          font-weight: 800;
          color: var(--text-primary);
          line-height: 1;
        }

        .header-logo__dot {
          font-family: var(--font-heading);
          font-size: 1.5rem;
          font-weight: 400;
          color: var(--accent-sky);
          line-height: 1;
        }

        .header-divider {
          width: 1px;
          height: 1.75rem;
          background: var(--border);
          flex-shrink: 0;
        }

        .header-service {
          min-width: 0;
        }

        .header-service__dept {
          display: block;
          font-family: var(--font-heading);
          font-size: 0.7rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          color: var(--text-muted);
          line-height: 1.2;
        }

        .header-service__name {
          display: block;
          font-family: var(--font-heading);
          font-size: 1rem;
          font-weight: 600;
          color: var(--text-primary);
          line-height: 1.3;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          flex-shrink: 0;
        }

        .header-nav {
          display: flex;
          gap: 0.25rem;
        }

        .header-nav__link {
          font-family: var(--font-heading);
          font-size: 0.875rem;
          font-weight: 600;
          color: var(--text-secondary);
          text-decoration: none;
          padding: 0.4rem 0.75rem;
          border-radius: var(--radius-md);
          transition: all var(--transition-fast);
        }

        .header-nav__link:hover {
          color: var(--accent-sky);
          background: var(--surface);
        }

        @media (max-width: 575.98px) {
          .header-container {
            padding-left: var(--space-md, 1rem);
            padding-right: var(--space-md, 1rem);
          }

          .header-logo__mark,
          .header-logo__dot {
            font-size: 1.2rem;
          }

          .header-service__name {
            font-size: 0.875rem;
          }

          .header-nav__link {
            font-size: 0.8125rem;
            padding: 0.3rem 0.5rem;
          }
        }
      `}</style>
    </header>
  );
}
