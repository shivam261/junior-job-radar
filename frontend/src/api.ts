export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, {
    ...init,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": decodeURIComponent(
        document.cookie
          .split("; ")
          .find((c) => c.startsWith("launchpad_csrf="))
          ?.split("=")[1] || "",
      ),
      ...init?.headers,
    },
  });
  if (response.status === 401 && !path.startsWith("/auth/")) {
    window.dispatchEvent(new Event("session-expired"));
  }
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
