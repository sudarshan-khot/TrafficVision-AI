import { Bar, BarChart, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';
import { useAnalytics } from '../hooks/useAnalytics';

export default function AnalyticsPage() {
  const { analytics, loading, error, startDate, endDate, setDateRange } = useAnalytics();

  return (
    <div className="page">
      <h2>Analytics</h2>

      <div className="filter-bar">
        <label>
          Start
          <input type="date" value={startDate} onChange={(e) => setDateRange(e.target.value, endDate)} />
        </label>
        <label>
          End
          <input type="date" value={endDate} onChange={(e) => setDateRange(startDate, e.target.value)} />
        </label>
      </div>

      {loading && <LoadingSpinner />}
      {error && <div className="error-banner">{error}</div>}

      {!loading && analytics && analytics.total === 0 && (
        <EmptyState message="No data available for the selected period" />
      )}

      {!loading && analytics && analytics.total > 0 && (
        <>
          <div className="chart-card">
            <h3>Violations by Type</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={Object.entries(analytics.by_type).map(([type, count]) => ({ type, count }))}>
                <XAxis dataKey="type" tick={{ fontSize: 10 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="count" fill="#6366f1" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-card">
            <h3>Daily Trend</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={analytics.by_date}>
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="count" stroke="#10b981" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
