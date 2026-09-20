export function formatDate(d: string | null): string {
  return d ?? "—";
}

export function formatCurrency(n: number | null, opts?: Intl.NumberFormatOptions): string | null {
  if (n === null) return null;
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", ...opts }).format(n);
}
