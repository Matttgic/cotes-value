import {
  cheminMarches, cheminMatchups, cheminSonde, extraire, handler, rechauffer, secretIdentique,
} from "../pinnacle-rechauffe/index.ts";

function egal(obtenu: unknown, attendu: unknown, message: string) {
  const a = JSON.stringify(obtenu);
  const b = JSON.stringify(attendu);
  if (a !== b) throw new Error(`${message}\nobtenu ${a}\nattendu ${b}`);
}

const sansPause = async (_ms: number) => {};

Deno.test("chemins identiques à la collecte Python, sans cache-buster", () => {
  egal(cheminMatchups(29), "/sports/29/matchups?withSpecials=true", "matchups");
  egal(cheminMarches(29), "/sports/29/markets/straight?primaryOnly=false&withSpecials=true", "marchés");
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
  }), fetchImpl, 0, sansPause);
  egal(res.status, 401, "statut");
  egal(appels, 0, "aucun appel");
  if ((await res.text()).includes("cle-guest")) throw new Error("clé reflétée");
});

Deno.test("MISS : deux lectures par sport, en-têtes du site, corps et clé jamais renvoyés", async () => {
  Deno.env.set("RECHAUFFEUR_SECRET", "attendu");
  const urls: string[] = [];
  const cle = "cle-guest-ne-pas-renvoyer";
  const fetchImpl: typeof fetch = async (input, init) => {
    urls.push(String(input).split("/0.1")[1]);
    const entete = new Headers(init?.headers);
    if (entete.get("X-API-Key") !== cle) throw new Error("clé absente de l'en-tête");
    if (entete.get("Referer") !== "https://www.pinnacle.com/") throw new Error("referer");
    return new Response(JSON.stringify([{ fuite: cle, cote: 1.5 }]), {
      status: 200, headers: { "cf-cache-status": "MISS" },
    });
  };
  const res = await handler(new Request("https://exemple/fn", {
    method: "POST",
    headers: { "x-secret": "attendu" },
    body: JSON.stringify({ sports: [29, "non", 0], key: `  ${cle}  ` }),
  }), fetchImpl, 0, sansPause);
  egal(res.status, 200, "statut");
  const corps = await res.json();
  egal(urls, [cheminMatchups(29), cheminMarches(29), cheminSonde(29, 0)], "deux URL fixes puis la sonde");
  egal(corps["29"].sonde.cache, "MISS", "sonde notée");
  egal(corps["29"].fresh, true, "renouvelé");
  egal(corps["29"].statuts, { matchups: 200, markets: 200 }, "statuts");
  if (JSON.stringify(corps).includes(cle) || JSON.stringify(corps).includes("fuite")) {
    throw new Error("donnée ou clé renvoyée");
  }
});

Deno.test("403 : disjoncteur, les sports suivants ne sont pas appelés, extrait sans clé", async () => {
  const vus: string[] = [];
  const fetchImpl: typeof fetch = async (input) => {
    const url = String(input);
    vus.push(url);
    if (url.includes("/sports/4/")) {
      return new Response("<html>Just a moment... k-secret</html>", { status: 403 });
    }
    return new Response("[]", { status: 200, headers: { "cf-cache-status": "HIT", Age: "30" } });
  };
  // Concurrence 2 : 4 et 29 partent ensemble ; 33 et 12 doivent être sautés.
  const data = await rechauffer([4, 29, 33, 12], "k-secret", 0, fetchImpl, sansPause);
  egal(data["4"].statuts, { matchups: 403, markets: null }, "refus noté");
  egal(data["4"].extrait, "<html>Just a moment... ***</html>", "extrait masqué");
  egal(data["12"].cache, "SAUTE", "sport suivant sauté");
  if (vus.some((u) => u.includes("/sports/12/"))) throw new Error("appel après refus");
  egal(data["29"].fresh, false, "HIT n'est pas un renouvellement");
});

Deno.test("204 sur matchups : pas de lecture des prix, pas de disjoncteur", async () => {
  const vus: string[] = [];
  const fetchImpl: typeof fetch = async (input) => {
    const url = String(input);
    vus.push(url);
    if (url.includes("/sports/29/")) return new Response(null, { status: 204 });
    return new Response("[]", { status: 200, headers: { "cf-cache-status": "EXPIRED" } });
  };
  const data = await rechauffer([29, 4], "k", 0, fetchImpl, sansPause);
  egal(data["29"].statuts, { matchups: 204, markets: null }, "204");
  egal(data["4"].fresh, true, "le sport suivant continue");
  egal(vus.filter((u) => u.includes("/sports/29/markets")).length, 0, "pas de prix après 204");
});

Deno.test("pause entre les lectures", async () => {
  const pauses: number[] = [];
  const fetchImpl: typeof fetch = async () =>
    new Response("[]", { status: 200, headers: { "cf-cache-status": "HIT" } });
  await rechauffer([29], "k", 0, fetchImpl, async (ms) => { pauses.push(ms); });
  egal(pauses, [300, 300, 300], "pause avant les prix, après le sport, avant la sonde");
});

Deno.test("extraire : compacte et coupe à 160 caractères", () => {
  egal(extraire("a\n  b", ""), "a b", "espaces");
  egal(extraire("x".repeat(500), "").length, 160, "longueur");
});

Deno.test("sonde : orthographe tournante toutes les 5 minutes, jamais l'URL fixe", () => {
  egal(cheminSonde(29, 0), "/sports/29/markets/straight", "cycle 0");
  egal(cheminSonde(29, 300_000), "/sports/29/markets/straight?primaryOnly=false", "cycle 1");
  egal(cheminSonde(29, 1_200_000), "/sports/29/markets/straight", "revient après 20 min");
  for (let t = 0; t < 1_200_000; t += 300_000) {
    if (cheminSonde(29, t) === cheminMarches(29)) throw new Error("la sonde ne doit pas toucher l'URL fixe");
  }
});

Deno.test("sonde absente si le sport 29 n'est pas demandé ou si un refus a eu lieu", async () => {
  const ok: typeof fetch = async () => new Response("[]", { status: 200, headers: { "cf-cache-status": "HIT" } });
  const sans = await rechauffer([4], "k", 0, ok, sansPause);
  egal(sans["4"].sonde, undefined, "pas de sonde hors sport 29");
  const refus: typeof fetch = async (input) =>
    String(input).includes("/sports/4/") ? new Response("non", { status: 403 })
      : new Response("[]", { status: 200, headers: { "cf-cache-status": "HIT" } });
  const bloque = await rechauffer([29, 4], "k", 0, refus, sansPause);
  egal(bloque["29"].sonde, undefined, "pas de sonde après un refus");
});
