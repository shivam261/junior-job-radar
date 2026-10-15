export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = "Something went wrong. Please try again.";
    try {
      const detail = (await response.json()).detail;
      message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail
                .map((entry: { msg?: string }) => entry.msg || "Invalid value")
                .join(" ")
            : message;
    } catch {
      /* plain response */
    }
    throw new Error(
      typeof message === "string"
        ? message
        : "Invalid request. Please check your filters.",
    );
  }
  return response.json();
}
