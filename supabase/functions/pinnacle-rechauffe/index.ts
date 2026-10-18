// Réchauffe le cache Cloudflare de l'API guest Pinnacle depuis Paris.
// verify_jwt est désactivé : seul l'en-tête x-secret (RECHAUFFEUR_SECRET) autorise l'appel.
//
// Leçon du 18/10/2026 : les URL avec cache-buster (« &_=uuid ») et la rotation de cinq orthographes
// faisaient répondre Pinnacle en 204/403 et la collecte tombait à 0 cote. On lit désormais
// exactement les deux URL que la collecte Python lit, lentement, et on s'arrête au premier refus.
const BASE = "https://guest.api.arcadia.pinnacle.com/0.1";
export const CONCURRENCE = 2;
export const PAUSE_MS = 300;

export function cheminMatchups(sid: number): string {
  return `/sports/${sid}/matchups?withSpecials=true`;
}

export function cheminMarches(sid: number): string {
  return `/sports/${sid}/markets/straight?primaryOnly=false&withSpecials=true`;
}

// Sonde (un seul sport) : une orthographe alternative des prix, qui change toutes les 5 minutes.
// Chacune revient toutes les 20 minutes, plus que la durée du cache (~15 min) : la lecture de Paris
// va donc chercher des cotes neuves. La collecte relit la même URL depuis GitHub pour mesurer si
// elle profite de ce cache. Rien n'est utilisé pour les données tant que ce n'est pas prouvé.
export const SPORT_SONDE = 29;
export const ORTHO_SONDE = ["", "?primaryOnly=false", "?withSpecials=true", "?withSpecials=true&primaryOnly=false"];

export function cheminSonde(sid: number, epochMs: number): string {
  const i = Math.floor(epochMs / 300_000) % ORTHO_SONDE.length;
  return `/sports/${sid}/markets/straight${ORTHO_SONDE[i]}`;
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
const REFUS = new Set([401, 403, 429]);

export type Lecture = {
  path: string; status: number; cache: string; age: number | null; extrait: string | null; octets: number;
};

function ageEntete(r: Response): number | null {
  const brut = r.headers.get("Age");
  if (brut == null || brut.trim() === "") return null;
  const n = Number(brut);
  return Number.isInteger(n) && n >= 0 ? n : null;
}

// Extrait court du corps d'une réponse refusée (page Cloudflare, message d'erreur…), sans la clé.
export function extraire(texte: string, key: string): string {
  let t = texte.replace(/\s+/g, " ").trim();
  if (key) t = t.split(key).join("***");
  return t.slice(0, 160);
}

async function lire(path: string, key: string, fetchImpl: typeof fetch): Promise<Lecture> {
  try {
    const r = await fetchImpl(BASE + path, {
      headers: entetes(key), redirect: "manual", signal: AbortSignal.timeout(20_000),
    });
    const cache = (r.headers.get("cf-cache-status") || "").toUpperCase();
    const age = ageEntete(r);
    const texte = await r.text();
    return {
      path, status: r.status, cache, age, extrait: r.status === 200 ? null : extraire(texte, key),
      octets: texte.length,
    };
  } catch (e) {
    return { path, status: 0, cache: "", age: null, extrait: extraire(String(e), key), octets: 0 };
  }
}

export type Plan = {
  matchups: string; markets: string; t: string; cache: string; fresh: boolean; age_s: number | null;
  statuts: { matchups: number | null; markets: number | null }; extrait: string | null;
  sonde?: { path: string; status: number; cache: string; age: number | null; octets: number; t: string };
};

export function planDepuis(sid: number, t: string, mu: Lecture | null, mk: Lecture | null): Plan {
  const fresh = mk != null && mk.status === 200 && REMPLIS.has(mk.cache);
  const refus = [mu, mk].find((l) => l != null && l.status !== 200 && l.status !== 204);
  return {
    matchups: cheminMatchups(sid),
    markets: cheminMarches(sid),
    t,
    cache: mk ? (mk.cache || String(mk.status)) : (mu ? `MATCHUPS_${mu.status}` : "SAUTE"),
    fresh,
    age_s: mk && mk.status === 200 ? mk.age : null,
    statuts: { matchups: mu?.status ?? null, markets: mk?.status ?? null },
    extrait: refus?.extrait ?? null,
  };
}

const dormir = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function rechauffer(
  sports: number[], key: string, epochMs: number,
  fetchImpl: typeof fetch = fetch, pause: (ms: number) => Promise<void> = dormir,
) {
  const t = new Date(epochMs).toISOString();
  const sortie: Record<string, Plan> = {};
  let i = 0;
  let bloque = false;               // disjoncteur : au premier refus, on n'insiste pas
  async function un() {
    while (i < sports.length) {
      const sid = sports[i++];
      if (bloque) {
        sortie[String(sid)] = planDepuis(sid, t, null, null);
        continue;
      }
      const mu = await lire(cheminMatchups(sid), key, fetchImpl);
      let mk: Lecture | null = null;
      if (REFUS.has(mu.status)) bloque = true;
      else if (mu.status === 200) {
        await pause(PAUSE_MS);
        mk = await lire(cheminMarches(sid), key, fetchImpl);
        if (REFUS.has(mk.status)) bloque = true;
      }
      const plan = planDepuis(sid, t, mu, mk);
      sortie[String(sid)] = plan;
      console.log(JSON.stringify({ sport: sid, statuts: plan.statuts, cache: plan.cache, age_s: plan.age_s,
        extrait: plan.extrait }));
      await pause(PAUSE_MS);
    }
  }
  await Promise.all(Array.from({ length: Math.min(CONCURRENCE, sports.length) }, () => un()));
  const plan = sortie[String(SPORT_SONDE)];
  if (!bloque && plan && plan.statuts.markets === 200) {
    await pause(PAUSE_MS);
    const debut = new Date().toISOString();
    const l = await lire(cheminSonde(SPORT_SONDE, epochMs), key, fetchImpl);
    plan.sonde = { path: l.path, status: l.status, cache: l.cache, age: l.age, octets: l.octets, t: debut };
    console.log(JSON.stringify({ sonde: plan.sonde }));
  }
  return sortie;
}

export async function handler(req: Request, fetchImpl: typeof fetch = fetch, maintenant = Date.now(),
  pause: (ms: number) => Promise<void> = dormir): Promise<Response> {
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
  return Response.json(await rechauffer(sports, key, maintenant, fetchImpl, pause));
}

if (import.meta.main) Deno.serve((req) => handler(req));
