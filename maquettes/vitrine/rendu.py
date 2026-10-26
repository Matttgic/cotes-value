from playwright.sync_api import sync_playwright
H='file:///workspace/design/vitrine/vitrine.html'; O='/workspace/design/vitrine/'
def prep(pg):
    pg.wait_for_load_state('networkidle'); pg.evaluate("document.fonts.ready"); pg.wait_for_timeout(700)
    return pg.evaluate("[...document.fonts].filter(f=>f.status=='loaded').map(f=>f.family).join('|')"), pg.evaluate("document.documentElement.scrollWidth")
def top(pg,sel): return pg.evaluate(f"document.querySelector('{sel}').getBoundingClientRect().top+scrollY")
with sync_playwright() as p:
    b=p.chromium.launch()
    for nom,ctx,secs in [
        ('desktop',dict(viewport={'width':1440,'height':900},device_scale_factor=2),['body','#methode','#bilan','#strategies','#fin']),
        ('mobile',dict(viewport={'width':390,'height':844},device_scale_factor=2,is_mobile=True,has_touch=True),['body','.specimen','#methode','.equation','.ligne','#bilan','.kelly','#strategies','#fin'])]:
        pg=b.new_context(**ctx).new_page(); pg.goto(H); print(nom,prep(pg))
        if nom=='desktop': pg.screenshot(path=O+'vitrine-desktop-page.png',full_page=True)
        for i,s in enumerate(secs,1):
            y=0 if s=='body' else top(pg,s)-(0 if nom=='desktop' else 16)
            pg.evaluate(f"window.scrollTo(0,{y})"); pg.wait_for_timeout(150)
            print(nom,i,s,y,pg.evaluate("scrollY"))
            pg.screenshot(path=O+f'vitrine-{nom}-ecran-{i}.png')
    b.close()
