import { useEffect, useState } from "react";

// Debounces free-text search input so it doesn't fire a query on every
// keystroke; also resets pagination whenever the debounced term changes.
export function useDebouncedSearch(resetOffset: () => void, delay = 250): [string, (v: string) => void, string] {
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");

  useEffect(() => {
    const handle = setTimeout(() => { setQ(qInput.trim()); resetOffset(); }, delay);
    return () => clearTimeout(handle);
  }, [qInput]);

  return [qInput, setQInput, q];
}
