'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import ProgressTracker from '@/components/ProgressTracker';
import DocumentPreview from '@/components/DocumentPreview';
import ConfirmDialog from '@/components/ConfirmDialog';
import {
  startPolling,
  type StatusResponse,
  type StatusSummary,
  type DocumentStatus,
} from '@/services/statusService';
import { deleteDocument, deleteAllDocuments } from '@/services/deleteService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TileConfig {
  label: string;
  value: number;
  variant: string;
  icon: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------

/**
 * Dashboard Page — Real-time conversion progress tracking.
 *
 * US7 — Track Conversion Progress in Real-Time
 *
 * Features:
 * - Metric tiles (runbook pattern) for batch summary
 * - ProgressTracker list showing each document
 * - Auto-refresh via statusService polling (3s default)
 * - Auto-stop polling when all documents reach terminal state
 * - Network error handling with retry
 *
 * Accessibility:
 * - Semantic heading hierarchy (h1 > h2)
 * - aria-live region for summary changes
 * - Keyboard-navigable cards and controls
 */
export default function DashboardPage() {
  // -----------------------------------------------------------------------
  // State
  // -----------------------------------------------------------------------

  const [documents, setDocuments] = useState<DocumentStatus[]>([]);
  const [summary, setSummary] = useState<StatusSummary>({
    total: 0,
    pending: 0,
    processing: 0,
    completed: 0,
    failed: 0,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const stopPollingRef = useRef<(() => void) | null>(null);

  // Preview modal state (T063)
  const [previewDoc, setPreviewDoc] = useState<DocumentStatus | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // Delete state (T008)
  const [deleteTarget, setDeleteTarget] = useState<{id: string; name: string} | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteTriggerRef = useRef<HTMLButtonElement | null>(null);

  // Clear All state (T009)
  const [showClearAll, setShowClearAll] = useState(false);
  const [isClearingAll, setIsClearingAll] = useState(false);
  const clearAllTriggerRef = useRef<HTMLButtonElement | null>(null);

  // aria-live announcement (T010)
  const [announcement, setAnnouncement] = useState('');

  // -----------------------------------------------------------------------
  // Polling lifecycle (T052)
  // -----------------------------------------------------------------------

  const handleUpdate = useCallback((response: StatusResponse) => {
    setDocuments(response.documents);
    setSummary(response.summary);
    setIsLoading(false);
    setError(null);
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;

    const stopFn = startPolling((response) => {
      handleUpdate(response);
    }, 3000);

    stopPollingRef.current = stopFn;

    return () => {
      stopFn();
      stopPollingRef.current = null;
    };
  }, [autoRefresh, handleUpdate]);

  useEffect(() => {
    const origConsoleError = console.error;
    console.error = (...args: unknown[]) => {
      const msg = args.join(' ');
      if (msg.includes('[statusService] Polling error')) {
        setError('Unable to reach the server. Retrying…');
        setIsLoading(false);
      }
      origConsoleError.apply(console, args);
    };

    return () => {
      console.error = origConsoleError;
    };
  }, []);

  // -----------------------------------------------------------------------
  // Retry handler
  // -----------------------------------------------------------------------

  const handleRetry = useCallback((documentId: string) => {
    setAutoRefresh(true);
    console.info(`[Dashboard] Retry requested for document: ${documentId}`);
  }, []);

  const handleManualRefresh = useCallback(() => {
    setAutoRefresh(true);
    setError(null);
  }, []);

  // -----------------------------------------------------------------------
  // Preview handler (T063)
  // -----------------------------------------------------------------------

  const handlePreview = useCallback((doc: DocumentStatus) => {
    setPreviewDoc(doc);
    setPreviewError(null);
    setPreviewLoading(false);
    setPreviewUrl(`/api/preview/${doc.document_id}`);
  }, []);

  const handleClosePreview = useCallback(() => {
    setPreviewDoc(null);
    setPreviewUrl(null);
    setPreviewError(null);
    setPreviewLoading(false);
  }, []);

  // Escape key closes preview overlay
  useEffect(() => {
    if (!previewDoc) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClosePreview();
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [previewDoc, handleClosePreview]);

  // -----------------------------------------------------------------------
  // Announce helper (T010)
  // -----------------------------------------------------------------------

  const announce = useCallback((text: string) => {
    setAnnouncement(text);
    const timer = setTimeout(() => setAnnouncement(''), 5000);
    return () => clearTimeout(timer);
  }, []);

  // -----------------------------------------------------------------------
  // Individual delete handlers (T008)
  // -----------------------------------------------------------------------

  const handleDeleteRequest = useCallback(
    (documentId: string, name: string) => {
      const activeEl = document.activeElement;
      if (activeEl instanceof HTMLButtonElement) {
        deleteTriggerRef.current = activeEl;
      }
      setDeleteTarget({ id: documentId, name });
      setDeleteError(null);
    },
    []
  );

  const handleDeleteConfirm = useCallback(async () => {
    if (!deleteTarget) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      await deleteDocument(deleteTarget.id);

      setDocuments((prev) =>
        prev.filter((d) => d.document_id !== deleteTarget.id)
      );
      setSummary((prev) => {
        const doc = documents.find((d) => d.document_id === deleteTarget.id);
        if (!doc) return prev;
        return {
          ...prev,
          total: Math.max(0, prev.total - 1),
          [doc.status]: Math.max(0, (prev[doc.status] || 0) - 1),
        };
      });

      announce(`${deleteTarget.name} has been deleted.`);
      setDeleteTarget(null);

      setTimeout(() => {
        deleteTriggerRef.current?.focus();
        deleteTriggerRef.current = null;
      }, 100);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : 'Failed to delete document. Please try again.';
      setDeleteError(message);
      announce('Failed to delete document. Please try again.');
    } finally {
      setIsDeleting(false);
    }
  }, [deleteTarget, documents, announce]);

  const handleDeleteCancel = useCallback(() => {
    setDeleteTarget(null);
    setDeleteError(null);

    setTimeout(() => {
      deleteTriggerRef.current?.focus();
      deleteTriggerRef.current = null;
    }, 100);
  }, []);

  // -----------------------------------------------------------------------
  // Clear All handlers (T009)
  // -----------------------------------------------------------------------

  const handleClearAllRequest = useCallback(() => {
    const activeEl = document.activeElement;
    if (activeEl instanceof HTMLButtonElement) {
      clearAllTriggerRef.current = activeEl;
    }
    setShowClearAll(true);
    setDeleteError(null);
  }, []);

  const handleClearAllConfirm = useCallback(async () => {
    setIsClearingAll(true);
    setDeleteError(null);

    try {
      await deleteAllDocuments();

      setDocuments([]);
      setSummary({
        total: 0,
        pending: 0,
        processing: 0,
        completed: 0,
        failed: 0,
      });

      setAutoRefresh(false);

      announce('All documents have been deleted.');
      setShowClearAll(false);

      setTimeout(() => {
        clearAllTriggerRef.current?.focus();
        clearAllTriggerRef.current = null;
      }, 100);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : 'Failed to delete all documents. Please try again.';
      setDeleteError(message);
      announce('Failed to delete all documents. Please try again.');
    } finally {
      setIsClearingAll(false);
    }
  }, [announce]);

  const handleClearAllCancel = useCallback(() => {
    setShowClearAll(false);

    setTimeout(() => {
      clearAllTriggerRef.current?.focus();
      clearAllTriggerRef.current = null;
    }, 100);
  }, []);

  // -----------------------------------------------------------------------
  // Metric tile config
  // -----------------------------------------------------------------------

  const tiles: TileConfig[] = [
    { label: 'Total', value: summary.total, variant: 'brand', icon: '📋' },
    { label: 'Pending', value: summary.pending, variant: 'muted', icon: '⏳' },
    { label: 'Processing', value: summary.processing, variant: 'sky', icon: '🔄' },
    { label: 'Completed', value: summary.completed, variant: 'emerald', icon: '✅' },
    { label: 'Failed', value: summary.failed, variant: 'red', icon: '❌' },
  ];

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <>
      {/* ----------------------------------------------------------------
          Page Hero
          ---------------------------------------------------------------- */}
      <section className="dashboard-hero" aria-labelledby="dashboard-heading">
        <div className="container py-4">
          <div className="dashboard-hero__inner">
            <div>
              <h1 id="dashboard-heading" className="dashboard-hero__title">
                Conversion Dashboard
              </h1>
              <p className="dashboard-hero__subtitle">
                Track your document conversions in real time.
              </p>
            </div>
            <Link href="/" className="btn btn-outline-light btn-sm">
              ← Upload More
            </Link>
          </div>
        </div>
      </section>

      <div className="container py-4">
        {/* ----------------------------------------------------------------
            Metric Tiles — Batch Summary
            ---------------------------------------------------------------- */}
        <section aria-labelledby="summary-heading" className="mb-3">
          <h2 id="summary-heading" className="visually-hidden">
            Batch Summary
          </h2>

          {/* Live region for screen reader updates */}
          <div className="visually-hidden" aria-live="polite" aria-atomic="true">
            {`${summary.total} documents: ${summary.completed} completed, ${summary.processing} processing, ${summary.pending} pending, ${summary.failed} failed.`}
          </div>

          <div className="tiles-grid" data-testid="summary-cards">
            {tiles.map((t, i) => (
              <div
                key={t.label}
                className={`tile tile--${t.variant} animate-fadeInUp delay-${i + 1}`}
                data-testid={`summary-card-${t.label.toLowerCase()}`}
              >
                <span className="tile__icon" aria-hidden="true">{t.icon}</span>
                <span className="tile__value">{t.value}</span>
                <span className="tile__label">{t.label}</span>
              </div>
            ))}
          </div>
        </section>

        {/* ----------------------------------------------------------------
            aria-live announcements for delete outcomes (T010)
            ---------------------------------------------------------------- */}
        <div
          className="visually-hidden"
          aria-live="assertive"
          aria-atomic="true"
          data-testid="delete-announcement"
        >
          {announcement}
        </div>

        {/* ----------------------------------------------------------------
            Section Header: Documents + Controls
            ---------------------------------------------------------------- */}
        <div className="section-bar">
          <h2 className="section-bar__title">Documents</h2>
          <div className="section-bar__actions">
            <button
              type="button"
              className={`btn btn-sm ${autoRefresh ? 'btn-info' : 'btn-outline-secondary'}`}
              onClick={() => setAutoRefresh((prev) => !prev)}
              aria-pressed={autoRefresh}
              data-testid="auto-refresh-toggle"
              title={autoRefresh ? 'Auto-refresh is on (click to pause)' : 'Auto-refresh is off (click to resume)'}
            >
              {autoRefresh ? (
                <>
                  <span className="spinner-grow spinner-grow-sm me-1" role="status" aria-hidden="true" />
                  Auto-refresh On
                </>
              ) : (
                '⏸ Auto-refresh Off'
              )}
            </button>
            {!autoRefresh && (
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                onClick={handleManualRefresh}
                data-testid="refresh-btn"
              >
                🔄 Refresh
              </button>
            )}
            {documents.length > 0 && (
              <button
                type="button"
                className="btn btn-sm btn-outline-danger"
                onClick={handleClearAllRequest}
                aria-label="Delete all documents"
                data-testid="clear-all-btn"
              >
                🗑️ Clear All
              </button>
            )}
          </div>
        </div>

        {/* ----------------------------------------------------------------
            Error Banner
            ---------------------------------------------------------------- */}
        {error && (
          <div
            className="alert alert-warning d-flex align-items-center gap-2 mb-3"
            role="alert"
            data-testid="network-error"
          >
            <span aria-hidden="true">⚠️</span>
            <span>{error}</span>
            <button
              type="button"
              className="btn btn-sm btn-outline-warning ms-auto"
              onClick={handleManualRefresh}
            >
              Retry Now
            </button>
          </div>
        )}

        {/* ----------------------------------------------------------------
            Delete Error Banner (T008)
            ---------------------------------------------------------------- */}
        {deleteError && (
          <div
            className="alert alert-danger d-flex align-items-center gap-2 mb-3"
            role="alert"
            data-testid="delete-error"
          >
            <span aria-hidden="true">⚠️</span>
            <span>{deleteError}</span>
            <button
              type="button"
              className="btn-close ms-auto"
              aria-label="Dismiss error"
              onClick={() => setDeleteError(null)}
            />
          </div>
        )}

        {/* ----------------------------------------------------------------
            Loading State
            ---------------------------------------------------------------- */}
        {isLoading && (
          <div
            className="loading-state"
            data-testid="loading-state"
            role="status"
          >
            <div className="spinner-border mb-3" aria-hidden="true">
              <span className="visually-hidden">Loading…</span>
            </div>
            <p className="text-muted mb-0">Loading document statuses…</p>
          </div>
        )}

        {/* ----------------------------------------------------------------
            Document Progress List
            ---------------------------------------------------------------- */}
        {!isLoading && (
          <ProgressTracker
            documents={documents}
            onRetry={handleRetry}
            onPreview={handlePreview}
            onDelete={handleDeleteRequest}
          />
        )}

        {/* ----------------------------------------------------------------
            Preview Panel (T063)
            ---------------------------------------------------------------- */}
        {previewDoc && (
          <div
            className="preview-overlay"
            data-testid="preview-overlay"
            role="dialog"
            aria-modal="true"
            aria-label={`Preview of ${previewDoc.name}`}
          >
            <div className="preview-panel">
              {previewLoading && (
                <div className="loading-state" data-testid="preview-panel-loading" role="status">
                  <div className="spinner-border mb-3" aria-hidden="true" />
                  <p className="text-muted mb-0">Loading preview…</p>
                </div>
              )}

              {previewError && (
                <div className="alert alert-danger m-4" role="alert" data-testid="preview-panel-error">
                  <p className="mb-2">{previewError}</p>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-danger"
                    onClick={() => handlePreview(previewDoc)}
                  >
                    🔄 Retry
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary ms-2"
                    onClick={handleClosePreview}
                  >
                    Close
                  </button>
                </div>
              )}

              {previewUrl && !previewLoading && !previewError && (
                <DocumentPreview
                  previewUrl={previewUrl}
                  documentName={previewDoc.name}
                  flaggedPages={
                    previewDoc.has_review_flags ? previewDoc.review_pages : []
                  }
                  onClose={handleClosePreview}
                />
              )}
            </div>
          </div>
        )}

        {/* ----------------------------------------------------------------
            Delete Confirmation Dialog (T008)
            ---------------------------------------------------------------- */}
        <ConfirmDialog
          isOpen={deleteTarget !== null}
          title="Delete Document"
          message={
            deleteTarget
              ? `Are you sure you want to permanently delete "${deleteTarget.name}"? This will remove the original file and all converted output. This action cannot be undone.`
              : ''
          }
          confirmLabel="Delete"
          cancelLabel="Cancel"
          variant="danger"
          onConfirm={handleDeleteConfirm}
          onCancel={handleDeleteCancel}
          isLoading={isDeleting}
        />

        {/* ----------------------------------------------------------------
            Clear All Confirmation Dialog (T009)
            ---------------------------------------------------------------- */}
        <ConfirmDialog
          isOpen={showClearAll}
          title="Clear All Documents"
          message={`Are you sure you want to permanently delete all ${documents.length} document(s)? This will remove all uploaded files and converted output. This action cannot be undone.`}
          confirmLabel="Delete All"
          cancelLabel="Cancel"
          variant="danger"
          onConfirm={handleClearAllConfirm}
          onCancel={handleClearAllCancel}
          isLoading={isClearingAll}
        />
      </div>

      {/* ----------------------------------------------------------------
          Styles
          ---------------------------------------------------------------- */}
      <style jsx>{`
        .dashboard-hero {
          background: linear-gradient(135deg, #0c1a30 0%, #0a1628 50%, #0f2340 100%);
          border-bottom: 1px solid var(--border);
        }

        [data-theme="light"] .dashboard-hero {
          background: linear-gradient(135deg, var(--nc-navy) 0%, var(--nc-navy-dark) 100%);
        }

        .dashboard-hero__inner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 1rem;
        }

        .dashboard-hero__title {
          font-family: var(--font-heading);
          font-size: 1.75rem;
          font-weight: 800;
          color: #fff;
          margin-bottom: 0.25rem;
        }

        .dashboard-hero__subtitle {
          font-family: var(--font-body);
          font-size: 0.9375rem;
          color: rgba(255, 255, 255, 0.7);
          margin-bottom: 0;
        }

        .tiles-grid {
          display: grid;
          grid-template-columns: repeat(5, 1fr);
          gap: 0.75rem;
        }

        @media (max-width: 767.98px) {
          .tiles-grid {
            grid-template-columns: repeat(3, 1fr);
          }
        }

        @media (max-width: 575.98px) {
          .tiles-grid {
            grid-template-columns: repeat(2, 1fr);
          }
        }

        .section-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 1rem;
          padding-bottom: 0.75rem;
          border-bottom: 1px solid var(--border);
        }

        .section-bar__title {
          font-family: var(--font-heading);
          font-size: 1.15rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .section-bar__actions {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .loading-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 3rem 1rem;
        }

        .preview-overlay {
          position: fixed;
          inset: 0;
          z-index: 1050;
          background: var(--overlay);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1rem;
          animation: fadeIn 0.2s ease;
        }

        .preview-panel {
          width: 100%;
          max-width: 960px;
          max-height: 90vh;
          overflow-y: auto;
          border-radius: var(--radius-lg);
          background: var(--card-bg);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-lg);
        }
      `}</style>
    </>
  );
}
