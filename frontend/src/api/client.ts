// Relative API calls keep the browser on one origin in local development.
// Deployments that expose the API separately can still provide VITE_API_URL.
const apiUrl = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

export type ApiFetchResult<T> = {
  data: T;
  response: Response;
};

export async function apiFetchWithResponse<T>(
  path: string,
  options: RequestInit & { token?: string } = {}
): Promise<ApiFetchResult<T>> {
  const { token, ...init } = options;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (init.body && typeof init.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${apiUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new ApiError(response.status, detail);
  }
  const data = response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  return { data, response };
}

export async function apiFetch<T>(path: string, options: RequestInit & { token?: string } = {}): Promise<T> {
  const result = await apiFetchWithResponse<T>(path, options);
  return result.data;
}

export async function apiFetchFile(path: string, options: RequestInit & { token?: string } = {}): Promise<Blob> {
  const { token, ...init } = options;
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(`${apiUrl}${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.text().catch(() => response.statusText);
    throw new ApiError(response.status, detail);
  }
  return response.blob();
}
