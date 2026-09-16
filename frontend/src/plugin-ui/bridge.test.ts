import { afterEach, describe, expect, it, vi } from 'vitest';
import { mountBridge, pluginFetch, validPath, send } from './bridge';

const cleanups: (() => void)[] = [];
function install(...args: Parameters<typeof mountBridge>) { cleanups.push(mountBridge(...args)); }
afterEach(() => { for (const cleanup of cleanups.splice(0)) cleanup(); history.replaceState(null, '', '/'); vi.unstubAllGlobals(); localStorage.clear(); document.body.replaceChildren(); });

describe('plugin transport boundary', () => {
  it('rejects external and ambiguous navigation paths', () => {
    for (const path of ['/../api', '/%2e%2e/api', '/%2fapi', 'https://other.test/', '//other.test/', '/\\other.test', '/\nother']) expect(validPath(path)).toBe(false);
    expect(validPath('/?noteId=one')).toBe(true);
  });
  it('ignores an old stored access token and preserves request options', async () => {
    localStorage.setItem('signaldeck.apiToken', 'test-token');
    const fetch = vi.fn().mockResolvedValue(new Response('{}'));
    vi.stubGlobal('fetch', fetch);
    const init = {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'};
    await pluginFetch('api/notes', init);
    expect(fetch.mock.calls[0][0]).toBe('/api/notes');
    expect(fetch.mock.calls[0][1]).toBe(init);
    expect(new Headers(fetch.mock.calls[0][1].headers).has('Authorization')).toBe(false);
  });
  it('returns a plugin 401 without prompting for credentials or retrying', async () => {
    const response = new Response('{}', {status:401});
    const fetch = vi.fn().mockResolvedValue(response);
    const prompt = vi.fn();
    vi.stubGlobal('fetch', fetch); vi.stubGlobal('prompt', prompt);
    expect(await pluginFetch('api/notes')).toBe(response);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(prompt).not.toHaveBeenCalled();
  });
  it('keeps mounted API calls within the plugin gateway prefix', async () => {
    history.replaceState(null, '', '/_plugins/release-one/?embedded=1');
    vi.resetModules();
    const mounted = await import('./bridge');
    const fetch = vi.fn().mockResolvedValue(new Response('{}')); vi.stubGlobal('fetch', fetch);
    await mounted.pluginFetch('api/reports');
    expect(fetch.mock.calls[0][0]).toBe('/_plugins/release-one/api/reports');
  });
  it('applies host navigation while a cancelable read is busy', () => {
    install(vi.fn());
    send('state', {dirty:false, busy:true});
    window.dispatchEvent(new MessageEvent('message', {origin:location.origin, source:window.parent,
      data:{protocol:'signaldeck.pluginUi/1',type:'location',path:'/?noteId=confirmed'}}));
    expect(new URLSearchParams(location.search).get('noteId')).toBe('confirmed');
    send('state', {dirty:false, busy:false});
  });
  it('cancels a deferred location when history returns to the current page during a write', async () => {
    history.replaceState(null, '', '/?report=A');
    let writing = true; install(vi.fn(), () => writing);
    send('state', {dirty:true,busy:true});
    const locationMessage = (path: string) => window.dispatchEvent(new MessageEvent('message', {
      origin:location.origin, source:window.parent, data:{protocol:'signaldeck.pluginUi/1',type:'location',path},
    }));
    locationMessage('/?report=B');
    locationMessage('/?report=A');
    writing = false; send('state', {dirty:true,busy:false});
    await Promise.resolve();
    expect(new URLSearchParams(location.search).get('report')).toBe('A');
  });
  it('ignores foreign sources, origins and malformed preferences', () => {
    const expert = vi.fn(); install(expert);
    const data = {protocol:'signaldeck.pluginUi/1',type:'preferences',theme:'dark',expertMode:true};
    window.dispatchEvent(new MessageEvent('message',{data,origin:'https://foreign.test',source:window.parent}));
    window.dispatchEvent(new MessageEvent('message',{data,origin:location.origin,source:null}));
    window.dispatchEvent(new MessageEvent('message',{data:{...data,token:'unexpected'},origin:location.origin,source:window.parent}));
    expect(expert).not.toHaveBeenCalled();
    window.dispatchEvent(new MessageEvent('message',{data,origin:location.origin,source:window.parent}));
    expect(expert).toHaveBeenCalledWith(true);
  });
});
