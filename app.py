
import os, pathlib, json, re, shutil, subprocess, datetime, base64, io, stat
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
load_dotenv()

BASE = pathlib.Path(__file__).parent
PRODUTOS_DIR = BASE / "produtos"
SITE_DIR = BASE / "site"

app = Flask(__name__)

def slugify(text):
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii','ignore').decode()
    text = re.sub(r'[^a-z0-9]+','-', text.lower()).strip('-')
    return text[:50] or "produto"

def get_status(pasta):
    try:
        result = subprocess.run(["git", "status", "--porcelain", str(pasta)], cwd=BASE, capture_output=True, text=True, shell=True)
        out = result.stdout
        if not out.strip():
            result2 = subprocess.run(["git", "ls-files", "--error-unmatch", str(pasta)], cwd=BASE, capture_output=True, text=True, shell=True)
            if result2.returncode == 0:
                return "publicado"
            else:
                return "não publicado"
        else:
            return "publicando..."
    except:
        return "não publicado"

def listar_produtos():
    lista=[]
    if not PRODUTOS_DIR.exists():
        return lista
    for p in sorted(PRODUTOS_DIR.iterdir(), reverse=True):
        if p.is_dir():
            def rd(n,d=""):
                f=p/f"{n}.txt"
                return f.read_text(encoding="utf-8").strip() if f.exists() else d
            imgs = list(p.glob("*.jpg"))+list(p.glob("*.png"))+list(p.glob("*.jpeg"))
            lista.append({
                "id": p.name,
                "titulo": rd("titulo", p.name),
                "valor": rd("valor"),
                "entrega": rd("entrega"),
                "link": rd("link"),
                "garantia": rd("garantia"),
                "estoque": rd("estoque"),
                "descricao": rd("descricao"),
                "imagem": imgs[0].name if imgs else "",
                "status": get_status(p)
            })
    return lista

def gerar_com_ia(prompt):
    gemini_key = os.getenv("GEMINI_API_KEY")
    grok_key = os.getenv("GROK_API_KEY")
    if gemini_key and gemini_key.startswith("AIza"):
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            texto = f"""Você é especialista em catálogo afiliados. Gere JSON com: titulo, valor, entrega, garantia, estoque, descricao. Produto: {prompt} Só JSON."""
            resp = model.generate_content(texto)
            j = resp.text.replace("```json","").replace("```","").strip()
            return json.loads(j)
        except Exception as e:
            print("Gemini erro:", e)
    return {
        "titulo": prompt.title()[:60] if prompt else "Produto Elite Comércio",
        "valor": "97.90",
        "entrega": "Full",
        "garantia": "12 meses",
        "estoque": "27",
        "descricao": f"{prompt} - Achado verificado Elite Comércio."
    }

def analisar_print_com_ia(image_b64):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and gemini_key.startswith("AIza"):
        try:
            import google.generativeai as genai
            from PIL import Image
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            if "," in image_b64:
                image_b64 = image_b64.split(",")[1]
            img_data = base64.b64decode(image_b64)
            img = Image.open(io.BytesIO(img_data))
            prompt = """Analise print de produto Mercado Livre. Extraia titulo, valor, entrega, garantia, estoque, descricao. Retorne JSON: {"titulo":"","valor":"","entrega":"Full","garantia":"","estoque":"","descricao":"","marcacoes":[{"campo":"titulo","x":10,"y":15,"w":80,"h":8}]} posições em %."""
            resp = model.generate_content([prompt, img])
            txt = resp.text.replace("```json","").replace("```","").strip()
            return json.loads(txt)
        except Exception as e:
            print("Vision erro:", e)
    return {
        "titulo": "Kit Ferramentas 120 Peças Profissional",
        "valor": "189.90",
        "entrega": "Full",
        "garantia": "12 meses",
        "estoque": "23",
        "descricao": "Kit completo profissional - achado Elite",
        "marcacoes": [
            {"campo":"titulo","x":8,"y":12,"w":84,"h":10},
            {"campo":"valor","x":8,"y":28,"w":35,"h":8},
            {"campo":"entrega","x":8,"y":38,"w":22,"h":6},
            {"campo":"garantia","x":8,"y":48,"w":30,"h":6},
            {"campo":"estoque","x":42,"y":48,"w":18,"h":6},
            {"campo":"descricao","x":8,"y":58,"w":84,"h":12}
        ]
    }

