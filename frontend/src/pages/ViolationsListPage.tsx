import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import api, { fixMinioUrl } from '../api/client';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';
import { useViolations } from '../hooks/useViolations';
import type { ViolationDetailResponse, BoundingBox } from '../types';

const VIOLATION_TYPES = [
  '',
  'HELMET_NON_COMPLIANCE',
  'TRIPLE_RIDING',
  'WRONG_SIDE_DRIVING',
  'STOP_LINE_VIOLATION',
  'ILLEGAL_PARKING',
];

function BoundingBoxPlotter({ imageUrl, box }: { imageUrl: string; box: BoundingBox }) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [coords, setCoords] = useState({ left: 0, top: 0, width: 0, height: 0 });

  const updateBox = () => {
    const img = imgRef.current;
    if (!img || !img.complete) return;

    const renderW = img.clientWidth;
    const renderH = img.clientHeight;
    const naturalW = img.naturalWidth;
    const naturalH = img.naturalHeight;

    if (naturalW === 0 || naturalH === 0) return;

    const scaleX = renderW / naturalW;
    const scaleY = renderH / naturalH;

    setCoords({
      left: box.x1 * scaleX,
      top: box.y1 * scaleY,
      width: (box.x2 - box.x1) * scaleX,
      height: (box.y2 - box.y1) * scaleY,
    });
  };

  useEffect(() => {
    updateBox();
    window.addEventListener('resize', updateBox);
    return () => window.removeEventListener('resize', updateBox);
  }, [imageUrl, box]);

  return (
    <div style={{ position: 'relative', display: 'inline-block', width: '100%', overflow: 'hidden' }}>
      <img
        ref={imgRef}
        src={fixMinioUrl(imageUrl)}
        alt="Original infraction"
        onLoad={updateBox}
        style={{ width: '100%', display: 'block', height: 'auto', borderRadius: '4px' }}
      />
      <div
        style={{
          position: 'absolute',
          left: `${coords.left}px`,
          top: `${coords.top}px`,
          width: `${coords.width}px`,
          height: `${coords.height}px`,
          border: '3px solid #ef4444',
          boxShadow: '0 0 12px rgba(239, 68, 68, 0.75)',
          borderRadius: '4px',
          pointerEvents: 'none',
          boxSizing: 'border-box',
          transition: 'all 0.2s ease-in-out',
        }}
      >
        <span
          style={{
            position: 'absolute',
            top: '-24px',
            left: '-3px',
            backgroundColor: '#ef4444',
            color: '#fff',
            fontSize: '11px',
            padding: '2px 6px',
            fontWeight: 'bold',
            borderRadius: '3px 3px 0 0',
            whiteSpace: 'nowrap',
          }}
        >
          Infracting Vehicle
        </span>
      </div>
    </div>
  );
}

export default function ViolationsListPage() {
  const { violations, totalCount, loading, error, filters, setFilters, setPage } = useViolations();
  const navigate = useNavigate();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedViolation, setSelectedViolation] = useState<ViolationDetailResponse | null>(null);
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);

  const pageSize = filters.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  const handleRowClick = async (violationId: string) => {
    setSelectedId(violationId);
    setDrawerLoading(true);
    setDrawerError(null);
    setSelectedViolation(null);

    try {
      const res = await api.get<ViolationDetailResponse>(`/violations/${violationId}`);
      setSelectedViolation(res.data);
    } catch (err: unknown) {
      setDrawerError('Failed to load violation details');
    } finally {
      setDrawerLoading(false);
    }
  };

  return (
    <div className="page">
      <h2>Violations</h2>

      <div className="filter-bar">
        <select
          value={filters.violation_type || ''}
          onChange={(e) => setFilters({ ...filters, violation_type: e.target.value || undefined, page: 1 })}
        >
          {VIOLATION_TYPES.map((t) => (
            <option key={t} value={t}>{t || 'All types'}</option>
          ))}
        </select>
        <input
          placeholder="Plate number"
          value={filters.plate_number || ''}
          onChange={(e) => setFilters({ ...filters, plate_number: e.target.value || undefined, page: 1 })}
        />
        <input
          type="date"
          value={filters.start_date?.slice(0, 10) || ''}
          onChange={(e) => setFilters({ ...filters, start_date: e.target.value || undefined, page: 1 })}
        />
        <input
          type="date"
          value={filters.end_date?.slice(0, 10) || ''}
          onChange={(e) => setFilters({ ...filters, end_date: e.target.value || undefined, page: 1 })}
        />
      </div>

      <div className="list-page-container">
        <div className="violations-main">
          {loading && <LoadingSpinner />}
          {error && <div className="error-banner">{error}</div>}

          {!loading && !violations.length && <EmptyState message="No violations found" />}

          {violations.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Plate</th>
                  <th>Confidence</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {violations.map((v) => (
                  <tr
                    key={v.id}
                    onClick={() => handleRowClick(v.id)}
                    className={`clickable-row ${selectedId === v.id ? 'selected-row' : ''}`}
                  >
                    <td>{v.violation_type}</td>
                    <td>{v.plate_number || '—'}</td>
                    <td>{v.confidence.toFixed(2)}</td>
                    <td>{new Date(v.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          <div className="pagination">
            <button disabled={(filters.page || 1) <= 1} onClick={() => setPage((filters.page || 1) - 1)}>Prev</button>
            <span>Page {filters.page || 1} of {totalPages}</span>
            <button disabled={(filters.page || 1) >= totalPages} onClick={() => setPage((filters.page || 1) + 1)}>Next</button>
          </div>
        </div>

        {selectedId && (
          <div className="drawer">
            <div className="drawer-header">
              <h3>Violation Info</h3>
              <button
                className="drawer-close-btn"
                onClick={() => {
                  setSelectedId(null);
                  setSelectedViolation(null);
                }}
              >
                &times;
              </button>
            </div>
            <div className="drawer-body">
              {drawerLoading && <LoadingSpinner />}
              {drawerError && <div className="error-banner">{drawerError}</div>}
              {selectedViolation && (
                <>
                  <div className="drawer-info">
                    <p><strong>Type:</strong> {selectedViolation.violation_type}</p>
                    <p><strong>Plate:</strong> {selectedViolation.plate_number || '—'}</p>
                    <p><strong>Confidence:</strong> {selectedViolation.confidence.toFixed(2)}</p>
                    <p><strong>Date:</strong> {new Date(selectedViolation.created_at).toLocaleString()}</p>
                    <button className="btn btn-primary" onClick={() => navigate(`/violations/${selectedViolation.id}`)}>
                      View Full Details
                    </button>
                  </div>

                  <div className="drawer-image-section">
                    <h4>Original Image (Infracting Vehicle Highlighted)</h4>
                    {selectedViolation.original_image_url ? (
                      <BoundingBoxPlotter
                        imageUrl={selectedViolation.original_image_url}
                        box={selectedViolation.bounding_box}
                      />
                    ) : (
                      <div className="image-placeholder">Original image unavailable</div>
                    )}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
