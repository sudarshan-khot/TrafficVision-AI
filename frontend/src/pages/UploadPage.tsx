import { useCallback, useEffect, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { useNavigate } from 'react-router-dom';
import LoadingSpinner from '../components/LoadingSpinner';
import { useUpload } from '../hooks/useUpload';
import { fixMinioUrl } from '../api/client';

const ANALYSIS_STEPS = [
  'Validating local image format...',
  'Uploading image to MinIO storage...',
  'Retrieving original image from storage...',
  'Running YOLOv8m base vehicle classification...',
  'Checking helmet compliance on motorcycles...',
  'Running PaddleOCR for license plate reading...',
  'Evaluating rules in the violation engine...',
  'Generating and uploading annotated evidence...',
  'Saving tracking and violation data to database...',
  'Completing analysis processing...'
];

export default function UploadPage() {
  const { upload, status, result, error } = useUpload();
  const navigate = useNavigate();
  const [activeStepIndex, setActiveStepIndex] = useState(0);

  const onDrop = useCallback(
    (files: File[]) => {
      if (files[0]) upload(files[0]);
    },
    [upload],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'image/jpeg': [], 'image/png': [] },
    maxFiles: 1,
    disabled: status === 'uploading' || status === 'analyzing',
  });

  useEffect(() => {
    if (status === 'success' && result?.violations.length) {
      navigate(`/violations/${result.violations[0].id}`);
    }
  }, [status, result, navigate]);

  useEffect(() => {
    if (status === 'idle') {
      setActiveStepIndex(0);
    } else if (status === 'validating') {
      setActiveStepIndex(0);
    } else if (status === 'uploading') {
      setActiveStepIndex(1);
    } else if (status === 'analyzing') {
      setActiveStepIndex(2);
      const interval = setInterval(() => {
        setActiveStepIndex((prev) => {
          if (prev < ANALYSIS_STEPS.length - 1) {
            return prev + 1;
          }
          return prev;
        });
      }, 1500);
      return () => clearInterval(interval);
    } else if (status === 'success') {
      setActiveStepIndex(ANALYSIS_STEPS.length);
    }
  }, [status]);

  const busy = status === 'uploading' || status === 'analyzing' || status === 'validating';

  return (
    <div className="page">
      <h2>Upload Image</h2>
      <div {...getRootProps()} className={`dropzone ${isDragActive ? 'active' : ''}`}>
        <input {...getInputProps()} />
        <p>{isDragActive ? 'Drop image here' : 'Drag & drop a JPEG/PNG image, or click to select'}</p>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {busy && (
        <div className="stepper-container">
          <div className="stepper-header">
            <LoadingSpinner />
            <span>Processing Traffic Image...</span>
          </div>

          <div className="stepper-progress-bar-bg">
            <div
              className="stepper-progress-bar-fill"
              style={{
                width: `${((activeStepIndex + 1) / ANALYSIS_STEPS.length) * 100}%`,
              }}
            />
          </div>

          <ul className="stepper-list">
            {ANALYSIS_STEPS.map((stepText, idx) => {
              let circleClass = 'stepper-circle';
              let textClass = 'stepper-text';

              if (idx < activeStepIndex) {
                circleClass += ' completed';
                textClass += ' completed';
              } else if (idx === activeStepIndex) {
                circleClass += ' active';
                textClass += ' active';
              }

              return (
                <li key={idx} className="stepper-item">
                  <div className={circleClass}>
                    {idx < activeStepIndex ? '✓' : idx + 1}
                  </div>
                  <div className={textClass}>{stepText}</div>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {status === 'success' && result && (
        <>
          <div className="card analysis-result">
            {result.violations.length === 0 ? (
              <p>No violations detected</p>
            ) : (
              <p>Found {result.violations.length} violation(s). Processing time: {result.processing_time_ms}ms</p>
            )}
          </div>

          {result.vehicles && result.vehicles.length > 0 && (
            <div className="card">
              <h3>Classified Objects ({result.vehicles.length})</h3>

              {result.annotated_image_url && (
                <div style={{ margin: '1rem 0 1.5rem 0', textAlign: 'center' }}>
                  <img
                    src={fixMinioUrl(result.annotated_image_url)}
                    alt="Annotated classifications"
                    className="annotated-image"
                    style={{ maxWidth: '100%', borderRadius: '8px', border: '1px solid #cbd5e1', display: 'inline-block' }}
                  />
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
                  {result.vehicles.map((v) => (
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
        </>
      )}
    </div>
  );
}