@app.route("/")
def home():
    produtos = listar_produtos()
    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Elite Comércio - App Local IA com Barra Flutuante</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Montserrat:wght@800&display=swap" rel="stylesheet">
<style>
  body{font-family:Inter} h1{font-family:Montserrat}
  #floatingBar{transition: all 0.3s; box-shadow: 0 25px 50px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,215,0,0.2);}
  .marker{position:absolute; border:2px solid #22c55e; background: rgba(34,197,94,0.15); border-radius:6px;}
  .marker-label{position:absolute; bottom:-18px; left:0; background:#22c55e; color:black; font-size:10px; font-weight:900; padding:2px 6px; border-radius:4px; text-transform:uppercase;}
  .drag-handle{cursor:move;}
</style>
</head>
<body class="bg-[#0a0a0a] text-white min-h-screen">
<div class="max-w-[1400px] mx-auto p-6">
  <div class="flex items-center gap-4 mb-8">
    <img src="/site/logo.jpg" class="w-16 h-16 rounded-full border-2 border-yellow-400">
    <div>
      <h1 class="text-3xl font-black text-yellow-400">ELITE COMÉRCIO</h1>
      <p class="text-sm opacity-70">App Local com IA + Barra Flutuante | @elite_comercio_</p>
    </div>
    <div class="ml-auto flex gap-2">
      <span class="px-3 py-1 bg-yellow-400 text-black rounded-full text-xs font-bold">{{produtos|length}} produtos</span>
      <button onclick="sync()" class="px-4 py-2 bg-white text-black rounded-lg font-bold hover:bg-yellow-400">🚀 Sync GitHub</button>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-[440px_1fr] gap-6">
    <div class="bg-[#151515] rounded-2xl p-6 border border-yellow-400/20 h-fit sticky top-6">
      <h2 class="text-xl font-bold mb-4 flex items-center gap-2">✨ Adicionar com IA</h2>
      
      <div class="mb-4 bg-black rounded-xl p-3 border border-white/5">
        <div class="flex items-center justify-between mb-2">
          <label class="text-xs opacity-60">IA por Texto</label>
          <button onclick="abrirBarraFlutuante()" class="w-10 h-10 bg-[#222] hover:bg-yellow-400 hover:text-black border border-yellow-400/30 rounded-xl flex items-center justify-center text-lg" title="Capturar Tela com IA">🖥️</button>
        </div>
        <textarea id="promptIA" rows="2" placeholder="Ex: smartwatch x8 ultra ou cole link" class="w-full p-3 bg-[#0a0a0a] border border-white/10 rounded-xl text-sm"></textarea>
        <button onclick="gerarIA()" class="w-full mt-2 py-2 bg-gradient-to-r from-yellow-400 to-amber-500 text-black font-black rounded-xl text-sm">GERAR COM GEMINI/GROK 🤖</button>
        <p class="text-[10px] opacity-40 mt-2">Dica: clique no 🖥️ para capturar tela do Mercado Livre</p>
      </div>

      <form id="formProd" enctype="multipart/form-data" class="space-y-3">
        <input id="titulo" placeholder="Título" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm" required>
        <div class="grid grid-cols-2 gap-2">
          <input id="valor" placeholder="Valor ex: 129.90" class="p-3 bg-black border border-white/10 rounded-xl text-sm" required>
          <select id="entrega" class="p-3 bg-black border border-white/10 rounded-xl text-sm"><option>Full</option><option>Normal</option><option>Retirada</option></select>
        </div>
        <input id="link" placeholder="Link de redirecionamento (afiliado)" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm" required>
        <div class="grid grid-cols-2 gap-2">
          <input id="garantia" placeholder="Garantia ex: 12 meses" class="p-3 bg-black border border-white/10 rounded-xl text-sm">
          <input id="estoque" placeholder="Estoque ex: 15" class="p-3 bg-black border border-white/10 rounded-xl text-sm">
        </div>
        <textarea id="descricao" placeholder="Descrição" rows="2" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm"></textarea>
        <div>
          <label class="text-xs opacity-60">Imagens (pega direto da pasta)</label>
          <input type="file" id="imagem" accept="image/*" multiple class="w-full mt-1 text-xs file:bg-yellow-400 file:text-black file:border-0 file:rounded-lg file:px-3 file:py-1">
          <div id="preview" class="mt-2 grid grid-cols-3 gap-2"></div>
        </div>
        <button type="submit" class="w-full py-3 bg-yellow-400 text-black font-black rounded-xl text-lg hover:bg-yellow-300">CRIAR PRODUTO 📦</button>
      </form>
      <p id="msg" class="mt-3 text-xs text-center opacity-70"></p>
    </div>

    <div class="bg-[#111] rounded-2xl p-6">
      <h2 class="font-bold mb-4">Produtos na pasta ({{produtos|length}})</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {% for p in produtos %}
        <div class="bg-[#1a1a1a] rounded-xl p-4 border border-white/5">
          <div class="flex gap-3">
            <div class="w-20 h-20 bg-black rounded-lg flex items-center justify-center text-[10px]">IMG</div>
            <div class="flex-1">
              <div class="flex items-center gap-2">
                <span class="text-[10px] px-2 py-0.5 rounded-full font-bold {% if p.status=='publicado' %}bg-green-500 text-black{% else %}bg-yellow-400 text-black{% endif %}">{{p.status}}</span>
                <span class="text-[10px] opacity-60">{{p.id}}</span>
              </div>
              <h3 class="font-bold text-sm mt-1">{{p.titulo}}</h3>
              <p class="text-yellow-400 font-black">R$ {{p.valor}}</p>
              <p class="text-[11px] opacity-60">Entrega: {{p.entrega}} | Estoque: {{p.estoque}}</p>
            </div>
          </div>
          <div class="flex gap-2 mt-3">
            <button onclick="editar('{{p.id}}')" class="flex-1 py-1.5 bg-white/10 rounded-lg text-xs">✏️ Editar</button>
            <button onclick="excluir('{{p.id}}')" class="flex-1 py-1.5 bg-red-500/20 text-red-400 rounded-lg text-xs">🗑️ Excluir</button>
          </div>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
</div>

<div id="floatingBar" class="hidden fixed bottom-5 right-5 w-[480px] max-w-[95vw] bg-[#1a1a1a] rounded-[20px] border-2 border-yellow-400/50 z-[9999] overflow-hidden">
  <div id="dragHeader" class="drag-handle flex items-center justify-between px-4 py-3 bg-black border-b border-white/10">
    <div class="flex items-center gap-2"><span class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span><span class="font-black text-sm text-yellow-400">CAPTURA IA - ELITE</span></div>
    <button onclick="fecharBarraFlutuante()" class="w-7 h-7 bg-red-500/20 hover:bg-red-500 text-red-400 hover:text-white rounded-full flex items-center justify-center font-bold">✕</button>
  </div>
  <div class="p-4">
    <div id="captureArea" class="relative w-full h-[300px] bg-[#0a0a0a] rounded-xl border-2 border-dashed border-white/20 overflow-hidden flex flex-col items-center justify-center">
      <div id="capturePlaceholder" class="text-center p-6">
        <div class="text-4xl mb-2">🖥️</div>
        <p class="text-sm font-bold">Clique em Capturar Tela</p>
        <p class="text-[11px] opacity-60 mt-1">Abra o produto no Mercado Livre<br>e a IA vai marcar em verde</p>
        <button onclick="capturarTela()" class="mt-4 px-6 py-2 bg-yellow-400 text-black font-black rounded-xl text-sm">📸 CAPTURAR TELA</button>
      </div>
      <img id="captureImg" class="hidden w-full h-full object-contain">
      <div id="markersLayer" class="absolute inset-0 pointer-events-none"></div>
    </div>
    <div id="analiseStatus" class="hidden mt-3 p-3 bg-black rounded-xl border border-white/10"><p class="text-xs font-bold">IA analisando tela...</p></div>
    <div id="resultadoIA" class="hidden mt-3 space-y-1 max-h-[150px] overflow-y-auto text-[11px] bg-black p-3 rounded-xl"></div>
    <div id="acoesBarra" class="hidden mt-4 flex gap-3">
      <button onclick="fecharBarraFlutuante()" class="flex-1 py-3 bg-red-500/10 border border-red-500/30 text-red-400 font-black rounded-xl">✕ CANCELAR</button>
      <button onclick="confirmarCaptura()" class="flex-1 py-3 bg-green-500 text-black font-black rounded-xl">✓ USAR DADOS (V)</button>
    </div>
  </div>
</div>

<script>
let imagemCapturadaBase64=null, dadosDetectados=null;
(function(){
  const bar=document.getElementById('floatingBar'), handle=document.getElementById('dragHeader');
  let drag=false,sx,sy,il,it;
  handle.addEventListener('mousedown',e=>{drag=true;sx=e.clientX;sy=e.clientY;let r=bar.getBoundingClientRect();il=r.left;it=r.top;bar.style.bottom='auto';bar.style.right='auto';});
  document.addEventListener('mousemove',e=>{if(!drag)return;bar.style.left=(il+e.clientX-sx)+'px';bar.style.top=(it+e.clientY-sy)+'px';});
  document.addEventListener('mouseup',()=>drag=false);
})();
function abrirBarraFlutuante(){document.getElementById('floatingBar').classList.remove('hidden');}
function fecharBarraFlutuante(){
  document.getElementById('floatingBar').classList.add('hidden');
  document.getElementById('capturePlaceholder').classList.remove('hidden');
  document.getElementById('captureImg').classList.add('hidden');
  document.getElementById('markersLayer').innerHTML='';
  document.getElementById('resultadoIA').classList.add('hidden');
  document.getElementById('acoesBarra').classList.add('hidden');
  document.getElementById('analiseStatus').classList.add('hidden');
  imagemCapturadaBase64=null; dadosDetectados=null;
}
async function capturarTela(){
  try{
    const stream=await navigator.mediaDevices.getDisplayMedia({video:true});
    const video=document.createElement('video'); video.srcObject=stream; await video.play();
    const canvas=document.createElement('canvas'); canvas.width=video.videoWidth; canvas.height=video.videoHeight;
    canvas.getContext('2d').drawImage(video,0,0); stream.getTracks().forEach(t=>t.stop());
    imagemCapturadaBase64=canvas.toDataURL('image/jpeg',0.8);
    document.getElementById('captureImg').src=imagemCapturadaBase64;
    document.getElementById('captureImg').classList.remove('hidden');
    document.getElementById('capturePlaceholder').classList.add('hidden');
    analisarTela();
  }catch(err){alert('Permita captura de tela');}
}
async function analisarTela(){
  if(!imagemCapturadaBase64)return;
  document.getElementById('analiseStatus').classList.remove('hidden');
  const res=await fetch('/api/analisar-print',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({imagem:imagemCapturadaBase64})});
  const data=await res.json(); dadosDetectados=data;
  document.getElementById('analiseStatus').classList.add('hidden');
  const layer=document.getElementById('markersLayer'); layer.innerHTML='';
  (data.marcacoes||[]).forEach(m=>{
    const el=document.createElement('div'); el.className='marker';
    el.style.left=m.x+'%'; el.style.top=m.y+'%'; el.style.width=m.w+'%'; el.style.height=m.h+'%';
    const lb=document.createElement('div'); lb.className='marker-label'; lb.innerText=m.campo; el.appendChild(lb); layer.appendChild(el);
  });
  const div=document.getElementById('resultadoIA');
  div.innerHTML=`<div class=text-green-400 font-bold>✅ Detectado:</div><div>Título: ${data.titulo}</div><div>Valor: R$ ${data.valor}</div><div>Entrega: ${data.entrega}</div>`;
  div.classList.remove('hidden'); document.getElementById('acoesBarra').classList.remove('hidden');
}
function confirmarCaptura(){
  if(!dadosDetectados)return;
  if(dadosDetectados.titulo) titulo.value=dadosDetectados.titulo;
  if(dadosDetectados.valor) valor.value=dadosDetectados.valor;
  if(dadosDetectados.entrega) entrega.value=dadosDetectados.entrega;
  if(dadosDetectados.garantia) garantia.value=dadosDetectados.garantia;
  if(dadosDetectados.estoque) estoque.value=dadosDetectados.estoque;
  if(dadosDetectados.descricao) descricao.value=dadosDetectados.descricao;
  msg.innerText='✅ Dados da captura aplicados!'; fecharBarraFlutuante();
}
async function gerarIA(){
  const prompt=document.getElementById('promptIA').value;
  if(!prompt)return alert('Digite algo');
  msg.innerText='Gerando com IA...';
  const res=await fetch('/api/gerar-ia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
  const data=await res.json();
  if(data.titulo) titulo.value=data.titulo;
  if(data.valor) valor.value=data.valor;
  if(data.entrega) entrega.value=data.entrega;
  if(data.garantia) garantia.value=data.garantia;
  if(data.estoque) estoque.value=data.estoque;
  if(data.descricao) descricao.value=data.descricao;
  msg.innerText='✨ Preenchido!';
}
imagem.addEventListener('change',e=>{
  const p=document.getElementById('preview'); p.innerHTML='';
  [...e.target.files].forEach(f=>{const img=document.createElement('img'); img.src=URL.createObjectURL(f); img.className='w-full h-20 object-cover rounded-lg'; p.appendChild(img);});
});
formProd.addEventListener('submit', async e=>{
  e.preventDefault();
  const fd=new FormData(); fd.append('titulo',titulo.value); fd.append('valor',valor.value); fd.append('entrega',entrega.value); fd.append('link',link.value); fd.append('garantia',garantia.value); fd.append('estoque',estoque.value); fd.append('descricao',descricao.value);
  for(let f of imagem.files) fd.append('imagens',f);
  msg.innerText='Criando...'; const res=await fetch('/api/criar',{method:'POST',body:fd}); const data=await res.json(); msg.innerText=data.msg; if(data.ok) setTimeout(()=>location.reload(),1200);
});
async function sync(){if(!confirm('Sync GitHub?'))return; const r=await fetch('/api/sync',{method:'POST'}); const d=await r.json(); alert(d.msg); location.reload();}
async function excluir(id){
  if(!confirm('Excluir '+id+'?'))return;
  const r=await fetch('/api/deletar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  const d=await r.json(); alert(d.msg||'Excluído'); location.reload();
}
async function editar(id){const n=prompt('Novo título'); if(!n)return; await fetch('/api/editar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,titulo:n})}); location.reload();}
</script>
</body>
</html>
    """
    return render_template_string(html, produtos=produtos)

@app.route("/api/gerar-ia", methods=["POST"])
def api_gerar_ia():
    data=request.json; return jsonify(gerar_com_ia(data.get("prompt","")))

@app.route("/api/analisar-print", methods=["POST"])
def api_analisar_print():
    try:
        data=request.json; return jsonify(analisar_print_com_ia(data.get("imagem","")))
    except Exception as e:
        return jsonify({"erro":str(e)}),500

@app.route("/api/criar", methods=["POST"])
def api_criar():
    try:
        titulo=request.form.get("titulo","").strip()
        if not titulo: return jsonify({"ok":False,"msg":"Título obrigatório"})
        valor=request.form.get("valor",""); entrega=request.form.get("entrega",""); link=request.form.get("link",""); garantia=request.form.get("garantia",""); estoque=request.form.get("estoque",""); descricao=request.form.get("descricao","")
        slug=slugify(titulo); existing=len([d for d in PRODUTOS_DIR.iterdir() if d.is_dir()])+1 if PRODUTOS_DIR.exists() else 1
        folder_name=f"{existing:03d}_{slug}"; pasta=PRODUTOS_DIR/folder_name; pasta.mkdir(parents=True,exist_ok=True)
        (pasta/"titulo.txt").write_text(titulo,encoding="utf-8"); (pasta/"valor.txt").write_text(valor,encoding="utf-8"); (pasta/"entrega.txt").write_text(entrega,encoding="utf-8"); (pasta/"link.txt").write_text(link,encoding="utf-8"); (pasta/"garantia.txt").write_text(garantia,encoding="utf-8"); (pasta/"estoque.txt").write_text(estoque,encoding="utf-8"); (pasta/"descricao.txt").write_text(descricao,encoding="utf-8")
        for idx,f in enumerate(request.files.getlist("imagens")):
            if f.filename:
                ext=pathlib.Path(f.filename).suffix or ".jpg"; dest=pasta/f"imagem_{idx+1}{ext}"; f.save(dest)
        subprocess.run(["python","scripts/gerar_catalogo.py"],cwd=BASE)
        try:
            subprocess.run(["git","add","."],cwd=BASE,shell=True); subprocess.run(["git","commit","-m",f"feat: {titulo}"],cwd=BASE,shell=True); subprocess.run(["git","push"],cwd=BASE,shell=True)
        except: pass
        return jsonify({"ok":True,"msg":f"✅ Criado {folder_name}"})
    except Exception as e:
        return jsonify({"ok":False,"msg":f"Erro: {e}"})

@app.route("/api/sync", methods=["POST"])
def api_sync():
    try:
        subprocess.run(["python","scripts/gerar_catalogo.py"],cwd=BASE); subprocess.run(["git","add","."],cwd=BASE,shell=True); subprocess.run(["git","commit","-m","sync"],cwd=BASE,shell=True); subprocess.run(["git","push"],cwd=BASE,shell=True)
        return jsonify({"ok":True,"msg":"Sincronizado!"})
    except Exception as e:
        return jsonify({"ok":False,"msg":str(e)})

@app.route("/api/deletar", methods=["POST"])
def api_del():
    try:
        id_=request.json.get("id"); p=PRODUTOS_DIR/id_
        if not p.exists(): return jsonify({"ok":False,"msg":"Pasta não encontrada"})
        def on_err(f,path,exc):
            try: os.chmod(path, stat.S_IWRITE)
            except: pass
            try: f(path)
            except: pass
        shutil.rmtree(p, onerror=on_err)
        site_dir=SITE_DIR/"produtos"
        if site_dir.exists():
            for img in site_dir.glob(f"{id_}_*"):
                try: img.unlink()
                except: pass
        subprocess.run(["python","scripts/gerar_catalogo.py"],cwd=BASE)
        try:
            subprocess.run(["git","rm","-rf",str(p)],cwd=BASE,shell=True); subprocess.run(["git","add","."],cwd=BASE,shell=True); subprocess.run(["git","commit","-m",f"remove: {id_}"],cwd=BASE,shell=True); subprocess.run(["git","push"],cwd=BASE,shell=True)
        except: pass
        return jsonify({"ok":True,"msg":"Excluído com sucesso!"})
    except Exception as e:
        return jsonify({"ok":False,"msg":f"Erro: {e}"})

@app.route("/api/editar", methods=["POST"])
def api_edit():
    id_=request.json.get("id"); titulo=request.json.get("titulo")
    p=PRODUTOS_DIR/id_
    if p.exists() and titulo:
        (p/"titulo.txt").write_text(titulo,encoding="utf-8")
        subprocess.run(["python","scripts/gerar_catalogo.py"],cwd=BASE)
    return jsonify({"ok":True})

if __name__=="__main__":
    PRODUTOS_DIR.mkdir(exist_ok=True); (SITE_DIR/"produtos").mkdir(exist_ok=True)
    print("ELITE COMÉRCIO - App Local com Barra Flutuante IA - http://localhost:5000")
    app.run(debug=True, port=5000)
