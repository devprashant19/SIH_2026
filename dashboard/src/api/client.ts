/** Minimal typed fetch wrapper. All calls are same-origin under /api/v1. */

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `API error ${status}`);
  }
}

type Params = Record<string, string | number | boolean | null | undefined | (string | number)[]>;

function buildUrl(path: string, params?: Params): string {
  const url = new URL(API_BASE + path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v == null || v === "") continue;
      if (Array.isArray(v)) v.forEach((item) => url.searchParams.append(k, String(item)));
      else url.searchParams.set(k, String(v));
    }
  }
  return url.pathname + url.search;
}

export async function api<T>(
  path: string,
  init: RequestInit & { params?: Params; json?: unknown } = {},
): Promise<T> {
  const { params, json, headers, ...rest } = init;
  const res = await fetch(buildUrl(path, params), {
    ...rest,
    headers: {
      Accept: "application/json",
      ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers ?? {}),
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    let detail: unknown = await res.text();
    try {
      detail = JSON.parse(detail as string)?.detail ?? detail;
    } catch {
      /* keep text */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Binary downloads (PDF/CSV). Returns a Blob the caller turns into an object URL. */
export async function apiBlob(path: string, params?: Params): Promise<Blob> {
  const res = await fetch(buildUrl(path, params));
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.blob();
}
