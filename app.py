
import os, pathlib, stat, json, re, shutil, subprocess, datetime
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
load_dotenv()

BASE = pathlib.Path(__file__).parent
PRODUTOS_DIR = BASE / "produtos"
SITE_DIR = BASE / "site"
SITE_JSON = SITE_DIR / "produtos.json"

app = Flask(__name__)

def slugify(text):
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii','ignore').decode()
    text = re.sub(r'[^a-z0-9]+','-', text.lower()).strip('-')
    return text[:50] or "produto"

def get_status(pasta):
    # verifica git
    try:
        result = subprocess.run(["git", "status", "--porcelain", str(pasta)], cwd=BASE, capture_output=True, text=True, shell=True)
        out = result.stdout
        if not out.strip():
            # check if committed
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

def gerar_com_ia(prompt, imagem_path=None):
    gemini_key = os.getenv("GEMINI_API_KEY")
    grok_key = os.getenv("GROK_API_KEY")
    # Tenta Gemini
    if gemini_key and gemini_key.startswith("AIza"):
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            texto = f"""Você é um especialista em catálogo de afiliados. 
            Gere JSON com: titulo (atraente), valor (ex: 129.90), entrega (Full ou Normal), garantia (ex: 12 meses), estoque (ex: 50), descricao (venda, 2 linhas).
            Produto: {prompt}
            Responda APENAS JSON puro."""
            resp = model.generate_content(texto)
            j = resp.text.replace("```json","").replace("```","").strip()
            data = json.loads(j)
            return data
        except Exception as e:
            print("Gemini erro:", e)
    # Tenta Grok
    if grok_key:
        try:
            import requests
            r = requests.post("https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {grok_key}"},
                json={
                    "model":"grok-beta",
                    "messages":[{"role":"user","content":f"Gere JSON para catalogo: titulo, valor, entrega, garantia, estoque, descricao para produto: {prompt}. Só JSON"}],
                    "temperature":0.7
                }, timeout=20)
            txt = r.json()["choices"][0]["message"]["content"]
            txt = txt.replace("```json","").replace("```","").strip()
            return json.loads(txt)
        except Exception as e:
            print("Grok erro:", e)
    # Fallback mock inteligente
    return {
        "titulo": prompt.title()[:60] if prompt else "Produto Elite Comércio",
        "valor": "97.90",
        "entrega": "Full",
        "garantia": "12 meses",
        "estoque": "27",
        "descricao": f"{prompt} - Achado imperdível selecionado pela Elite Comércio. Qualidade verificada!"
    }

