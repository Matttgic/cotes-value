from PIL import Image, ImageDraw, ImageFont
av=Image.open('/tmp/avant.png').convert('RGB'); ap=Image.open('interface-desktop-ecran-1.png').convert('RGB')
W,H=av.size; g=80; top=150
im=Image.new('RGB',(W*2+g*3,H+top+g),'#ECE9E1'); d=ImageDraw.Draw(im)
f=ImageFont.truetype('/usr/share/fonts/truetype/sand-box/google/Familjen Grotesk/FamiljenGrotesk-VariableFont_wght.ttf',64)
m=ImageFont.truetype('/usr/share/fonts/truetype/sand-box/google/Geist Mono/GeistMono-VariableFont_wght.ttf',34)
d.text((g,40),'AVANT — maquette A',font=f,fill='#12120F'); d.text((g*2+W,40),'APRÈS — A habillée avec la DA',font=f,fill='#12120F')
d.text((g+W-560,62),'accueil · 1440×900',font=m,fill='#77746B'); d.text((g*2+W*2-560,62),'accueil · 1440×900',font=m,fill='#77746B')
im.paste(av,(g,top)); im.paste(ap,(g*2+W,top))
d.rectangle((g-1,top-1,g+W,top+H),outline='#12120F',width=2); d.rectangle((g*2+W-1,top-1,g*2+2*W,top+H),outline='#12120F',width=2)
im.save('comparatif-avant-apres.png',optimize=True); print(im.size)
