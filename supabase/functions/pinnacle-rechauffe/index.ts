// Réchauffe le cache Cloudflare de l'API guest Pinnacle depuis Paris.
// verify_jwt est désactivé : seul l'en-tête x-secret (RECHAUFFEUR_SECRET) autorise l'appel.
const BASE = "https://guest.api.arcadia.pinnacle.com/0.1";
const ORTHO = [
  "",
  "?primaryOnly=false",
  "?withSpecials=true",
  "?primaryOnly=false&withSpecials=true",
  "?withSpecials=true&primaryOnly=false",
];

export function ordreOrthographes(epochMs: number): string[] {
  const i = Math.floor(epochMs / 1000 / 300) % ORTHO.length;
  return ORTHO.slice(i).concat(ORTHO.slice(0, i));
}

export function secretIdentique(fourni: string, attendu: string): boolean {
  const a = new TextEncoder().encode(fourni);
  const b = new TextEncoder().encode(attendu);
  let diff = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return diff === 0 && attendu.length > 0;
}

function entetes(key: string): HeadersInit {
  return {
    "User-Agent": "Mozilla/5.0 (cotes-value)",
    Accept: "application/json",
    Referer: "https://www.pinnacle.com/",
    Origin: "https://www.pinnacle.com",
    "X-API-Key": key,
  };
}

async function lire(url: string, key: string, fetchImpl: typeof fetch) {
  const r = await fetchImpl(url, {
    headers: entetes(key), redirect: "manual", signal: AbortSignal.timeout(20_000),
  });
  const cache = (r.headers.get("cf-cache-status") || "").toUpperCase();
  await r.arrayBuffer();
  return { cache: cache || String(r.status), stop: r.status === 200 && cache !== "HIT" };
}

export async function rechauffer(sports: number[], key: string, epochMs: number, fetchImpl: typeof fetch = fetch) {
  const ordre = ordreOrthographes(epochMs);
  const t = new Date(epochMs).toISOString();
  const sortie: Record<string, { matchups: string; markets: string; t: string; cache: string }> = {};
  let i = 0;
  async function un() {
    while (i < sports.length) {
      const sid = sports[i++];
      const matchups = `/sports/${sid}/matchups?withSpecials=true&_=${crypto.randomUUID().replaceAll("-", "")}`;
      let markets = `/sports/${sid}/markets/straight${ordre[0]}`;
      let cache = "ECHEC";
      try {
        await lire(BASE + matchups, key, fetchImpl);
        for (const q of ordre) {
          markets = `/sports/${sid}/markets/straight${q}`;
          const res = await lire(BASE + markets, key, fetchImpl);
          cache = res.cache;
          if (res.stop) break;
        }
      } catch { cache = "ECHEC"; }
      sortie[String(sid)] = { matchups, markets, t, cache };
    }
  }
  await Promise.all(Array.from({ length: Math.min(4, sports.length) }, () => un()));
  return sortie;
}

export async function handler(req: Request, fetchImpl: typeof fetch = fetch, maintenant = Date.now()): Promise<Response> {
  if (req.method !== "POST") return new Response("methode", { status: 405 });
  const attendu = Deno.env.get("RECHAUFFEUR_SECRET") ?? "";
  if (!secretIdentique(req.headers.get("x-secret") ?? "", attendu)) {
    return new Response("non autorise", { status: 401 });
  }
  let corps: { sports?: unknown; key?: unknown };
  try { corps = await req.json(); } catch { return new Response("corps", { status: 400 }); }
  const key = typeof corps?.key === "string" ? corps.key.trim() : "";
  const sports = Array.isArray(corps?.sports)
    ? corps.sports.filter((s): s is number => Number.isInteger(s) && (s as number) > 0).slice(0, 40)
    : [];
  if (!key || sports.length === 0) return new Response("corps", { status: 400 });
  return Response.json(await rechauffer(sports, key, maintenant, fetchImpl));
}

if (import.meta.main) Deno.serve((req) => handler(req));
