interface EmptyStateProps {
  message: string;
}

export default function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="empty-icon">📭</span>
      <p>{message}</p>
    </div>
  );
}