@app.route("/")
def home():
    produtos = listar_produtos()
    # HTML do app local
    html = '''
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Elite Comércio - App Local IA</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Montserrat:wght@800&display=swap" rel="stylesheet">
<style>body{font-family:Inter}h1{font-family:Montserrat}</style>
</head>
<body class="bg-[#0a0a0a] text-white min-h-screen">
<div class="max-w-[1400px] mx-auto p-6">
  <div class="flex items-center gap-4 mb-8">
    <img src="/site/logo.jpg" class="w-16 h-16 rounded-full border-2 border-yellow-400">
    <div>
      <h1 class="text-3xl font-black text-yellow-400">ELITE COMÉRCIO</h1>
      <p class="text-sm opacity-70">App Local com IA - @elite_comercio_ | Irecê BA</p>
    </div>
    <div class="ml-auto flex gap-2">
      <span class="px-3 py-1 bg-yellow-400 text-black rounded-full text-xs font-bold">{{produtos|length}} produtos</span>
      <button onclick="sync()" class="px-4 py-2 bg-white text-black rounded-lg font-bold hover:bg-yellow-400">🚀 Sincronizar GitHub</button>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-[420px_1fr] gap-6">
    <!-- FORM -->
    <div class="bg-[#151515] rounded-2xl p-6 border border-yellow-400/20 h-fit sticky top-6">
      <h2 class="text-xl font-bold mb-4 flex items-center gap-2">✨ Adicionar com IA</h2>

      <div class="mb-4">
        <label class="text-xs opacity-60">Descreva o produto ou cole link Mercado Livre</label>
        <textarea id="promptIA" rows="2" placeholder="Ex: smartwatch x8 ultra 49mm com pulseira" class="w-full mt-1 p-3 bg-black border border-white/10 rounded-xl text-sm"></textarea>
        <button onclick="gerarIA()" class="w-full mt-2 py-2 bg-gradient-to-r from-yellow-400 to-amber-500 text-black font-black rounded-xl">GERAR COM GEMINI/GROK 🤖</button>
      </div>

      <hr class="border-white/10 my-4">

      <form id="formProd" enctype="multipart/form-data" class="space-y-3">
        <input id="titulo" placeholder="Título" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm" required>
        <div class="grid grid-cols-2 gap-2">
          <input id="valor" placeholder="Valor ex: 129.90" class="p-3 bg-black border border-white/10 rounded-xl text-sm" required>
          <select id="entrega" class="p-3 bg-black border border-white/10 rounded-xl text-sm">
            <option>Full</option><option>Normal</option><option>Retirada</option>
          </select>
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

    <!-- LISTA -->
    <div class="bg-[#111] rounded-2xl p-6">
      <h2 class="font-bold mb-4">Produtos na pasta ({{produtos|length}})</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {% for p in produtos %}
        <div class="bg-[#1a1a1a] rounded-xl p-4 border border-white/5 hover:border-yellow-400/30 transition">
          <div class="flex gap-3">
            <div class="w-20 h-20 bg-black rounded-lg overflow-hidden flex items-center justify-center text-[10px]">IMG</div>
            <div class="flex-1">
              <div class="flex items-center gap-2">
                <span class="text-[10px] px-2 py-0.5 rounded-full font-bold 
                  {% if p.status=='publicado' %}bg-green-500 text-black{% elif p.status=='não publicado' %}bg-yellow-400 text-black{% elif p.status=='publicando...' %}bg-blue-400 text-black{% else %}bg-red-500{% endif %}">
                  {{p.status}}
                </span>
                <span class="text-[10px] opacity-60">{{p.id}}</span>
              </div>
              <h3 class="font-bold text-sm mt-1 leading-tight">{{p.titulo}}</h3>
              <p class="text-yellow-400 font-black">R$ {{p.valor}}</p>
              <p class="text-[11px] opacity-60">Entrega: {{p.entrega}} | Estoque: {{p.estoque}} | {{p.garantia}}</p>
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

<script>
async function gerarIA(){
  const prompt = document.getElementById('promptIA').value;
  if(!prompt) return alert('Digite algo');
  document.getElementById('msg').innerText='Gerando com IA...';
  const res = await fetch('/api/gerar-ia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
  const data = await res.json();
  if(data.titulo) document.getElementById('titulo').value=data.titulo;
  if(data.valor) document.getElementById('valor').value=data.valor;
  if(data.entrega) document.getElementById('entrega').value=data.entrega;
  if(data.garantia) document.getElementById('garantia').value=data.garantia;
  if(data.estoque) document.getElementById('estoque').value=data.estoque;
  if(data.descricao) document.getElementById('descricao').value=data.descricao;
  document.getElementById('msg').innerText='✨ Preenchido com IA!';
}

document.getElementById('imagem').addEventListener('change', e=>{
  const preview=document.getElementById('preview'); preview.innerHTML='';
  [...e.target.files].forEach(f=>{
    const img=document.createElement('img'); img.src=URL.createObjectURL(f); img.className='w-full h-20 object-cover rounded-lg';
    preview.appendChild(img);
  })
});

document.getElementById('formProd').addEventListener('submit', async e=>{
  e.preventDefault();
  const fd = new FormData();
  fd.append('titulo', titulo.value);
  fd.append('valor', valor.value);
  fd.append('entrega', entrega.value);
  fd.append('link', link.value);
  fd.append('garantia', garantia.value);
  fd.append('estoque', estoque.value);
  fd.append('descricao', descricao.value);
  for(let f of imagem.files) fd.append('imagens', f);
  msg.innerText='Criando pasta e sincronizando...';
  const res = await fetch('/api/criar',{method:'POST',body:fd});
  const data = await res.json();
  msg.innerText=data.msg;
  if(data.ok) setTimeout(()=>location.reload(),1200);
});

async function sync(){
  if(!confirm('Enviar todos produtos para GitHub e Render?')) return;
  const res = await fetch('/api/sync',{method:'POST'});
  const data = await res.json();
  alert(data.msg);
  location.reload();
}
async function excluir(id){
  if(!confirm('Excluir '+id+'?')) return;
  await fetch('/api/deletar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
  location.reload();
}
async function editar(id){
  const novo = prompt('Novo título para '+id);
  if(!novo) return;
  await fetch('/api/editar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,titulo:novo})});
  location.reload();
}
</script>
</body>
</html>
    '''
    return render_template_string(html, produtos=produtos)

