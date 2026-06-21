import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import api, { fixMinioUrl } from '../api/client';
import ConfidenceBadge from '../components/ConfidenceBadge';
import LoadingSpinner from '../components/LoadingSpinner';
import type { ViolationDetailResponse } from '../types';

export default function ViolationDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ViolationDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api
      .get<ViolationDetailResponse>(`/violations/${id}`)
      .then((res) => setData(res.data))
      .catch(() => setError('Violation not found'))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingSpinner />;
  if (error || !data) {
    return (
      <div className="page">
        <h2>Violation not found</h2>
        <p>{error}</p>
        <Link to="/violations">Back to violations list</Link>
      </div>
    );
  }

  return (
    <div className="page">
      <h2>Violation Detail</h2>
      <div className="card">
        <p><strong>Type:</strong> {data.violation_type}</p>
        <p><strong>Confidence:</strong> <ConfidenceBadge confidence={data.confidence} /></p>
        <p><strong>Plate:</strong> {data.plate_number || '—'}</p>
        <p><strong>Timestamp:</strong> {new Date(data.created_at).toLocaleString()}</p>
      </div>

      {(!data.all_vehicles || data.all_vehicles.length === 0) && (
        <div className="card">
          <h3>Annotated Image</h3>
          {data.annotated_image_url && !imgError ? (
            <img
              src={fixMinioUrl(data.annotated_image_url)}
              alt="Annotated violation"
              className="annotated-image"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="image-placeholder">
              <p>Annotated image unavailable</p>
            </div>
          )}
        </div>
      )}

      {data.vehicle && (
        <div className="card">
          <h3>Vehicle Info</h3>
          <p><strong>Class:</strong> {data.vehicle.vehicle_class}</p>
          <p><strong>Bounding box:</strong> ({data.vehicle.bounding_box.x1}, {data.vehicle.bounding_box.y1}) &rarr; ({data.vehicle.bounding_box.x2}, {data.vehicle.bounding_box.y2})</p>
        </div>
      )}

      {data.all_vehicles && data.all_vehicles.length > 0 && (
        <div className="card">
          <h3>All Classified Objects in Image ({data.all_vehicles.length})</h3>

          {data.annotated_image_url && !imgError ? (
            <div style={{ margin: '1rem 0 1.5rem 0', textAlign: 'center' }}>
              <img
                src={fixMinioUrl(data.annotated_image_url)}
                alt="Annotated classifications"
                className="annotated-image"
                style={{ maxWidth: '100%', borderRadius: '8px', border: '1px solid #cbd5e1', display: 'inline-block' }}
                onError={() => setImgError(true)}
              />
            </div>
          ) : (
            <div className="image-placeholder" style={{ margin: '1rem 0 1.5rem 0' }}>
              <p>Annotated image unavailable</p>
            </div>
          )}

          <table className="data-table" style={{ width: '100%', marginTop: '1rem' }}>
            <thead>
              <tr>
                <th>Class</th>
                <th>Plate Number</th>
                <th>Bounding Box</th>
              </tr>
            </thead>
            <tbody>
              {data.all_vehicles.map((v) => (
                <tr key={v.id}>
                  <td style={{ textTransform: 'capitalize' }}>{v.vehicle_class}</td>
                  <td>{v.plate_number || '—'}</td>
                  <td>
                    ({v.bounding_box.x1}, {v.bounding_box.y1}) &rarr; ({v.bounding_box.x2}, {v.bounding_box.y2})
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
