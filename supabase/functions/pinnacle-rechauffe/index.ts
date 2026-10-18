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

const REMPLIS = new Set(["MISS", "EXPIRED", "DYNAMIC"]);

export type VueMarche = { path: string; cache: string; age: number | null; remplir: boolean };

function ageEntete(r: Response): number | null {
  const brut = r.headers.get("Age");
  if (brut == null || brut.trim() === "") return null;
  const n = Number(brut);
  return Number.isInteger(n) && n >= 0 ? n : null;
}

async function lire(url: string, path: string, key: string, fetchImpl: typeof fetch): Promise<VueMarche> {
  const r = await fetchImpl(url, {
    headers: entetes(key), redirect: "manual", signal: AbortSignal.timeout(20_000),
  });
  const cache = (r.headers.get("cf-cache-status") || "").toUpperCase();
  const age = ageEntete(r);
  await r.arrayBuffer();
  return { path, cache: cache || String(r.status), age, remplir: r.status === 200 && REMPLIS.has(cache) };
}

export function choisirMarche(vues: VueMarche[], repli: string) {
  const neuf = vues.find((v) => v.remplir);
  if (neuf) return { markets: neuf.path, cache: neuf.cache, fresh: true, age_s: neuf.age };
  let meilleur: VueMarche | undefined;
  for (const v of vues) {
    if (v.age == null) continue;
    if (!meilleur || meilleur.age == null || v.age < meilleur.age) meilleur = v;
  }
  if (meilleur && meilleur.age != null) {
    return { markets: meilleur.path, cache: meilleur.cache, fresh: false, age_s: meilleur.age };
  }
  const premier = vues[0];
  return { markets: premier?.path ?? repli, cache: premier?.cache ?? "ECHEC", fresh: false, age_s: null };
}

export async function rechauffer(sports: number[], key: string, epochMs: number, fetchImpl: typeof fetch = fetch) {
  const ordre = ordreOrthographes(epochMs);
  const t = new Date(epochMs).toISOString();
  const sortie: Record<string, { matchups: string; markets: string; t: string; cache: string; fresh: boolean; age_s: number | null }> = {};
  let i = 0;
  async function un() {
    while (i < sports.length) {
      const sid = sports[i++];
      const matchups = `/sports/${sid}/matchups?withSpecials=true&_=${crypto.randomUUID().replaceAll("-", "")}`;
      const repli = `/sports/${sid}/markets/straight${ordre[0]}`;
      const vues: VueMarche[] = [];
      try {
        await lire(BASE + matchups, matchups, key, fetchImpl);
        for (const q of ordre) {
          const path = `/sports/${sid}/markets/straight${q}`;
          const vue = await lire(BASE + path, path, key, fetchImpl);
          vues.push(vue);
          if (vue.remplir) break;
        }
      } catch { /* les vues déjà lues suffisent à choisir */ }
      sortie[String(sid)] = { matchups, t, ...choisirMarche(vues, repli) };
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
