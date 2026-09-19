import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";



const ORIGINAL_API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const ORIGINAL_DEV = import.meta.env.DEV;
const ORIGINAL_FETCH = globalThis.fetch;

function createFetchMock() {
  return vi.fn<
    (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>
  >();
}

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function textResponse(
  body: string,
  status: number,
  headers: Record<string, string> = {},
): Response {
  return new Response(body, {
    status,
    headers: { "content-type": "text/plain", ...headers },
  });
}

async function loadApiModule({
  baseUrl = "",
  dev = true,
}: {
  baseUrl?: string;
  dev?: boolean;
} = {}) {
  vi.resetModules();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", baseUrl);
  Reflect.set(import.meta.env, "DEV", dev);
  return import("./api-client");
}

function getLastFetchCall(fetchMock: ReturnType<typeof createFetchMock>): {
  init: RequestInit | undefined;
  url: string;
} {
  const call = fetchMock.mock.calls.at(-1);

  if (!call) {
    throw new Error("Expected fetch to be called");
  }

  const [input, init] = call;
  return { init, url: String(input) };
}

const draftFixture = {
  id: "draft-1",
  name: "Daily summary",
  parameters: { summary: "Market summary" },
  updatedAt: "2024-03-15T12:00:00Z",
};

const draftInput = {
  name: "Daily summary",
  parameters: { summary: "Market summary" },
};

let fetchMock = createFetchMock();

beforeEach(() => {
  fetchMock = createFetchMock();
  globalThis.fetch = fetchMock as typeof fetch;
  localStorage.clear();
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", "");
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  globalThis.fetch = ORIGINAL_FETCH;
  Reflect.set(import.meta.env, "VITE_API_BASE_URL", ORIGINAL_API_BASE_URL);
  Reflect.set(import.meta.env, "DEV", ORIGINAL_DEV);
});

describe("api client", () => {
  it("sends a successful GET request to the dev API base", async () => {
    const { requestPlatform } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse([draftFixture], 200));

    await expect(requestPlatform("/task-drafts")).resolves.toEqual([draftFixture]);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe("http://127.0.0.1:8000/api/task-drafts");
    expect(init?.method).toBe("GET");
    expect(init?.body).toBeUndefined();
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
  });

  it("does not read or attach a token left in browser storage", async () => {
    localStorage.setItem("signaldeck.apiToken", "obsolete-token");
    const readStorage = vi.spyOn(Storage.prototype, "getItem");
    const promptSpy = vi.spyOn(window, "prompt");
    const { requestPlatform } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 200));

    await expect(requestPlatform("/workflow-packages", {
      headers: { "X-Request-Id": "request-one" },
    })).resolves.toEqual({});

    const headers = new Headers(getLastFetchCall(fetchMock).init?.headers);
    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("X-Request-Id")).toBe("request-one");
    expect(readStorage).not.toHaveBeenCalled();
    expect(promptSpy).not.toHaveBeenCalled();
  });

  it("returns a 401 as an API error without prompting or retrying", async () => {
    const { ApiRequestError, requestPlatform } = await loadApiModule();
    const promptSpy = vi.spyOn(window, "prompt");
    const readStorage = vi.spyOn(Storage.prototype, "getItem");
    const writeStorage = vi.spyOn(Storage.prototype, "setItem");
    fetchMock.mockResolvedValueOnce(jsonResponse({
      code: "upstream_unauthorized",
      message: "Request denied",
      details: [],
    }, 401));

    const request = requestPlatform("/workflow-packages");
    await expect(request).rejects.toBeInstanceOf(ApiRequestError);
    await expect(request).rejects.toMatchObject({
      status: 401,
      code: "upstream_unauthorized",
      message: "Request denied",
      details: [],
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(promptSpy).not.toHaveBeenCalled();
    expect(readStorage).not.toHaveBeenCalled();
    expect(writeStorage).not.toHaveBeenCalled();
  });

  it("sends a successful JSON POST request", async () => {
    const { requestPlatform } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse(draftFixture, 201));

    await expect(
      requestPlatform("/task-drafts", { method: "POST", body: draftInput }),
    ).resolves.toEqual(draftFixture);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe("http://127.0.0.1:8000/api/task-drafts");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(draftInput));
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("preserves status, code, message, and validation details for 422 responses", async () => {
    const { ApiRequestError, requestPlatform } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          code: "validation_error",
          message: "Validation failed",
          details: [
            { field: "name", issue: "Required" },
            { field: "content", issue: "Required" },
            {
              code: "provider_unavailable",
              providerKey: "market-data",
              surface: "tool.quoteLookup",
              retryAfterSeconds: 30,
              recoverable: true,
              optional: null,
            },
            {
              field: "credentials",
              issue: "Invalid credentials",
              apiKey: "sk-secret",
              exceptionType: "RuntimeError",
              debugPayload: { path: "/home/qing/private.py" },
              rawList: ["internal"],
              "bad-key": "not exposed",
            },
            "not an object",
          ],
        },
        422,
      ),
    );

    let error: unknown;
    try {
      await requestPlatform("/task-drafts", { method: "POST", body: draftInput });
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_error",
      message: "Validation failed",
      details: [
        { field: "name", issue: "Required" },
        { field: "content", issue: "Required" },
        {
          code: "provider_unavailable",
          providerKey: "market-data",
          surface: "tool.quoteLookup",
          retryAfterSeconds: 30,
          recoverable: true,
          optional: null,
        },
        { field: "credentials", issue: "Invalid credentials" },
      ],
    });
  });

  it("drops malformed non-array details from JSON error envelopes", async () => {
    const { ApiRequestError, requestPlatform } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(
      jsonResponse(
        {
          code: "validation_error",
          message: "Validation failed",
          details: { field: "name", issue: "Required" },
        },
        422,
      ),
    );

    let error: unknown;
    try {
      await requestPlatform("/task-drafts");
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 422,
      code: "validation_error",
      message: "Validation failed",
      details: [],
    });
  });

  it("falls back to a generic request_failed error for 500 text responses", async () => {
    const { ApiRequestError, requestPlatform } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(textResponse("Internal Server Error", 500));

    let error: unknown;
    try {
      await requestPlatform("/task-drafts");
    } catch (caught) {
      error = caught;
    }

    expect(error).toBeInstanceOf(ApiRequestError);
    expect(error).toMatchObject({
      status: 500,
      code: "request_failed",
      message: "Internal Server Error",
      details: [],
    });
  });

  it.each([
    ["", false, "/api/resources"],
    ["https://signaldeck.example.com/root/", false, "https://signaldeck.example.com/root/api/resources"],
    ["https://signaldeck.example.com/api/v1/", true, "https://signaldeck.example.com/api/resources"],
    ["https://signaldeck.example.com/api/v2/", true, "https://signaldeck.example.com/api/resources"],
  ])("derives the unversioned API base from VITE_API_BASE_URL %j", async (baseUrl, dev, expectedUrl) => {
    const { requestPlatform } = await loadApiModule({ baseUrl, dev });
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(requestPlatform("/resources")).resolves.toEqual({ items: [] });

    expect(getLastFetchCall(fetchMock).url).toBe(expectedUrl);
  });

  it("encodes path segments against the derived base URL", async () => {
    const { requestPlatform, toPathSegment } = await loadApiModule({
      baseUrl: "https://signaldeck.example.com/api/",
    });
    fetchMock.mockResolvedValueOnce(jsonResponse(draftFixture, 200));

    await expect(
      requestPlatform(`/task-drafts/${toPathSegment("draft with/slash")}`),
    ).resolves.toEqual(draftFixture);

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe(
      "https://signaldeck.example.com/api/task-drafts/draft%20with%2Fslash",
    );
  });

  it.each([[undefined, "report.md"], ["访谈附件.txt", "访谈附件.txt"]])("downloads the original bytes with the requested name %s and keeps the URL alive", async (filename, expectedName) => {
    const { downloadPlatformFile } = await loadApiModule();
    const originalCreateObjectUrl = URL.createObjectURL;
    const originalRevokeObjectUrl = URL.revokeObjectURL;
    const createObjectUrlMock = vi.fn((_blob: Blob) => "blob:signaldeck-report");
    const revokeObjectUrlMock = vi.fn();
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        expect(revokeObjectUrlMock).not.toHaveBeenCalled();
        expect(this.download).toBe(expectedName);
      });

    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectUrlMock,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectUrlMock,
    });
    vi.useFakeTimers();
    fetchMock.mockResolvedValueOnce(
      textResponse("Downloaded report", 200, {
        "content-disposition": 'attachment; filename="report.md"',
      }),
    );

    try {
      await expect(downloadPlatformFile("/artifacts/report", { filename })).resolves.toBeUndefined();
      expect(clickSpy).toHaveBeenCalledOnce();
      expect(await createObjectUrlMock.mock.calls[0][0].text()).toBe("Downloaded report");
      expect(revokeObjectUrlMock).not.toHaveBeenCalled();

      await vi.runAllTimersAsync();
      expect(revokeObjectUrlMock).toHaveBeenCalledWith("blob:signaldeck-report");
    } finally {
      vi.useRealTimers();
      Object.defineProperty(URL, "createObjectURL", {
        configurable: true,
        value: originalCreateObjectUrl,
      });
      Object.defineProperty(URL, "revokeObjectURL", {
        configurable: true,
        value: originalRevokeObjectUrl,
      });
    }
  });
});
