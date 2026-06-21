import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';
import { useAnalytics } from '../hooks/useAnalytics';
import { useViolations } from '../hooks/useViolations';

function SummaryPanel() {
  const { analytics, loading, error } = useAnalytics();
  if (loading) return <LoadingSpinner />;
  if (error) return <div className="error-banner">{error}</div>;
  if (!analytics) return <EmptyState message="No analytics data" />;

  return (
    <div className="summary-panel">
      <div className="stat-card">
        <h3>Total Violations</h3>
        <p className="stat-value">{analytics.total}</p>
      </div>
      {Object.entries(analytics.by_type).map(([type, count]) => (
        <div key={type} className="stat-card">
          <h3>{type.replace(/_/g, ' ')}</h3>
          <p className="stat-value">{count}</p>
        </div>
      ))}
    </div>
  );
}

function DailyViolationsChart() {
  const { analytics, loading } = useAnalytics();
  if (loading || !analytics?.by_date?.length) return null;
  return (
    <div className="chart-card">
      <h3>Daily Violations</h3>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={analytics.by_date}>
          <XAxis dataKey="date" />
          <YAxis />
          <Tooltip />
          <Line type="monotone" dataKey="count" stroke="#3b82f6" strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function RecentViolationsList() {
  const { violations, loading, error } = useViolations({ page_size: 5 });
  if (loading) return <LoadingSpinner />;
  if (error) return <div className="error-banner">{error}</div>;
  if (!violations.length) return <EmptyState message="No recent violations" />;

  return (
    <div className="card">
      <h3>Recent Violations</h3>
      <ul className="violation-list">
        {violations.map((v) => (
          <li key={v.id}>
            <strong>{v.violation_type}</strong> — {v.plate_number || 'No plate'} — {new Date(v.created_at).toLocaleString()}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <div className="page">
      <h2>Dashboard</h2>
      <SummaryPanel />
      <DailyViolationsChart />
      <RecentViolationsList />
    </div>
  );
}
