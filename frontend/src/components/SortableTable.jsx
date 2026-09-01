import { ArrowUp, ArrowDown, ArrowUpDown } from "lucide-react";

/** Sortable table header cell. Click cycles asc→desc. */
export function SortableTh({ label, sortKey, sort, onSort, align = "left", className = "" }) {
  const isActive = sort?.by === sortKey;
  const dir = isActive ? sort.dir : null;
  return (
    <th
      onClick={() => onSort(sortKey)}
      data-testid={`th-${sortKey}`}
      className={`grid-cell sort-th text-${align} ${className}`}
      title={`Sort by ${label}`}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <span className="sort-arrow">
          {dir === "asc" ? <ArrowUp size={10} /> : dir === "desc" ? <ArrowDown size={10} /> : <ArrowUpDown size={10} className="opacity-40" />}
        </span>
      </span>
    </th>
  );
}

export function useSort(initialKey, initialDir = "desc") {
  // Small helper to keep the sort state consistent
  return null; // unused; sort state managed per-page via useState.
}

export function nextDir(prevBy, prevDir, key) {
  if (prevBy !== key) return { by: key, dir: "desc" };
  return { by: key, dir: prevDir === "desc" ? "asc" : "desc" };
}
