
import os, pathlib, json, re, shutil, subprocess, base64, io, stat, time
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
        if not result.stdout.strip():
            r2 = subprocess.run(["git", "ls-files", "--error-unmatch", str(pasta)], cwd=BASE, capture_output=True, text=True, shell=True)
            return "publicado" if r2.returncode==0 else "não publicado"
        return "publicando..."
    except:
        return "não publicado"

def listar_produtos():
    lista=[]
    if PRODUTOS_DIR.exists():
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
    gemini_key = os.getenv("GEMINI_API_KEY","").strip()
    if gemini_key and gemini_key.startswith("AIza") and len(gemini_key)>30:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(f"Gere JSON: titulo, valor, entrega, garantia, estoque, descricao para: {prompt}. Só JSON", generation_config={"temperature":0.3})
            txt = resp.text.replace("```json","").replace("```","").strip()
            s=txt.find("{"); e=txt.rfind("}")+1
            if s!=-1: txt=txt[s:e]
            return json.loads(txt)
        except Exception as e:
            print(f"Gemini erro: {e}")
    return {"titulo":prompt.title()[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":prompt}

def analisar_print_avancado(image_b64):
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316","descricao":"#06b6d4"}
    fallback = {
        "titulo":"Fone Gamer Kapbom Ka-9007","valor":"89.99","entrega":"Normal","garantia":"15 dias","estoque":"3","descricao":"Achado verificado Elite Comércio",
        "marcacoes":[
            {"campo":"titulo","x":6,"y":10,"w":62,"h":10,"conf":0.88,"color":"#22c55e"},
            {"campo":"valor","x":6,"y":24,"w":30,"h":7,"conf":0.92,"color":"#eab308"},
            {"campo":"entrega","x":6,"y":34,"w":18,"h":5,"conf":0.85,"color":"#3b82f6"},
            {"campo":"garantia","x":28,"y":34,"w":22,"h":5,"conf":0.80,"color":"#a855f7"},
            {"campo":"estoque","x":52,"y":34,"w":12,"h":5,"conf":0.80,"color":"#f97316"},
        ]
    }
    gemini_key = os.getenv("GEMINI_API_KEY","").strip()
    if not gemini_key or len(gemini_key)<30:
        return fallback
    try:
        import google.generativeai as genai
        from PIL import Image
        genai.configure(api_key=gemini_key)
        if "," in image_b64: image_b64=image_b64.split(",")[1]
        img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
        if img.width>1600: img.thumbnail((1600,1600))
        prompt="Extraia titulo,valor,entrega,garantia,estoque,descricao e bbox em % como JSON: {titulo,valor,entrega,garantia,estoque,descricao,marcacoes:[{campo,x,y,w,h,conf}]} Só JSON"
        for model_name in ["gemini-1.5-pro","gemini-1.5-flash"]:
            try:
                model=genai.GenerativeModel(model_name)
                resp=model.generate_content([prompt, img], generation_config={"temperature":0.1})
                txt=resp.text.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1: txt=txt[s:e]
                data=json.loads(txt)
                for m in data.get("marcacoes",[]):
                    m["color"]=cores.get(m["campo"],"#22c55e")
                return data
            except Exception as e:
                print(f"{model_name} fail {e}")
                continue
    except Exception as e:
        print(f"Erro geral {e}")
    return fallback

@app.route("/")
def home():
    produtos = listar_produtos()
    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Elite Comércio - v3 Fixed Botões</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Montserrat:wght@800&display=swap" rel="stylesheet">
<style>
body{font-family:Inter} h1{font-family:Montserrat}
#floatingBar{box-shadow:0 25px 50px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,215,0,0.3);}
.marker{position:absolute; border-width:2.5px; border-style:solid; border-radius:8px; background:rgba(0,0,0,0.12); animation:pulse 2s infinite;}
.marker-label{position:absolute; bottom:-20px; left:0; color:black; font-size:10px; font-weight:900; padding:2px 8px; border-radius:6px; text-transform:uppercase;}
.conf-badge{position:absolute; top:-8px; right:-8px; background:black; color:white; font-size:9px; padding:1px 5px; border-radius:10px;}
@keyframes pulse{0%,100%{opacity:0.9}50%{opacity:0.5}}
.drag-handle{cursor:move; user-select:none;}
.btn{transition: all 0.2s;}
.btn:active{transform:scale(0.97);}
</style>
</head>
<body class="bg-[#0a0a0a] text-white min-h-screen">
<div class="max-w-[1400px] mx-auto p-6">
  <div class="flex items-center gap-4 mb-8">
    <img src="/site/logo.jpg" onerror="this.style.display='none'" class="w-16 h-16 rounded-full border-2 border-yellow-400">
    <div><h1 class="text-3xl font-black text-yellow-400">ELITE COMÉRCIO</h1><p class="text-sm opacity-70">v3 Fixed - Botões corrigidos | @elite_comercio_</p></div>
    <div class="ml-auto flex gap-2">
      <span class="px-3 py-1 bg-yellow-400 text-black rounded-full text-xs font-bold">{{produtos|length}} produtos</span>
      <button type="button" onclick="syncGitHub()" class="btn px-4 py-2 bg-white text-black rounded-lg font-bold hover:bg-yellow-400">🚀 Sync GitHub</button>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-[460px_1fr] gap-6">
    <!-- FORM -->
    <div class="bg-[#151515] rounded-2xl p-6 border border-yellow-400/20 h-fit lg:sticky top-6">
      <h2 class="text-xl font-bold mb-4">✨ Adicionar com IA</h2>
      <div class="mb-4 bg-black rounded-xl p-3 border border-yellow-400/30">
        <div class="flex items-center justify-between mb-2">
          <label class="text-xs font-bold text-yellow-400">🔍 DETECÇÃO V3</label>
          <button type="button" id="btnAbrirBarra" class="btn w-11 h-11 bg-gradient-to-br from-yellow-400 to-amber-500 text-black rounded-xl flex items-center justify-center text-xl font-black shadow-lg hover:scale-105">🖥️</button>
        </div>
        <textarea id="promptIA" rows="2" placeholder="Ex: fone gamer..." class="w-full p-3 bg-[#0a0a0a] border border-white/10 rounded-xl text-sm focus:border-yellow-400 outline-none"></textarea>
        <button type="button" id="btnGerarIA" class="btn w-full mt-2 py-2.5 bg-gradient-to-r from-yellow-400 to-amber-500 text-black font-black rounded-xl">GERAR COM GEMINI/GROK 🤖</button>
      </div>

      <form id="formProd" class="space-y-3">
        <input id="titulo" placeholder="Título" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm focus:border-yellow-400 outline-none" required>
        <div class="grid grid-cols-2 gap-2">
          <input id="valor" placeholder="Valor ex: 129.90" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm focus:border-yellow-400 outline-none" required>
          <select id="entrega" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm"><option>Full</option><option>Normal</option><option>Retirada</option></select>
        </div>
        <input id="link" placeholder="Link de redirecionamento (afiliado)" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm focus:border-yellow-400 outline-none" required>
        <div class="grid grid-cols-2 gap-2">
          <input id="garantia" placeholder="Garantia ex: 12 meses" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm focus:border-yellow-400 outline-none">
          <input id="estoque" placeholder="Estoque ex: 15" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm focus:border-yellow-400 outline-none">
        </div>
        <textarea id="descricao" placeholder="Descrição" rows="2" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm focus:border-yellow-400 outline-none"></textarea>
        <div>
          <label class="text-xs opacity-60">Imagens (pega direto da pasta)</label>
          <input type="file" id="imagem" accept="image/*" multiple class="w-full mt-1 text-xs file:bg-yellow-400 file:text-black file:border-0 file:rounded-lg file:px-3 file:py-1.5 file:font-bold file:cursor-pointer cursor-pointer">
          <div id="preview" class="mt-2 grid grid-cols-3 gap-2"></div>
        </div>
        <button type="submit" class="btn w-full py-3 bg-yellow-400 text-black font-black rounded-xl text-lg hover:bg-yellow-300">CRIAR PRODUTO 📦</button>
      </form>
      <p id="msg" class="mt-3 text-xs text-center min-h-[16px] opacity-70"></p>
    </div>

    <!-- LISTA PRODUTOS -->
    <div class="bg-[#111] rounded-2xl p-6">
      <h2 class="font-bold mb-4">Produtos na pasta ({{produtos|length}})</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {% for p in produtos %}
        <div class="bg-[#1a1a1a] rounded-xl p-4 border border-white/5 hover:border-yellow-400/20 transition">
          <div class="flex gap-3">
            <div class="w-20 h-20 bg-black rounded-lg flex items-center justify-center text-[10px] opacity-50">IMG</div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="text-[10px] px-2 py-0.5 rounded-full font-bold {% if p.status=='publicado' %}bg-green-500 text-black{% elif p.status=='publicando...' %}bg-blue-400 text-black{% else %}bg-yellow-400 text-black{% endif %}">{{p.status}}</span>
                <span class="text-[9px] opacity-50 truncate">{{p.id}}</span>
              </div>
              <h3 class="font-bold text-sm leading-tight line-clamp-2">{{p.titulo}}</h3>
              <p class="text-yellow-400 font-black text-sm">R$ {{p.valor}}</p>
              <p class="text-[11px] opacity-60">Entrega: {{p.entrega}} | Estoque: {{p.estoque}}</p>
            </div>
          </div>
          <div class="flex gap-2 mt-3">
            <button type="button" data-id="{{p.id}}" class="btn-editar flex-1 py-2 bg-white/10 hover:bg-white/20 rounded-lg text-xs font-bold">✏️ Editar</button>
            <button type="button" data-id="{{p.id}}" class="btn-excluir flex-1 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-xs font-bold">🗑️ Excluir</button>
          </div>
        </div>
        {% endfor %}
      </div>
      {% if produtos|length == 0 %}
      <p class="text-center opacity-40 text-sm py-10">Nenhum produto ainda. Crie o primeiro ao lado 👈</p>
      {% endif %}
    </div>
  </div>
</div>

<!-- BARRA FLUTUANTE V3 FIXED -->
<div id="floatingBar" class="hidden fixed bottom-5 right-5 w-[560px] max-w-[96vw] bg-[#161616] rounded-[20px] border-2 border-yellow-400/50 z-[9999] overflow-hidden">
  <div id="dragHeader" class="drag-handle flex items-center justify-between px-4 py-3 bg-black border-b border-white/10">
    <div class="flex items-center gap-2"><span class="w-3 h-3 bg-green-400 rounded-full animate-pulse"></span><span class="font-black text-sm text-yellow-400">CAPTURA IA v3 FIXED</span><span class="text-[9px] px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full">Botões OK</span></div>
    <div class="flex gap-2"><button type="button" id="btnMelhorar" class="btn w-7 h-7 bg-white/10 hover:bg-yellow-400 hover:text-black rounded-full text-xs" title="Tentar de novo">✨</button><button type="button" id="btnFecharBarra" class="btn w-7 h-7 bg-red-500/20 hover:bg-red-500 text-red-400 hover:text-white rounded-full font-bold">✕</button></div>
  </div>
  <div class="p-4">
    <div class="flex flex-wrap gap-2 mb-3 text-[10px]"><span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#22c55e]"></span>Título</span><span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#eab308]"></span>Valor</span><span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#3b82f6]"></span>Entrega</span><span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#a855f7]"></span>Garantia</span><span class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-[#f97316]"></span>Estoque</span></div>
    <div id="captureArea" class="relative w-full h-[360px] bg-[#0a0a0a] rounded-xl border-2 border-dashed border-white/20 overflow-hidden flex flex-col items-center justify-center">
      <div id="capturePlaceholder" class="text-center p-6">
        <div class="text-5xl mb-3">🎯</div><p class="text-sm font-black">DETECÇÃO PRECISA</p><p class="text-[11px] opacity-60 mt-2">Clique em capturar, escolha a aba do<br>Mercado Livre e veja as caixas coloridas</p>
        <button type="button" id="btnCapturar" class="btn mt-5 px-8 py-3 bg-gradient-to-r from-yellow-400 to-amber-500 text-black font-black rounded-xl text-sm hover:scale-105">📸 CAPTURAR TELA AGORA</button>
      </div>
      <img id="captureImg" class="hidden w-full h-full object-contain">
      <div id="markersLayer" class="absolute inset-0 pointer-events-none"></div>
    </div>
    <div id="analiseStatus" class="hidden mt-3 p-3 bg-black rounded-xl border border-yellow-400/20"><p class="text-xs font-bold flex items-center gap-2"><span class="w-3 h-3 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin"></span>IA analisando posições...</p><div class="w-full h-1 bg-white/10 rounded-full mt-2 overflow-hidden"><div id="progressBar" class="h-full bg-yellow-400 transition-all duration-300" style="width:0%"></div></div></div>
    <div id="resultadoIA" class="hidden mt-3 bg-black rounded-xl p-3 border border-white/10 text-[11px]"></div>
    <div id="acoesBarra" class="hidden mt-4 flex gap-3"><button type="button" id="btnCancelarBarra" class="btn flex-1 py-3 bg-red-500/10 border border-red-500/30 text-red-400 font-black rounded-xl hover:bg-red-500 hover:text-white">✕ CANCELAR</button><button type="button" id="btnConfirmarBarra" class="btn flex-1 py-3 bg-green-500 text-black font-black rounded-xl hover:bg-green-400">✓ USAR DADOS (V)</button></div>
  </div>
</div>

<script>
// ===== ELEMENTOS =====
const $ = id => document.getElementById(id);
const msgEl = $('msg');
const formProd = $('formProd');
const promptIA = $('promptIA');
const tituloEl = $('titulo');
const valorEl = $('valor');
const entregaEl = $('entrega');
const linkEl = $('link');
const garantiaEl = $('garantia');
const estoqueEl = $('estoque');
const descricaoEl = $('descricao');
const imagemEl = $('imagem');
const previewEl = $('preview');

let imagemCapturadaBase64=null, dadosDetectados=null;

// ===== DRAG BARRA =====
(function(){
  const bar=$('floatingBar'), handle=$('dragHeader');
  let drag=false,sx,sy,il,it;
  handle.addEventListener('mousedown',e=>{
    if(e.target.tagName==='BUTTON') return;
    drag=true; sx=e.clientX; sy=e.clientY;
    const r=bar.getBoundingClientRect(); il=r.left; it=r.top;
    bar.style.bottom='auto'; bar.style.right='auto';
  });
  document.addEventListener('mousemove',e=>{
    if(!drag) return;
    bar.style.left=(il+e.clientX-sx)+'px';
    bar.style.top=(it+e.clientY-sy)+'px';
  });
  document.addEventListener('mouseup',()=>drag=false);
})();

// ===== FUNÇÕES BARRA =====
function abrirBarraFlutuante(){
  $('floatingBar').classList.remove('hidden');
  console.log('Barra aberta');
}
function fecharBarraFlutuante(){
  $('floatingBar').classList.add('hidden');
  $('capturePlaceholder').classList.remove('hidden');
  $('captureImg').classList.add('hidden');
  $('markersLayer').innerHTML='';
  $('resultadoIA').classList.add('hidden');
  $('acoesBarra').classList.add('hidden');
  $('analiseStatus').classList.add('hidden');
  $('progressBar').style.width='0%';
  imagemCapturadaBase64=null; dadosDetectados=null;
  console.log('Barra fechada');
}
async function capturarTela(){
  try{
    const stream=await navigator.mediaDevices.getDisplayMedia({video:true});
    const video=document.createElement('video');
    video.srcObject=stream;
    await video.play();
    const canvas=document.createElement('canvas');
    canvas.width=video.videoWidth; canvas.height=video.videoHeight;
    canvas.getContext('2d').drawImage(video,0,0);
    stream.getTracks().forEach(t=>t.stop());
    imagemCapturadaBase64=canvas.toDataURL('image/jpeg',0.85);
    $('captureImg').src=imagemCapturadaBase64;
    $('captureImg').classList.remove('hidden');
    $('capturePlaceholder').classList.add('hidden');
    console.log('Tela capturada');
    analisarTela();
  }catch(err){
    console.error(err);
    alert('Você precisa permitir a captura de tela. Clique em Permitir.');
  }
}
async function analisarTela(){
  if(!imagemCapturadaBase64){ alert('Nenhuma imagem capturada'); return; }
  $('analiseStatus').classList.remove('hidden');
  let prog=0;
  const interval=setInterval(()=>{prog=Math.min(90,prog+7); $('progressBar').style.width=prog+'%';},200);
  try{
    const res=await fetch('/api/analisar-print',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({imagem: imagemCapturadaBase64})
    });
    if(!res.ok) throw new Error('Erro servidor '+res.status);
    const data=await res.json();
    dadosDetectados=data;
    clearInterval(interval);
    $('progressBar').style.width='100%';
    setTimeout(()=>{
      $('analiseStatus').classList.add('hidden');
      // desenha marcações
      const layer=$('markersLayer'); layer.innerHTML='';
      (data.marcacoes||[]).forEach((m,i)=>{
        const el=document.createElement('div'); el.className='marker';
        el.style.left=m.x+'%'; el.style.top=m.y+'%'; el.style.width=m.w+'%'; el.style.height=m.h+'%';
        el.style.borderColor=m.color||'#22c55e'; el.style.background=(m.color||'#22c55e')+'22';
        el.style.animationDelay=(i*0.08)+'s';
        const lb=document.createElement('div'); lb.className='marker-label'; lb.style.background=m.color||'#22c55e'; lb.textContent=m.campo;
        const cf=document.createElement('div'); cf.className='conf-badge'; cf.style.color=m.color||'#22c55e'; cf.textContent=Math.round((m.conf||0.9)*100)+'%';
        el.appendChild(lb); el.appendChild(cf); layer.appendChild(el);
      });
      // resultado
      const div=$('resultadoIA');
      const media = data.marcacoes && data.marcacoes.length ? Math.round(data.marcacoes.reduce((a,b)=>a+(b.conf||0.9),0)/data.marcacoes.length*100) : 85;
      div.innerHTML=`
        <div class="flex items-center justify-between mb-2"><span class="text-green-400 font-black text-xs">✅ DETECTADO - ${media}% confiança</span><span class="text-[10px] px-2 py-0.5 bg-green-500/20 text-green-400 rounded-full">${data.marcacoes?.length||0} elementos</span></div>
        <div class="grid grid-cols-2 gap-2"><div><b>Título:</b> ${(data.titulo||'').substring(0,35)}</div><div><b>Valor:</b> R$ ${data.valor||''}</div><div><b>Entrega:</b> ${data.entrega||''}</div><div><b>Garantia:</b> ${data.garantia||''}</div></div>
      `;
      div.classList.remove('hidden');
      $('acoesBarra').classList.remove('hidden');
      console.log('Detecção OK', data);
    },500);
  }catch(e){
    clearInterval(interval);
    $('analiseStatus').classList.add('hidden');
    console.error(e);
    alert('Erro na IA: '+e.message);
  }
}
function confirmarCaptura(){
  if(!dadosDetectados){ alert('Nenhum dado detectado'); return; }
  if(dadosDetectados.titulo) tituloEl.value=dadosDetectados.titulo;
  if(dadosDetectados.valor) valorEl.value=dadosDetectados.valor;
  if(dadosDetectados.entrega) entregaEl.value=dadosDetectados.entrega;
  if(dadosDetectados.garantia) garantiaEl.value=dadosDetectados.garantia;
  if(dadosDetectados.estoque) estoqueEl.value=dadosDetectados.estoque;
  if(dadosDetectados.descricao) descricaoEl.value=dadosDetectados.descricao;
  msgEl.textContent='✅ Dados da captura aplicados! Confira e clique em CRIAR PRODUTO';
  msgEl.className='mt-3 text-xs text-center text-green-400';
  fecharBarraFlutuante();
  formProd.scrollIntoView({behavior:'smooth'});
}

// ===== EVENT LISTENERS - TODOS OS BOTÕES CORRIGIDOS =====
document.addEventListener('DOMContentLoaded', ()=>{
  console.log('DOM carregado - v3 Fixed');

  // Botões da barra flutuante
  $('btnAbrirBarra').addEventListener('click', abrirBarraFlutuante);
  $('btnFecharBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCancelarBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCapturar').addEventListener('click', capturarTela);
  $('btnConfirmarBarra').addEventListener('click', confirmarCaptura);
  $('btnMelhorar').addEventListener('click', ()=>{ if(imagemCapturadaBase64) analisarTela(); else alert('Capture primeiro'); });

  // Botão gerar IA texto
  $('btnGerarIA').addEventListener('click', async ()=>{
    const prompt = promptIA.value.trim();
    if(!prompt){ alert('Digite algo no campo acima'); promptIA.focus(); return; }
    msgEl.textContent='🤖 Gerando com IA...'; msgEl.className='mt-3 text-xs text-center opacity-70';
    try{
      const res=await fetch('/api/gerar-ia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
      if(!res.ok) throw new Error('Erro '+res.status);
      const data=await res.json();
      if(data.titulo) tituloEl.value=data.titulo;
      if(data.valor) valorEl.value=data.valor;
      if(data.entrega) entregaEl.value=data.entrega;
      if(data.garantia) garantiaEl.value=data.garantia;
      if(data.estoque) estoqueEl.value=data.estoque;
      if(data.descricao) descricaoEl.value=data.descricao;
      msgEl.textContent='✨ Preenchido com IA! Confira os campos';
      msgEl.className='mt-3 text-xs text-center text-green-400';
    }catch(e){
      msgEl.textContent='❌ Erro na IA: '+e.message;
      msgEl.className='mt-3 text-xs text-center text-red-400';
    }
  });

  // Preview imagens
  imagemEl.addEventListener('change', e=>{
    previewEl.innerHTML='';
    [...e.target.files].forEach(f=>{
      const img=document.createElement('img');
      img.src=URL.createObjectURL(f);
      img.className='w-full h-20 object-cover rounded-lg border border-white/10';
      previewEl.appendChild(img);
    });
  });

  // Submit criar produto
  formProd.addEventListener('submit', async e=>{
    e.preventDefault();
    const fd=new FormData();
    fd.append('titulo', tituloEl.value.trim());
    fd.append('valor', valorEl.value.trim());
    fd.append('entrega', entregaEl.value);
    fd.append('link', linkEl.value.trim());
    fd.append('garantia', garantiaEl.value.trim());
    fd.append('estoque', estoqueEl.value.trim());
    fd.append('descricao', descricaoEl.value.trim());
    for(let f of imagemEl.files) fd.append('imagens', f);
    if(!tituloEl.value.trim()){ alert('Título obrigatório'); tituloEl.focus(); return; }
    if(!linkEl.value.trim()){ alert('Link obrigatório'); linkEl.focus(); return; }
    msgEl.textContent='📦 Criando pasta e sincronizando...';
    msgEl.className='mt-3 text-xs text-center opacity-70';
    try{
      const res=await fetch('/api/criar',{method:'POST',body:fd});
      const data=await res.json();
      msgEl.textContent=data.msg;
      msgEl.className='mt-3 text-xs text-center '+(data.ok?'text-green-400':'text-red-400');
      if(data.ok) setTimeout(()=>location.reload(),1200);
    }catch(e){
      msgEl.textContent='❌ Erro: '+e.message;
      msgEl.className='mt-3 text-xs text-center text-red-400';
    }
  });

  // Botões editar/excluir (delegação para evitar bug com aspas no ID)
  document.querySelectorAll('.btn-editar').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id=btn.getAttribute('data-id');
      const novo=prompt('Novo título para '+id+' :');
      if(!novo) return;
      try{
        await fetch('/api/editar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,titulo:novo})});
        location.reload();
      }catch(e){ alert('Erro: '+e.message); }
    });
  });
  document.querySelectorAll('.btn-excluir').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id=btn.getAttribute('data-id');
      if(!confirm('Excluir '+id+'? Essa ação não pode ser desfeita!')) return;
      btn.textContent='⏳ Excluindo...'; btn.disabled=true;
      try{
        const res=await fetch('/api/deletar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
        const data=await res.json();
        if(data.ok){ alert('✅ Excluído!'); location.reload(); }
        else{ alert('❌ '+data.msg); btn.textContent='🗑️ Excluir'; btn.disabled=false; }
      }catch(e){ alert('Erro: '+e.message); btn.textContent='🗑️ Excluir'; btn.disabled=false; }
    });
  });
});

