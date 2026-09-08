export function runSearch(
  current: URLSearchParams,
  next: Record<string, string>,
) {
  const query = new URLSearchParams(next);
  const history = current.get("history");
  if (history) query.set("history", history);
  return query;
}
