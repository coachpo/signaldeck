import type {
  ApiErrorDetail,
  ApiErrorDetailValue,
  ApiErrorResponse,
} from "./types/common";

type RequestMethod = "DELETE" | "GET" | "PATCH" | "POST" | "PUT";
export type RequestQueryValue = boolean | number | string | null | undefined;

export interface RequestOptions {
  body?: FormData | object | null;
  headers?: HeadersInit;
  method?: RequestMethod;
  query?: Record<string, RequestQueryValue>;
  signal?: AbortSignal;
}

export interface DownloadFileOptions extends RequestOptions {
  filename?: string;
}

export interface ApiRequestErrorOptions {
  code: string;
  details?: ApiErrorDetail[];
  message: string;
  status: number;
}

export type IdParam = number | string;

const DEFAULT_API_BASE_URL = import.meta.env.DEV
  ? "http://127.0.0.1:8000/api"
  : "/api";
const CONFIGURED_API_BASE_URL = normalizeApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
);
const API_BASE_URL = toVersionedApiBaseUrl(CONFIGURED_API_BASE_URL, "v1");
const PLATFORM_API_BASE_URL = toPlatformApiBaseUrl(CONFIGURED_API_BASE_URL);
const DETAIL_KEY_PATTERN = /^[A-Za-z][A-Za-z0-9_]*$/;
const API_TOKEN_STORAGE_KEY = "signaldeck.apiToken";
const UNSAFE_DETAIL_KEY_PARTS = [
  "apikey",
  "authorization",
  "credential",
  "exception",
  "header",
  "internal",
  "password",
  "secret",
  "stack",
  "token",
  "traceback",
] as const;
const MAX_DETAIL_STRING_LENGTH = 500;

export class ApiRequestError extends Error {
  readonly code: string;
  readonly details: ApiErrorDetail[];
  readonly status: number;

  constructor({ status, code, message, details = [] }: ApiRequestErrorOptions) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function normalizeApiBaseUrl(value: string | undefined): string {
  const normalized = value?.trim();

  if (!normalized) {
    return DEFAULT_API_BASE_URL;
  }

  return normalized.endsWith("/") ? normalized.slice(0, -1) : normalized;
}

export function toPathSegment(value: IdParam): string {
  return encodeURIComponent(String(value));
}

function toPlatformApiBaseUrl(baseUrl: string): string {
  if (/\/api\/v\d+$/.test(baseUrl)) {
    return baseUrl.replace(/\/api\/v\d+$/, "/api");
  }

  if (baseUrl.endsWith("/api")) {
    return baseUrl;
  }

  return `${baseUrl}/api`;
}

function toVersionedApiBaseUrl(baseUrl: string, version: `v${number}`): string {
  return `${toPlatformApiBaseUrl(baseUrl)}/${version}`;
}

function normalizePath(path: string): string {
  return path.startsWith("/") ? path : `/${path}`;
}

function buildApiUrlForBaseUrl(baseUrl: string, path: string): string {
  return `${baseUrl}${normalizePath(path)}`;
}

export function buildApiUrl(path: string): string {
  return buildApiUrlForBaseUrl(API_BASE_URL, path);
}

export function buildPlatformApiUrl(path: string): string {
  return buildApiUrlForBaseUrl(PLATFORM_API_BASE_URL, path);
}

export function toQueryRecord<T extends object>(
  params?: T,
): Record<string, RequestQueryValue> | undefined {
  return params as Record<string, RequestQueryValue> | undefined;
}

function buildQueryString(query?: Record<string, RequestQueryValue>): string {
  if (!query) {
    return "";
  }

  const searchParams = new URLSearchParams();

  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null) {
      continue;
    }

    searchParams.set(key, String(value));
  }

  return searchParams.toString();
}

function readStoredApiToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage.getItem(API_TOKEN_STORAGE_KEY) || null;
  } catch {
    return null;
  }
}

function writeStoredApiToken(token: string): void {
  try {
    window.localStorage.setItem(API_TOKEN_STORAGE_KEY, token);
  } catch {
    return;
  }
}

function applyStoredApiToken(headers: Headers): void {
  const token = readStoredApiToken();

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
}

// ponytail: prompt-based token entry; build a settings page if multi-user ever happens.
function promptForApiToken(): string | null {
  if (typeof window === "undefined" || typeof window.prompt !== "function") {
    return null;
  }

  const token = window.prompt("请输入访问口令以继续使用 SignalDeck")?.trim();
  if (!token) {
    return null;
  }

  writeStoredApiToken(token);
  return token;
}

function buildUrlForBaseUrl(
  baseUrl: string,
  path: string,
  query?: Record<string, RequestQueryValue>,
): string {
  const normalizedPath = normalizePath(path);
  const queryString = buildQueryString(query);

  if (!queryString) {
    return `${baseUrl}${normalizedPath}`;
  }

  return `${baseUrl}${normalizedPath}?${queryString}`;
}

function isSafeDetailKey(key: string): boolean {
  if (!DETAIL_KEY_PATTERN.test(key)) {
    return false;
  }

  const normalizedKey = key.replace(/[^A-Za-z0-9]/g, "").toLowerCase();
  return !UNSAFE_DETAIL_KEY_PARTS.some((part) => normalizedKey.includes(part));
}