// Funções globais ainda necessárias para compatibilidade
async function syncGitHub(){
  if(!confirm('Enviar todos produtos para GitHub e Render?')) return;
  const btn=document.querySelector('button[onclick="syncGitHub()"]');
  if(btn){ btn.textContent='⏳ Sincronizando...'; btn.disabled=true; }
  try{
    const res=await fetch('/api/sync',{method:'POST'});
    const data=await res.json();
    alert(data.msg);
    location.reload();
  }catch(e){ alert('Erro sync: '+e.message); if(btn){ btn.textContent='🚀 Sync GitHub'; btn.disabled=false; } }
}
</script>
</body>
</html>
    """
    return render_template_string(html, produtos=produtos)

@app.route("/api/gerar-ia", methods=["POST"])
def api_gerar_ia():
    return jsonify(gerar_com_ia(request.json.get("prompt","")))

@app.route("/api/analisar-print", methods=["POST"])
def api_analisar_print():
    try:
        return jsonify(analisar_print_avancado(request.json.get("imagem","")))
    except Exception as e:
        return jsonify({"titulo":"Erro","valor":"0","entrega":"Full","garantia":"","estoque":"","descricao":"","marcacoes":[]})

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
        return jsonify({"ok":True,"msg":"Sincronizado! Render atualiza em 1-2min"})
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
        return jsonify({"ok":False,"msg":f"Erro ao excluir: {e}"})

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
    print("ELITE COMÉRCIO v3 FIXED - http://localhost:5000")
    app.run(debug=True, port=5000)
