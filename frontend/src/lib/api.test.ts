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
  const apiClient = await import("./api-client");
  return {
    ...apiClient,
    listTemplates: () => apiClient.request("/templates"),
    createTemplate: (body: object) => apiClient.request("/templates", { method: "POST", body }),
    getTemplate: (id: string) => apiClient.request(`/templates/${apiClient.toPathSegment(id)}`),
    listModelConnections: () => apiClient.requestPlatform("/resources"),
  };
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

const templateFixture = {
  id: 1,
  name: "Daily summary",
  content: "Market summary",
  createdAt: "2024-03-15T12:00:00Z",
  updatedAt: "2024-03-15T12:00:00Z",
};

const templateInput = {
  name: "Daily summary",
  content: "Market summary",
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
  it("sends a successful GET request for listTemplates", async () => {
    const { listTemplates } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse([templateFixture], 200));

    await expect(listTemplates()).resolves.toEqual([templateFixture]);

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe("http://127.0.0.1:8000/api/v1/templates");
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

  it("sends a successful POST request for createTemplate", async () => {
    const { createTemplate } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(jsonResponse(templateFixture, 201));

    await expect(createTemplate(templateInput)).resolves.toEqual(
      templateFixture,
    );

    const { init, url } = getLastFetchCall(fetchMock);
    expect(url).toBe("http://127.0.0.1:8000/api/v1/templates");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify(templateInput));
    expect(new Headers(init?.headers).get("Accept")).toBe("application/json");
    expect(new Headers(init?.headers).get("Content-Type")).toBe(
      "application/json",
    );
  });

  it("preserves status, code, message, and validation details for 422 responses", async () => {
    const { ApiRequestError, createTemplate } = await loadApiModule();
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
      await createTemplate(templateInput);
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
    const { ApiRequestError, listTemplates } = await loadApiModule();
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
      await listTemplates();
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
    const { ApiRequestError, listTemplates } = await loadApiModule();
    fetchMock.mockResolvedValueOnce(textResponse("Internal Server Error", 500));

    let error: unknown;
    try {
      await listTemplates();
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

  it("derives v1 and platform URLs from a configured versioned base", async () => {
    const { buildApiUrl, buildPlatformApiUrl } = await loadApiModule({
      baseUrl: "https://signaldeck.example.com/api/v2/",
    });

    expect(buildApiUrl("/templates")).toBe(
      "https://signaldeck.example.com/api/v1/templates",
    );
    expect(buildPlatformApiUrl("/workflow-packages")).toBe(
      "https://signaldeck.example.com/api/workflow-packages",
    );
  });

  it("routes platform modules through the unversioned api base", async () => {
    const { listModelConnections } = await loadApiModule({
      baseUrl: "https://signaldeck.example.com/api/v1/",
    });
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [] }, 200));

    await expect(listModelConnections()).resolves.toEqual({ items: [] });

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe("https://signaldeck.example.com/api/resources");
  });

  it("encodes v1 path segments against the derived base URL", async () => {
    const { getTemplate } = await loadApiModule({
      baseUrl: "https://signaldeck.example.com/api/",
    });
    fetchMock.mockResolvedValueOnce(
      jsonResponse(templateFixture, 200),
    );

    await expect(getTemplate("template with/slash")).resolves.toEqual(
      templateFixture,
    );

    const { url } = getLastFetchCall(fetchMock);
    expect(url).toBe(
      "https://signaldeck.example.com/api/v1/templates/template%20with%2Fslash",
    );
  });

  it.each([[undefined, "report.md"], ["访谈附件.txt", "访谈附件.txt"]])("downloads the original bytes with the requested name %s and keeps the URL alive", async (filename, expectedName) => {
    const { downloadFile } = await loadApiModule();
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
      await expect(downloadFile("/reports/report/download", { filename })).resolves.toBeUndefined();
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

  it("defaults to same-origin /api/v1 outside dev when the env base is empty", async () => {
    const { buildApiUrl, buildPlatformApiUrl } = await loadApiModule({
      dev: false,
    });

    expect(buildApiUrl("/templates")).toBe("/api/v1/templates");
    expect(buildPlatformApiUrl("/reports")).toBe("/api/reports");
  });

  it("keeps explicit VITE_API_BASE_URL behavior unchanged", async () => {
    const { buildApiUrl, buildPlatformApiUrl } = await loadApiModule({
      baseUrl: "https://signaldeck.example.com/root/",
      dev: false,
    });

    expect(buildApiUrl("/templates")).toBe(
      "https://signaldeck.example.com/root/api/v1/templates",
    );
    expect(buildPlatformApiUrl("/reports")).toBe(
      "https://signaldeck.example.com/root/api/reports",
    );
  });
});
