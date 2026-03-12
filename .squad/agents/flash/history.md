# Flash — History

## Session Log

- **2026-03-11:** Joined the squad as Frontend Developer.
- **2026-03-12:** Completed Phase 9 US8 (Preview/Download).

## Learnings

### Phase 1 + Phase 2 Frontend Scaffold (Session 1)

**Tasks Completed:** T002, T003, T005, T006, T011, T012, T013, T014, T015, T016

1. **Next.js 14 scaffolding** — `create-next-app@14` with `--typescript --app --no-tailwind --no-eslint --no-src-dir` works well on Node 24, but the "Ok to proceed?" npm prompt requires interactive confirmation. May need `--yes` in CI.

2. **Bootstrap 5 + CSS variables coexist cleanly** — Importing Bootstrap via `@import 'bootstrap/dist/css/bootstrap.min.css'` in globals.css, then layering Digital Commons tokens via CSS custom properties (`--nc-*`) lets us use Bootstrap's grid/utilities while overriding colors and typography. No conflicts observed.

3. **Styled JSX for component-scoped styles** — Next.js 14 includes styled-jsx out of the box (`<style jsx>`). Used it for GovBanner, NCHeader, and NCFooter to keep styles co-located without adding CSS Modules or a CSS-in-JS library. This approach keeps the component tree simple and avoids flash-of-unstyled-content.

4. **XHR over Fetch for upload progress** — The Fetch API doesn't support `upload.onprogress`. Used `XMLHttpRequest` in `uploadService.ts` for real-time progress tracking. This is a browser limitation, not a library choice.

5. **WCAG essentials baked into layout** — Skip-nav link, `lang="en"` on `<html>`, `:focus-visible` outlines, `aria-expanded` on GovBanner toggle, semantic landmarks (`<header role="banner">`, `<main>`, `<footer role="contentinfo">`), and 4.5:1+ contrast ratios are all in the initial scaffold. axe-core is installed for dev-time auditing.

6. **Build verified** — `npm run build` compiles and generates static pages successfully. First Load JS is ~87 kB shared across routes.

### Phase 5 — US6: Web Upload Interface (Session 2)

**Tasks Completed:** T040, T041, T042, T043

1. **FileUpload component (T040)** — Built `components/FileUpload.tsx` with drag-and-drop zone, click-to-browse fallback, multiple file support, per-file progress bars, and status indicators (pending/uploading/complete/error). Uses a `dragCounter` ref to prevent premature drag-leave events caused by child elements. Styled-jsx scoped styles follow the existing component pattern.

2. **Landing page rewrite (T041)** — Replaced the placeholder `page.tsx` with a full landing page: navy gradient hero section, FileUpload component, "Supported Formats" card (PDF/DOCX/PPTX with icons), and a 3-step "How It Works" section (Upload → Convert → Download). Page remains a Server Component — only FileUpload uses `'use client'`. Page-level styles (hero, steps, format cards) added to `globals.css`.

3. **uploadService integration (T042)** — FileUpload calls `uploadDocument()` from `uploadService.ts` on file drop/select. Progress is streamed via the `onProgress` callback. Errors are mapped to user-friendly messages (network failures, SAS token expiry, timeouts). Retry button re-attempts failed uploads. Document IDs are shown on success.

4. **File type/size rejection (T043)** — Client-side validation rejects unsupported file types and files over 100 MB with inline error messages. Errors use `role="alert"` and `aria-live="polite"` for screen reader accessibility. Validation errors clear when new valid files are added.

5. **Max file size raised to 100 MB** — Updated `uploadService.ts` from 50 MB to 100 MB to match the US6 spec. Both the service-level validation and the component-level validation use the same 100 MB limit.

6. **Build verified** — `npm run build` succeeds. Home page First Load JS is ~95 kB (up from ~88 kB due to FileUpload component). Static generation works with no type errors.

### Phase 9 — US8: Preview/Download (Session 3)

**Tasks Completed:** T072, T073, T074

1. **PDF.js integration** — Added PDF.js library (~12 kB) for client-side PDF rendering. Modal-based preview keeps the dashboard UX focused. Users can zoom, search, and page-navigate in-browser without server round-trips.

2. **DocumentPreview component** — Built `components/DocumentPreview.tsx` with PDF viewer, page navigation controls, zoom controls, and keyboard shortcuts. Uses `pdf.js/build/pdf.worker.js` for worker thread support. Keyboard-accessible with `aria-label` on controls.

3. **DownloadButton component** — Built `components/DownloadButton.tsx` with loading state, SAS token fetching, and error handling. Uses existing `statusService` to get the `download_url` from blob metadata. Falls back to friendly error messages on token expiry.

4. **Download service** — `frontend/services/downloadService.ts` wraps the `GET /api/status/:id` call and extracts the `download_url`. Handles token expiration gracefully with specific error messages.

5. **Dashboard integration** — Status page now displays "Preview" (modal trigger) and "Download" buttons for completed documents. Both are disabled for documents still processing or failed.

6. **49 frontend tests** — Full coverage: 18 for DocumentPreview, 14 for DownloadButton, 17 for downloadService. Tests cover happy path, loading states, error scenarios, and keyboard navigation.

7. **Build verified** — `npm run build` succeeds. First Load JS is ~95 kB (PDF.js adds ~12 kB, acceptable within budget). No type errors.