@app.route("/site/<path:path>")
def serve_site(path):
    return app.send_static_file(path)

@app.route("/api/gerar-ia", methods=["POST"])
def api_gerar_ia():
    data = request.json
    prompt = data.get("prompt","")
    result = gerar_com_ia(prompt)
    return jsonify(result)

@app.route("/api/criar", methods=["POST"])
def api_criar():
    try:
        titulo = request.form.get("titulo","").strip()
        if not titulo:
            return jsonify({"ok":False,"msg":"Título obrigatório"})
        valor = request.form.get("valor","")
        entrega = request.form.get("entrega","")
        link = request.form.get("link","")
        garantia = request.form.get("garantia","")
        estoque = request.form.get("estoque","")
        descricao = request.form.get("descricao","")

        slug = slugify(titulo)
        # ID incremental
        existing = len([d for d in PRODUTOS_DIR.iterdir() if d.is_dir()]) + 1 if PRODUTOS_DIR.exists() else 1
        folder_name = f"{existing:03d}_{slug}"
        pasta = PRODUTOS_DIR / folder_name
        pasta.mkdir(parents=True, exist_ok=True)

        (pasta/"titulo.txt").write_text(titulo, encoding="utf-8")
        (pasta/"valor.txt").write_text(valor, encoding="utf-8")
        (pasta/"entrega.txt").write_text(entrega, encoding="utf-8")
        (pasta/"link.txt").write_text(link, encoding="utf-8")
        (pasta/"garantia.txt").write_text(garantia, encoding="utf-8")
        (pasta/"estoque.txt").write_text(estoque, encoding="utf-8")
        (pasta/"descricao.txt").write_text(descricao, encoding="utf-8")

        # imagens
        for idx, f in enumerate(request.files.getlist("imagens")):
            if f.filename:
                ext = pathlib.Path(f.filename).suffix or ".jpg"
                dest = pasta / f"imagem_{idx+1}{ext}"
                f.save(dest)

        # gera catalogo
        subprocess.run(["python", "scripts/gerar_catalogo.py"], cwd=BASE)

        # git auto
        try:
            subprocess.run(["git","add","."], cwd=BASE, shell=True)
            subprocess.run(["git","commit","-m",f"feat: novo produto {titulo}"], cwd=BASE, shell=True)
            subprocess.run(["git","push"], cwd=BASE, shell=True)
            status = "publicando... (push enviado)"
        except:
            status = "criado local - faça push manual"

        return jsonify({"ok":True,"msg":f"✅ Produto criado em {folder_name} | {status}"})
    except Exception as e:
        return jsonify({"ok":False,"msg":f"Erro: {e}"})

@app.route("/api/sync", methods=["POST"])
def api_sync():
    try:
        subprocess.run(["python","scripts/gerar_catalogo.py"], cwd=BASE)
        subprocess.run(["git","add","."], cwd=BASE, shell=True)
        subprocess.run(["git","commit","-m","sync: elite comercio catalogo"], cwd=BASE, shell=True)
        subprocess.run(["git","push"], cwd=BASE, shell=True)
        return jsonify({"ok":True,"msg":"Sincronizado com GitHub! Render vai atualizar em 1-2min"})
    except Exception as e:
        return jsonify({"ok":False,"msg":str(e)})

@app.route("/api/deletar", methods=["POST"])
def api_del():
    id_ = request.json.get("id")
    p = PRODUTOS_DIR / id_
    if p.exists():
        shutil.rmtree(p)
        subprocess.run(["python","scripts/gerar_catalogo.py"], cwd=BASE)
        return jsonify({"ok":True})
    return jsonify({"ok":False})

@app.route("/api/editar", methods=["POST"])
def api_edit():
    id_ = request.json.get("id")
    titulo = request.json.get("titulo")
    p = PRODUTOS_DIR / id_
    if p.exists() and titulo:
        (p/"titulo.txt").write_text(titulo, encoding="utf-8")
        subprocess.run(["python","scripts/gerar_catalogo.py"], cwd=BASE)
    return jsonify({"ok":True})

if __name__ == "__main__":
    PRODUTOS_DIR.mkdir(exist_ok=True)
    (SITE_DIR/"produtos").mkdir(exist_ok=True)
    print("="*50)
    print(" ELITE COMÉRCIO - App Local com IA")
    print(" Acesse: http://localhost:5000")
    print("="*50)
    app.run(debug=True, port=5000)
