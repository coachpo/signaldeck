// navigator.clipboard exists only in secure contexts, but SignalDeck is also served
// over plain HTTP on trusted networks. There the copy command still works, but only
// while the click is being handled, so call this before awaiting anything else.
export async function copyText(text: string) {
  if (navigator.clipboard) return navigator.clipboard.writeText(text);
  const field = document.createElement("textarea");
  field.value = text;
  field.readOnly = true;
  // Off screen, without scrolling on focus or zooming on iOS.
  Object.assign(field.style, { position: "fixed", top: "0", left: "-9999px", fontSize: "12pt" });
  const focused = document.activeElement;
  document.body.append(field);
  field.focus({ preventScroll: true });
  field.select();
  field.setSelectionRange(0, field.value.length);
  try {
    if (!document.execCommand("copy")) throw new Error("The browser did not copy the text.");
  } finally {
    field.remove();
    if (focused instanceof HTMLElement) focused.focus({ preventScroll: true });
  }
}
