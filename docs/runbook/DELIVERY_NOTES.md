# Runbook Delivery Notes

## What Was Built

A **government-grade dark ops** operations runbook for the NCDIT WCAG Document Converter, designed as a single self-contained HTML file for StaticCrypt encryption.

**File:** `docs/runbook/index.html` (46KB, 1,519 lines)

---

## Design Execution

### Aesthetic: "Government-Grade Dark Ops"

**NOT generic dark mode.** This is a classified briefing meets premium developer docs.

**Typography:**
- Headings: **Outfit** (geometric, modern, authoritative) — 700-800 weight
- Body: **Literata** (editorial serif, readable) — optical sizing enabled
- Code: **JetBrains Mono** (distinctive monospace)
- All fonts loaded from Google Fonts CDN

**Color Palette:**
- Deep navy near-black background (`#0a1628`)
- Layered card surfaces (`#0f2340`, `#162d50`)
- Soft white primary text (`#e2e8f0`) — 14.71:1 contrast ratio ✅
- Muted secondary text (`#94a3b8`) — 7.07:1 contrast ratio ✅
- Sky blue accent (`#38bdf8`) — 8.46:1 contrast ratio ✅
- Gradient section labels (sky → emerald, amber → red)
- NCDIT brand navy (`#003366`) used sparingly

**Layout & Micro-interactions:**
- Single-column, 780px max-width (Anvil-inspired editorial flow)
- Sticky header with smooth scroll navigation
- Scroll-reveal animations via IntersectionObserver
- Terminal boxes with **copy-to-clipboard** functionality (green check animation)
- Hover states on architecture diagram nodes (glow effects)
- Gradient text on section labels
- Responsive design (mobile-friendly)
- Print-optimized styles (black & white compatible)

---

## Content Sections (10 Total)

1. **Hero/Header** — Title, subtitle, version badge, date, classification
2. **System Architecture** — Visual HTML/CSS diagram + component table
3. **Deployment Guide** — Azure CLI commands for backend + frontend
4. **Configuration Reference** — Environment variables table
5. **API Endpoints** — HTTP endpoints + auth requirements
6. **Operations & Monitoring** — Health checks, metrics, log streaming
7. **Troubleshooting** — Symptom/cause/resolution table + debug commands
8. **Incident Response** — P1/P2/P3 severity levels + escalation contacts
9. **Security & Compliance** — WCAG compliance, key rotation, data residency
10. **Performance Targets** — SLOs for conversion speed + output quality

**Plus:** Maintenance section (dependency updates, eval suite, backup)

---

## Technical Highlights

### Architecture Diagram
Built with pure HTML/CSS (no images):
- 11 interactive nodes with hover effects
- Arrows and flow indicators
- Responsive (stacks vertically on mobile)
- Print-friendly

### Terminal Boxes
7 command-line examples with:
- Syntax highlighting (green prompts, gray comments)
- Copy button (strips prompts/comments for clean paste)
- Dark terminal aesthetic (#000 background)

### Callout Boxes
18 contextual alerts:
- ⚠️ Warning (amber)
- ℹ️ Info (sky blue)
- 🔴 Critical (red)
- ✅ Success (emerald)

### Tables
5 data tables:
- Component details
- Environment variables
- API endpoints
- Troubleshooting matrix
- Performance targets

---

## Accessibility (WCAG 2.1 AA Compliant)

✅ **Semantic HTML:** Proper heading hierarchy, landmarks  
✅ **ARIA:** `role="banner"`, `role="main"`, `role="navigation"`, `role="img"` with labels  
✅ **Keyboard Navigation:** Skip link, focus-visible outlines, smooth scroll  
✅ **Color Contrast:** All text exceeds 7:1 (AA requires 4.5:1)  
✅ **Responsive:** Works on desktop, tablet, mobile  
✅ **Print Styles:** Black & white compatible, page-break controls  

---

## StaticCrypt Ready

The HTML is **completely self-contained** except for Google Fonts CDN:
- All CSS inline in `<style>` tag
- All JavaScript inline in `<script>` tag
- No external images or assets
- Ready for AES-256 encryption

**See:** `ENCRYPTION.md` for StaticCrypt deployment guide

---

## File Size

- **Uncompressed:** 46KB
- **Gzipped:** ~8KB (estimated)
- **Lines of code:** 1,519

Single HTTP request (plus 3 for Google Fonts) — no build step, no dependencies.

---

## What Makes This Special

1. **NOT generic dark mode** — deep navy "classified briefing" aesthetic, not purple-on-black or blue-on-black clichés
2. **Editorial typography** — Outfit + Literata feels authoritative and modern, not corporate-boring
3. **Interactive architecture diagram** — built with CSS, not a static image
4. **Copy-to-clipboard terminals** — smart copy (strips prompts and comments)
5. **Scroll-reveal animations** — subtle, elegant, not distracting
6. **Gradient section labels** — Anvil-inspired, but inverted for dark theme
7. **Government trust** — NCDIT branding, security callouts, compliance focus
8. **Accessible by default** — 14.71:1 contrast, semantic HTML, keyboard nav

---

## Deployment Checklist

- [ ] Review content accuracy (Azure resource names, endpoints, etc.)
- [ ] Update version badge and date in hero section
- [ ] Test in browsers: Chrome, Firefox, Safari, Edge
- [ ] Test on mobile devices
- [ ] Verify print styles (Cmd/Ctrl+P)
- [ ] Encrypt with StaticCrypt (see `ENCRYPTION.md`)
- [ ] Deploy encrypted file to Azure Static Web Apps or Blob Storage
- [ ] Share password with on-call engineers via secure channel
- [ ] Test password unlock flow

---

**Built by Flash (Frontend Developer) for NCDIT**  
**March 2026**
