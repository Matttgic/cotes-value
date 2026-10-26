import sys
from playwright.sync_api import sync_playwright
D='/workspace/design/interface-da/'
def prep(pg):
    pg.wait_for_load_state('networkidle'); pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(600)
    return pg.evaluate("[...document.fonts].filter(f=>f.status=='loaded').map(f=>f.family).join('|')"), pg.evaluate("[document.documentElement.scrollWidth,document.documentElement.scrollHeight]")
def top(pg,sel): return pg.evaluate(f"document.querySelector('{sel}').getBoundingClientRect().top+scrollY")
DESK=dict(viewport={'width':1440,'height':900},device_scale_factor=2)
MOB=dict(viewport={'width':390,'height':844},device_scale_factor=2,is_mobile=True,has_touch=True)
plan=[('desktop',DESK,[('accueil.html',None,0),('accueil.html','aside .card:nth-child(3)',-24),('strategies.html',None,0),('strategies.html','main > h3',-24)]),
      ('mobile',MOB,[('accueil.html',None,0),('accueil.html','.value:nth-of-type(3)',-12),('strategies.html',None,0)])]
with sync_playwright() as p:
    b=p.chromium.launch()
    for nom,ctx,ecrans in plan:
        c=b.new_context(**ctx)
        for f in ['accueil.html','strategies.html']:
            pg=c.new_page(); pg.goto('file://'+D+f); print(nom,f,prep(pg)); pg.screenshot(path=f'/tmp/full-{nom}-{f[:-5]}.png',full_page=True); pg.close()
        for i,(f,sel,off) in enumerate(ecrans,1):
            pg=c.new_page(); pg.goto('file://'+D+f); prep(pg)
            if sel:
                y=top(pg,sel)+off; pg.evaluate(f"window.scrollTo(0,{y})"); pg.wait_for_timeout(150)
            print(nom,i,f,sel,pg.evaluate("scrollY"))
            pg.screenshot(path=D+f'interface-{nom}-ecran-{i}.png'); pg.close()
    # comparatif : même écran A avant / après
    c=b.new_context(**DESK)
    pg=c.new_page(); pg.goto('file:///workspace/design/maquettes/A/accueil.html'); prep(pg); pg.screenshot(path='/tmp/avant.png'); pg.close()
    b.close()
