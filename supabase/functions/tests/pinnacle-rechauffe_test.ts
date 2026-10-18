import { handler, ordreOrthographes, rechauffer, secretIdentique } from "../pinnacle-rechauffe/index.ts";

function egal(obtenu: unknown, attendu: unknown, message: string) {
  const a = JSON.stringify(obtenu);
  const b = JSON.stringify(attendu);
  if (a !== b) throw new Error(`${message}\nobtenu ${a}\nattendu ${b}`);
}

Deno.test("rotation des cinq orthographes toutes les 5 minutes", () => {
  const cinq = [
    "",
    "?primaryOnly=false",
    "?withSpecials=true",
    "?primaryOnly=false&withSpecials=true",
    "?withSpecials=true&primaryOnly=false",
  ];
  egal(ordreOrthographes(0), cinq, "cycle 0");
  egal(ordreOrthographes(300_000), cinq.slice(1).concat(cinq.slice(0, 1)), "cycle 1");
  egal(ordreOrthographes(1_200_000), cinq.slice(4).concat(cinq.slice(0, 4)), "cycle 4");
  egal(ordreOrthographes(1_500_000), cinq, "cycle 5 revient au début");
});

Deno.test("secret : comparaison stricte, longueurs différentes refusées", () => {
  if (!secretIdentique("attendu", "attendu")) throw new Error("égal");
  if (secretIdentique("autre", "attendu")) throw new Error("différent");
  if (secretIdentique("attendu-long", "attendu")) throw new Error("préfixe");
  if (secretIdentique("", "") || secretIdentique("x", "")) throw new Error("vide");
});

Deno.test("x-secret incorrect : 401 sans appel Pinnacle", async () => {
  Deno.env.set("RECHAUFFEUR_SECRET", "attendu");
  let appels = 0;
  const fetchImpl: typeof fetch = async () => {
    appels += 1;
    return new Response("[]", { status: 200 });
  };
  const res = await handler(new Request("https://exemple/fn", {
    method: "POST",
    headers: { "x-secret": "mauvais", "content-type": "application/json" },
    body: JSON.stringify({ sports: [29], key: "cle-guest" }),
  }), fetchImpl, 0);
  egal(res.status, 401, "statut");
  egal(appels, 0, "aucun appel");
  if ((await res.text()).includes("cle-guest")) throw new Error("clé reflétée");
});

Deno.test("HIT puis MISS : la deuxième orthographe est retenue, le corps n'est pas renvoyé", async () => {
  Deno.env.set("RECHAUFFEUR_SECRET", "attendu");
  const urls: string[] = [];
  const cle = "cle-guest-ne-pas-renvoyer";
  const fetchImpl: typeof fetch = async (input, init) => {
    const url = String(input);
    urls.push(url);
    const entete = new Headers(init?.headers);
    if (entete.get("X-API-Key") !== cle) throw new Error("clé absente de l'en-tête");
    if (entete.get("Referer") !== "https://www.pinnacle.com/") throw new Error("referer");
    if (entete.get("Origin") !== "https://www.pinnacle.com") throw new Error("origin");
    if (entete.get("User-Agent") !== "Mozilla/5.0 (cotes-value)") throw new Error("ua");
    const hit = url.includes("/markets/straight") && !url.includes("?");
    return new Response(JSON.stringify([{ fuite: cle, cote: 1.5 }]), {
      status: 200,
      headers: { "cf-cache-status": hit ? "HIT" : "MISS" },
    });
  };
  const res = await handler(new Request("https://exemple/fn", {
    method: "POST",
    headers: { "x-secret": "attendu" },
    body: JSON.stringify({ sports: [29, "non", 0], key: `  ${cle}  ` }),
  }), fetchImpl, 0);
  egal(res.status, 200, "statut");
  const corps = await res.json();
  const plan = corps["29"];
  egal(plan.markets, "/sports/29/markets/straight?primaryOnly=false", "orthographe suivante");
  egal(plan.cache, "MISS", "cache");
  egal(plan.fresh, true, "renouvelé");
  if (!plan.matchups.startsWith("/sports/29/matchups?withSpecials=true&_=")) throw new Error(plan.matchups);
  if (plan.matchups.includes("cle-guest")) throw new Error("clé dans le chemin");
  if (JSON.stringify(corps).includes(cle) || JSON.stringify(corps).includes("fuite")) {
    throw new Error("donnée ou clé renvoyée");
  }
  const marches = urls.filter((u) => u.includes("/markets/straight"));
  egal(marches.map((u) => u.split("/0.1")[1]), [
    "/sports/29/markets/straight",
    "/sports/29/markets/straight?primaryOnly=false",
  ], "arrêt au MISS");
});

Deno.test("rechauffer direct : EXPIRED arrête, les sports avancent en parallèle", async () => {
  const vus: string[] = [];
  const fetchImpl: typeof fetch = async (input) => {
    const url = String(input);
    vus.push(url);
    const expired = url.includes("withSpecials=true&primaryOnly=false");
    return new Response("[]", { status: 200, headers: { "cf-cache-status": expired ? "EXPIRED" : "HIT" } });
  };
  const data = await rechauffer([4, 29], "k", 1_200_000, fetchImpl);
  egal(data["4"].markets, "/sports/4/markets/straight?withSpecials=true&primaryOnly=false", "première du cycle 4");
  egal(data["29"].cache, "EXPIRED", "statut");
  egal(data["4"].fresh, true, "renouvelé");
  if (vus.filter((u) => u.includes("/markets/")).length !== 2) throw new Error("trop d'orthographes");
});

Deno.test("cinq HIT : plus petit Age connu, sans le faire passer pour un renouvellement", async () => {
  const fetchImpl: typeof fetch = async (input) => {
    const url = String(input);
    const path = url.split("/0.1")[1] ?? url;
    let age: string | null = null;
    if (path.includes("/sports/29/")) {
      if (path.endsWith("/markets/straight")) age = "294";
      else if (path.endsWith("?primaryOnly=false")) age = null;
      else if (path.endsWith("?withSpecials=true")) age = "287";
      else if (path.includes("primaryOnly=false&withSpecials=true")) age = "400";
      else if (path.includes("withSpecials=true&primaryOnly=false")) age = "290";
    }
    const headers = new Headers({ "cf-cache-status": "HIT" });
    if (age != null) headers.set("Age", age);
    return new Response("[]", { status: 200, headers });
  };
  const data = await rechauffer([29, 4], "k", 0, fetchImpl);
  egal(data["29"].markets, "/sports/29/markets/straight?withSpecials=true", "plus petit Age");
  egal(data["29"].fresh, false, "pas un renouvellement");
  egal(data["29"].age_s, 287, "âge retenu");
  egal(data["29"].cache, "HIT", "statut");
  egal(data["4"].fresh, false, "sans Age");
  egal(data["4"].age_s, null, "âge inconnu");
  egal(data["4"].markets, "/sports/4/markets/straight", "première orthographe si tout est inconnu");
});
