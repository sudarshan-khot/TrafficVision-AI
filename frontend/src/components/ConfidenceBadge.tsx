interface ConfidenceBadgeProps {
  confidence: number;
}

export default function ConfidenceBadge({ confidence }: ConfidenceBadgeProps) {
  const pct = confidence * 100;
  const level = pct >= 80 ? 'high' : pct >= 50 ? 'medium' : 'low';
  return <span className={`confidence-badge confidence-${level}`}>{confidence.toFixed(2)}</span>;
}
