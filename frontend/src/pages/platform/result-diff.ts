export type DiffBlock = { kind: "same" | "removed" | "added"; text: string };
/** Bounded line comparison. Large changed regions are emitted whole, never truncated. */
export function compareText(left: string, right: string): { blocks: DiffBlock[]; coarse: boolean } {
  const a = left.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  const b = right.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  let end = 0;
  while (end < a.length - start && end < b.length - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end++;
  const aa = a.slice(start, a.length - end);
  const bb = b.slice(start, b.length - end);
  const blocks: DiffBlock[] = [];
  const add = (kind: DiffBlock["kind"], text: string) => {
    if (!text) return;
    if (blocks.at(-1)?.kind === kind) blocks[blocks.length - 1].text += text;
    else blocks.push({ kind, text });
  };
  add("same", a.slice(0, start).join(""));
  const coarse = (aa.length + 1) * (bb.length + 1) > 250_000;
  if (coarse) {
    add("removed", aa.join(""));
    add("added", bb.join(""));
  } else {
    const width = bb.length + 1;
    const lengths = new Uint32Array((aa.length + 1) * width);
    for (let i = aa.length - 1; i >= 0; i--) {
      for (let j = bb.length - 1; j >= 0; j--) {
        lengths[i * width + j] = aa[i] === bb[j] ? 1 + lengths[(i + 1) * width + j + 1]
          : Math.max(lengths[(i + 1) * width + j], lengths[i * width + j + 1]);
      }
    }
    let i = 0, j = 0;
    while (i < aa.length || j < bb.length) {
      if (i < aa.length && j < bb.length && aa[i] === bb[j]) { add("same", aa[i]); i++; j++; }
      else if (i < aa.length && (j === bb.length || lengths[(i + 1) * width + j] >= lengths[i * width + j + 1])) { add("removed", aa[i++]); }
      else { add("added", bb[j++]); }
    }
  }
  add("same", end ? a.slice(a.length - end).join("") : "");
  return { blocks, coarse };
}
