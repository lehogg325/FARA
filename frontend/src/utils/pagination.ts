export function makeResetPage(setOffset: (n: number) => void) {
  return <T>(setter: (v: T) => void) => (v: T) => { setter(v); setOffset(0); };
}
