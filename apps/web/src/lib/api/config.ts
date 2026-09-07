export function getApiBaseUrl(
  configured = process.env.NEXT_PUBLIC_API_BASE_URL,
  environment = process.env.NODE_ENV,
  localHostname =
    typeof globalThis.location === "undefined"
      ? "localhost"
      : globalThis.location.hostname,
): string {
  const candidate = configured?.trim();
  if (!candidate) {
    if (environment === "production") {
      throw new Error("NEXT_PUBLIC_API_BASE_URL is required in production");
    }
    return `http://${localHostname}:8010`;
  }

  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL");
  }
  if (!(["http:", "https:"] as string[]).includes(parsed.protocol)) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL");
  }
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must not contain credentials or parameters");
  }
  if (environment === "production" && parsed.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_API_BASE_URL must use HTTPS in production");
  }
  return parsed.toString().replace(/\/$/, "");
}
