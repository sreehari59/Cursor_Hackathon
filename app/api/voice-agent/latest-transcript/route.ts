export async function GET() {
  const backendBase = (process.env.BACKEND_API_BASE_URL || "http://localhost:5000/api").replace(/\/$/, "")

  const backendResponse = await fetch(`${backendBase}/voice-agent/latest-transcript`, {
    method: "GET",
    cache: "no-store",
  })

  const responseText = await backendResponse.text()
  return new Response(responseText, {
    status: backendResponse.status,
    headers: { "Content-Type": backendResponse.headers.get("Content-Type") || "application/json" },
  })
}
