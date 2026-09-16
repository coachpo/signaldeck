let busy = false;
let pendingExpert: (() => void) | undefined;
let pendingLocation: (() => void) | undefined;
const protocol = 'signaldeck.pluginUi/1';
export const embedded = window.parent !== window && new URLSearchParams(location.search).get('embedded') === '1';
const mount = location.pathname.match(/^\/_plugins\/[^/]+\//)?.[0] ?? '/';
export function pluginUrl(path: string) { return mount + path.replace(/^\//, ''); }
export async function pluginFetch(path: string, init: RequestInit = {}) {
  return fetch(pluginUrl(path), init);
}
export function send(type: string, fields: Record<string, unknown> = {}) {
  if (type === 'state') { busy = fields.busy === true; if (!busy && pendingLocation) { const apply = pendingLocation; pendingLocation = undefined; queueMicrotask(apply); } }
  if (!busy && pendingExpert) { const apply = pendingExpert; pendingExpert = undefined; queueMicrotask(apply); }
  if (embedded) window.parent.postMessage({ protocol, type, ...fields }, location.origin);
}
export function relativeLocation() {
  const params = new URLSearchParams(location.search); params.delete('embedded');
  return '/' + location.pathname.slice(mount.length) + (params.size ? '?' + params : '') + location.hash;
}
export function navigate(path: string, replace = false, render = true) {
  if (!validPath(path)) return;
  const clean = new URL(path, location.origin); clean.searchParams.delete('embedded');
  path = clean.pathname + clean.search + clean.hash;
  const target = new URL(pluginUrl(path), location.origin);
  if (embedded) target.searchParams.set('embedded', '1');
  history[embedded || replace ? 'replaceState' : 'pushState'](null, '', target);
  send('navigate', { path, replace });
  if (render) window.dispatchEvent(new PopStateEvent('popstate'));
}
export function validPath(path: unknown): path is string {
  if (typeof path !== 'string' || !path.startsWith('/') || path.startsWith('//') || (path.includes('\\') || [...path].some(char => char.charCodeAt(0) <= 32))) return false;
  try {
    const pathname = path.split(/[?#]/)[0];
    const decoded = decodeURIComponent(pathname);
    return !decoded.includes('\\') && ![...decoded].some(char => char.charCodeAt(0) <= 32) && !decoded.split('/').some(part => part === '.' || part === '..') && !/%2f/i.test(pathname) && new URL(path, location.origin).origin === location.origin;
  } catch { return false; }
}
export function mountBridge(onExpert: (expert: boolean) => void, navigationBlocked: () => boolean = () => false) {
  const receive = (event: MessageEvent) => {
    if (event.origin !== location.origin || event.source !== window.parent) return;
    const value = event.data;
    if (!value || value.protocol !== protocol) return;
    if (value.type === 'preferences' && Object.keys(value).every(key => ['protocol', 'type', 'theme', 'expertMode', 'returnTo'].includes(key)) && ['light','dark','system'].includes(value.theme) && typeof value.expertMode === 'boolean' && (value.returnTo === undefined || value.returnTo === null || validPath(value.returnTo))) {
      const dark = value.theme === 'dark' || (value.theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
      document.documentElement.classList.toggle('dark', dark);
      document.documentElement.classList.toggle('light', !dark);
      if (busy) pendingExpert = () => onExpert(value.expertMode); else onExpert(value.expertMode);
    }
    if (value.type === 'location' && Object.keys(value).every(key => ['protocol','type','path'].includes(key)) && validPath(value.path)) {
      pendingLocation = undefined;
      if (value.path === relativeLocation()) return;
      const apply = () => { const target = new URL(pluginUrl(value.path), location.origin); target.searchParams.set('embedded', '1');
        history.replaceState(null, '', target); window.dispatchEvent(new PopStateEvent('popstate')); };
      if (navigationBlocked()) pendingLocation = apply; else apply();
    }
  };
  window.addEventListener('message', receive);
  const follow = (event: MouseEvent) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest('a') : null;
    if (!link || link.target || link.download) return;
    const url = new URL(link.href);
    if (url.origin === location.origin && url.pathname.startsWith(mount)) {
      event.preventDefault(); const params = new URLSearchParams(url.search); params.delete('embedded');
      navigate('/' + url.pathname.slice(mount.length) + (params.size ? '?' + params : '') + url.hash);
    }
  };
  document.addEventListener('click', follow);
  send('ready');
  return () => { window.removeEventListener('message', receive); document.removeEventListener('click', follow); };
}
