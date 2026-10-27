export class ApiError extends Error {
  constructor(message: string) {
    super(message);
  }
}

function base() {
  if (typeof window === "undefined") return process.env.API_URL || "http://127.0.0.1:8000";
  return "";
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base()}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(message);
  }
  return response.json();
}
