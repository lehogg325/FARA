export function Pagination({
  total, offset, setOffset, pageSize,
}: {
  total: number;
  offset: number;
  setOffset: (o: number) => void;
  pageSize: number;
}) {
  if (total <= pageSize) return null;
  return (
    <div className="pagination">
      <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>&larr; Prev</button>
      <span className="row-meta">{offset + 1}–{Math.min(offset + pageSize, total)} of {total}</span>
      <button disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>Next &rarr;</button>
    </div>
  );
}
