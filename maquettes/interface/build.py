import re
A='/workspace/design/maquettes/A/'
css=open('da.css').read()
def common(h):
    h=re.sub(r'<style>.*?</style>','<meta name="viewport" content="width=device-width, initial-scale=1"><style>\n'+css+'</style>',h,flags=re.S)
    h=h.replace('<div class="logo"><i>cv.</i>Cotes Value</div>','<div class="logo"><i>cv<b>.</b></i>Cotes Value</div>')
    h=h.replace('<div class="seg"><span class="on">Fixe 10 €</span><span>Kelly ¼</span></div>','<div class="mode"><em>Mise</em><div class="seg"><span>Fixe 10 €</span><span class="on">Kelly ¼</span></div></div>')
    return h
h=common(open(A+'accueil.html').read())
kp=re.search(r'<div class="kpis">.*?\n</div>',h,re.S).group(0)
h=h.replace(kp,'''<div class="kpis">
 <div class="kpi"><p>Gain net · paris uniques · Kelly ¼</p><strong class="num pos"><span class="plus">+</span>631<sup>€</sup></strong><span>2 777 réglés · toutes références <b>+1 198 €</b></span></div>
 <div class="kpi"><p>Réussite · CLV</p><strong class="num">39 %</strong><span>CLV moy. +2,4 % · ROI en 10 € fixes −5,7 %</span></div>
 <div class="kpi"><p>Mes stratégies · depuis activation</p><strong class="num neg">−60,00<sup>€</sup></strong><span>Pinnacle 1, 2, 5, 6 · 6 réglés · 6 en cours · 10 € par prise</span></div>
 <div class="kpi alerte"><p>Fuite principale</p><strong class="num neg">−2 090<sup>€</sup></strong><span>Cotes &gt; 10 : 568 paris, ROI −36,8 % · 10 € fixes</span></div>
</div>''')
h=h.replace('<small>bilan depuis le 14/10</small>','<small>depuis le 14/10 · 10 € par prise</small>')
h=h.replace('Gain cumulé <small>paris uniques</small>','Gain cumulé <small>paris uniques · 10 € fixes</small>')
h=h.replace('Top 5 stratégies <small>gain net</small>','Top 5 stratégies <small>gain net · 10 € par prise</small>')
h=h.replace('Derniers résultats</h3>','Derniers résultats <small>10 € par prise</small></h3>')
h=h.replace('Voir tous les paris, filtres avancés et export CSV ›','Voir tous les paris, filtres avancés et export CSV →').replace(' ›</span>',' →</span>').replace('Parier ›','Parier →')
h=h.replace('stroke="#d6dbe8" stroke-dasharray="3 3"','stroke="#C9C4B8" stroke-dasharray="3 3"').replace('stroke="#d23c3c" stroke-width="2"','stroke="#12120F" stroke-width="1.5"')
h=h.replace('<span class="s">05/10</span><span class="s">25/10</span>','<span class="s" style="font-family:var(--mono)">05/10</span><span class="s" style="font-family:var(--mono)">25/10</span>')
h=h.replace('style="font-size:13px"','style="font-size:13.5px"')
open('accueil.html','w').write(h)
s=common(open(A+'strategies.html').read())
s=s.replace('<div class="nm">★ ','<div class="nm"><span class="mk"></span>')
s=s.replace('ton suivi (★)','ton suivi (<span style="display:inline-block;width:7px;height:7px;background:#12120F;vertical-align:1px"></span>)')
s=s.replace('style="font-weight:700"','').replace('class="num pos" >','class="net num pos">').replace('class="num neg" >','class="net num neg">').replace('class="num nul" >','class="net num nul">')
s=s.replace('<main><h2>Stratégies</h2><p class="note" style="font-size:13px;margin-top:4px">','<main><div class="pagehead"><h2>Stratégies</h2><p class="note" style="font-size:13.5px;margin-top:6px">')
s=s.replace('10 € par prise.</p>','10 € par prise.</p></div>',1)
s=s.replace('<div class="card" style="padding:6px 8px">','<div class="card" style="padding-top:0">')
s=s.replace('style="padding:8px 12px"','style="padding:10px 0"')
s=s.replace('<small>2 777 réglés · −1 591,20 € · ROI −5,7 %</small>','<small>2 777 réglés · Kelly ¼ <span class="plus">+</span>631 € · toutes réf. <span class="plus">+</span>1 198 € · ROI ci-dessous en 10 € fixes (−1 591,20 € · −5,7 %)</small>')
s=s.replace('<h3 style="margin-top:24px">','<h3 style="margin-top:40px">')
s=s.replace('Classer par : Gain net ▾','Classer par : Gain net ↓')
open('strategies.html','w').write(s)