type ApiErrorDetailValueResult =
  | { safe: false }
  | { safe: true; value: ApiErrorDetailValue };

function toApiErrorDetailValue(value: unknown): ApiErrorDetailValueResult {
  if (value === null) {
    return { safe: true, value };
  }
  if (typeof value === "boolean") {
    return { safe: true, value };
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? { safe: true, value } : { safe: false };
  }
  if (typeof value === "string") {
    return {
      safe: true,
      value:
        value.length <= MAX_DETAIL_STRING_LENGTH
          ? value
          : `${value.slice(0, MAX_DETAIL_STRING_LENGTH - 3)}...`,
    };
  }

  return { safe: false };
}

function toApiErrorDetail(value: unknown): ApiErrorDetail | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }

  const detail: ApiErrorDetail = {};
  for (const [key, rawValue] of Object.entries(value)) {
    if (!isSafeDetailKey(key)) {
      continue;
    }
    const safeValue = toApiErrorDetailValue(rawValue);
    if (!safeValue.safe) {
      continue;
    }
    detail[key] = safeValue.value;
  }

  return Object.keys(detail).length > 0 ? detail : null;
}

function isApiErrorDetail(
  value: ApiErrorDetail | null,
): value is ApiErrorDetail {
  return value !== null;
}

async function toApiRequestError(response: Response): Promise<ApiRequestError> {
  const defaultMessage = `Request failed with status ${response.status}`;
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const payload = (await response.json()) as Partial<ApiErrorResponse> | null;

    return new ApiRequestError({
      status: response.status,
      code: typeof payload?.code === "string" ? payload.code : "request_failed",
      message:
        typeof payload?.message === "string" ? payload.message : defaultMessage,
      details: Array.isArray(payload?.details)
        ? payload.details.map(toApiErrorDetail).filter(isApiErrorDetail)
        : [],
    });
  }

  const text = await response.text();

  return new ApiRequestError({
    status: response.status,
    code: "request_failed",
    message: text || defaultMessage,
  });
}

function filenameFromContentDisposition(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const encodedFilename = /filename\*=UTF-8''([^;]+)/i.exec(value)?.[1];
  if (encodedFilename) {
    try {
      return decodeURIComponent(encodedFilename);
    } catch {
      return encodedFilename;
    }
  }

  return (
    /filename="([^"]+)"/i.exec(value)?.[1] ??
    /filename=([^;]+)/i.exec(value)?.[1]?.trim() ??
    null
  );
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(href), 0);
}

async function fetchWithBaseUrl(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
  defaultAccept: string,
): Promise<Response> {
  const headers = new Headers(options.headers);
  const method = options.method ?? "GET";
  const url = buildUrlForBaseUrl(baseUrl, path, options.query);
  let body: BodyInit | undefined;

  if (options.body instanceof FormData) {
    body = options.body;
  } else if (options.body !== undefined && options.body !== null) {
    if (!headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    body = JSON.stringify(options.body);
  }

  if (!headers.has("Accept")) {
    headers.set("Accept", defaultAccept);
  }
  applyStoredApiToken(headers);

  let response = await fetch(url, {
    body,
    headers,
    method,
    signal: options.signal,
  });

  if (response.status === 401) {
    const token = promptForApiToken();
    if (token) {
      const retryHeaders = new Headers(headers);
      retryHeaders.set("Authorization", `Bearer ${token}`);
      response = await fetch(url, {
        body,
        headers: retryHeaders,
        method,
        signal: options.signal,
      });
    }
  }

  if (!response.ok) {
    throw await toApiRequestError(response);
  }

  return response;
}

async function requestWithBaseUrl<T>(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await fetchWithBaseUrl(
    baseUrl,
    path,
    options,
    "application/json",
  );

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  const text = await response.text();

  if (!text) {
    return undefined as T;
  }

  return JSON.parse(text) as T;
}

async function requestTextWithBaseUrl(
  baseUrl: string,
  path: string,
  options: RequestOptions = {},
): Promise<string> {
  const response = await fetchWithBaseUrl(
    baseUrl,
    path,
    options,
    "text/plain, application/yaml, */*",
  );

  return response.text();
}

async function downloadFileWithBaseUrl(
  baseUrl: string,
  path: string,
  options: DownloadFileOptions = {},
): Promise<void> {
  const response = await fetchWithBaseUrl(baseUrl, path, options, "*/*");
  const blob = await response.blob();
  const filename =
    options.filename ??
    filenameFromContentDisposition(response.headers.get("content-disposition")) ??
    "download";

  triggerBrowserDownload(blob, filename);
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  return requestWithBaseUrl<T>(API_BASE_URL, path, options);
}

export async function requestPlatform<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  return requestWithBaseUrl<T>(PLATFORM_API_BASE_URL, path, options);
}

export function requestPlatformText(
  path: string,
  options: RequestOptions = {},
): Promise<string> {
  return requestTextWithBaseUrl(PLATFORM_API_BASE_URL, path, options);
}

export function downloadFile(
  path: string,
  options: DownloadFileOptions = {},
): Promise<void> {
  return downloadFileWithBaseUrl(API_BASE_URL, path, options);
}

export function downloadPlatformFile(
  path: string,
  options: DownloadFileOptions = {},
): Promise<void> {
  return downloadFileWithBaseUrl(PLATFORM_API_BASE_URL, path, options);
}
