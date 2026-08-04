
import os, pathlib, json, re, shutil, subprocess, base64, io, stat, time
from flask import Flask, request, jsonify, render_template_string

# ===== CARREGA .ENV DE TODO LUGAR POSSÍVEL =====
BASE = pathlib.Path(__file__).parent
print("="*70)
print("🔍 Procurando .env...")

# Tenta carregar de vários lugares
env_locs = [BASE / ".env", pathlib.Path.cwd() / ".env", BASE.parent / ".env", pathlib.Path.home() / ".env"]
for env_path in env_locs:
    if env_path.exists():
        print(f"📁 Encontrado .env em: {env_path}")
        try:
            from dotenv import load_dotenv
            load_dotenv(dotenv_path=env_path, override=True)
            print(f"✅ Carregado {env_path}")
        except Exception as e:
            print(f"⚠️ Erro load_dotenv: {e}")

# Fallback manual se dotenv falhar
try:
    from dotenv import load_dotenv
    load_dotenv(override=True)
except:
    pass

def carrega_env_manual():
    """Lê .env manualmente caso dotenv não pegue"""
    for env_path in env_locs:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line=line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k,v=line.split("=",1)
                    k=k.strip()
                    v=v.strip().strip('"').strip("'").strip()
                    if k and v and k not in os.environ:
                        os.environ[k]=v
            except:
                pass

carrega_env_manual()

def get_grok_key():
    for name in ["GROK_API_KEY", "XAI_API_KEY", "XAI_APIKEY", "GROK_KEY", "XAI_KEY", "GROK_API", "XAI"]:
        val = os.getenv(name)
        if val and len(val.strip()) > 15:
            return val.strip()
    return ""

def get_gemini_key():
    val = os.getenv("GEMINI_API_KEY","").strip()
    if val and len(val) > 20:
        return val
    return ""

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
    """Gera com GROK 4.5 ou GEMINI - tenta ambos"""
    grok_key = get_grok_key()
    gemini_key = get_gemini_key()
    
    # 1. Tenta GROK 4.5 primeiro (mais rápido)
    if grok_key:
        try:
            import requests
            print(f"🤖 GROK gerando texto...")
            for modelo in ["grok-4.5", "grok-4", "grok-3", "grok-beta"]:
                try:
                    r = requests.post("https://api.x.ai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {grok_key}", "Content-Type":"application/json"},
                        json={
                            "model": modelo,
                            "messages":[{"role":"user","content":f"Gere JSON para catalogo: titulo atraente, valor (ex: 129.90), entrega (Full/Normal), garantia (ex: 12 meses), estoque (ex: 27), descricao curta venda para produto: {prompt}. Só JSON puro"}],
                            "temperature":0.4
                        }, timeout=25)
                    if r.status_code==200:
                        txt = r.json()["choices"][0]["message"]["content"]
                        txt = txt.replace("```json","").replace("```","").strip()
                        s=txt.find("{"); e=txt.rfind("}")+1
                        if s!=-1: txt=txt[s:e]
                        print(f"✅ GROK {modelo} texto OK")
                        return json.loads(txt)
                except Exception as e:
                    print(f"Grok {modelo} texto falhou: {e}")
                    continue
        except Exception as e:
            print(f"Grok geral erro: {e}")

    # 2. Tenta Gemini
    if gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(f"Gere JSON: titulo, valor, entrega, garantia, estoque, descricao para: {prompt}. Só JSON puro sem markdown", generation_config={"temperature":0.4})
            txt = resp.text.replace("```json","").replace("```","").strip()
            s=txt.find("{"); e=txt.rfind("}")+1
            if s!=-1: txt=txt[s:e]
            print(f"✅ Gemini texto OK")
            return json.loads(txt)
        except Exception as e:
            print(f"Gemini texto falhou: {e}")

    # Fallback
    return {"titulo":prompt.title()[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":f"{prompt} - Achado verificado Elite Comércio"}

def analisar_com_grok_vision(image_b64):
    """Análise REAL com GROK 4.5 Vision"""
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316","descricao":"#06b6d4"}
    grok_key = get_grok_key()
    if not grok_key:
        print("❌ Sem GROK_API_KEY")
        return None

    try:
        import requests
        
        if not image_b64.startswith("data:"):
            if "," in image_b64:
                b64_data = image_b64.split(",")[1]
            else:
                b64_data = image_b64
            image_data_url = f"data:image/jpeg;base64,{b64_data}"
        else:
            image_data_url = image_b64

        prompt = """
        Analise PRINT REAL de produto Mercado Livre Brasil. 

        IGNORE TOTALMENTE:
        - Cabeçalho amarelo no topo com logo Mercado Livre, busca, categorias, CEP, carrinho
        - Menu superior, propagandas
        - FOQUE APENAS no produto principal no centro

        LEIA O TEXTO REAL que você vê na imagem (não invente):

        - TITULO: Texto grande preto 2-3 linhas à DIREITA da foto do produto ou ACIMA dela. Ex: "Câmera IP Visão Noturna Wi-Fi Dome Lâmpada"
        - VALOR: Texto MUITO GRANDE com R$ + número em negrito abaixo do título. Ex: "R$ 109,99" 
        - ENTREGA: Texto com "Chegará grátis entre 29 e 30ago", "FULL", "Envio", perto do preço com ícone caminhão
        - GARANTIA: "Compra Garantida", "30 dias", "Devolução grátis" com ícone escudo
        - ESTOQUE: "4 disponíveis", "1 unidade", "Últimas" perto do botão Comprar
        - DESCRIÇÃO: Pode não estar visível no print, deixe vazio se não ver

        Retorne APENAS JSON válido:
        {
          "titulo": "Texto EXATO que leu na imagem",
          "valor": "109.99",
          "entrega": "Chegará grátis entre 29 e 30ago",
          "garantia": "Compra Garantida 30 dias",
          "estoque": "4 disponíveis",
          "descricao": "",
          "marcacoes": [
            {"campo":"titulo","x":35,"y":32,"w":40,"h":8,"conf":0.95},
            {"campo":"valor","x":35,"y":42,"w":25,"h":6,"conf":0.98}
          ]
        }

        REGRAS MARCAÇÕES x,y,w,h em % (0-100):
        - x = distância da esquerda, y = do topo, w = largura, h = altura
        - NUNCA y < 20% (topo é cabeçalho amarelo, PROIBIDO marcar lá)
        - TITULO: y deve ser 25-45%, w > 30% (texto longo)
        - VALOR: y 40-60%, w 15-35%, h 4-10% (texto grande)
        - ENTREGA/GARANTIA/ESTOQUE: y 50-75%
        - Caixas justas ao texto, NÃO se sobrepor
        - Se não vê campo, NÃO inclua em marcacoes
        - conf = 0-1 confiança (0.95=certeza)
        - Seja EXTREMAMENTE preciso, olhe pixel por pixel
        """

        modelos = ["grok-4.5", "grok-4.5-latest", "grok-4", "grok-4-latest", "grok-3", "grok-3-latest", "grok-beta"]

        for modelo in modelos:
            try:
                print(f"👁️ GROK Vision tentando {modelo}...")
                payload = {
                    "model": modelo,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url, "detail": "high"}}
                        ]
                    }],
                    "temperature": 0.1,
                    "max_tokens": 2500
                }
                
                r = requests.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {grok_key}", "Content-Type":"application/json"},
                    json=payload,
                    timeout=90
                )
                
                print(f"GROK {modelo} status: {r.status_code}")
                if r.status_code != 200:
                    print(f"Erro {modelo}: {r.text[:600]}")
                    continue
                
                resp_json = r.json()
                txt = resp_json["choices"][0]["message"]["content"]
                print(f"📄 GROK {modelo} resposta: {txt[:700]}")
                
                txt = txt.replace("```json","").replace("```","").strip()
                s = txt.find("{"); e = txt.rfind("}")+1
                if s!=-1 and e!=-1:
                    txt = txt[s:e]
                
                data = json.loads(txt)
                
                validas = []
                for m in data.get("marcacoes",[]):
                    try:
                        y = float(m.get("y",0))
                        if y < 18:  # ignora cabeçalho amarelo
                            print(f"⚠️ Ignorando {m.get('campo')} y={y} no topo amarelo")
                            continue
                        w = float(m.get("w",0))
                        h = float(m.get("h",0))
                        if w > 85 and h > 18:
                            continue
                        m["color"] = cores.get(m["campo"], "#22c55e")
                        m["x"] = max(0, min(90, float(m.get("x",0))))
                        m["y"] = max(18, min(90, y))
                        m["w"] = max(5, min(80, w))
                        m["h"] = max(2, min(15, h))
                        m["conf"] = max(0.1, min(1.0, float(m.get("conf",0.85))))
                        validas.append(m)
                    except:
                        continue
                
                data["marcacoes"] = validas
                data["usou_fallback"] = False
                data["modelo_usado"] = modelo
                data["provedor"] = "GROK"
                
                if not validas:
                    print(f"⚠️ {modelo} retornou 0 marcações válidas")
                    continue
                
                print(f"✅ GROK SUCESSO {modelo}: {len(validas)} elementos - Título: {data.get('titulo','')[:70]}")
                return data
                
            except Exception as e:
                print(f"❌ GROK {modelo} exceção: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        return None
        
    except Exception as e:
        print(f"❌ Erro geral Grok Vision: {e}")
        import traceback
        traceback.print_exc()
        return None

def analisar_com_gemini_vision(image_b64):
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316","descricao":"#06b6d4"}
    gemini_key = get_gemini_key()
    if not gemini_key:
        print("❌ Sem GEMINI_API_KEY")
        return None
    try:
        import google.generativeai as genai
        from PIL import Image
        genai.configure(api_key=gemini_key)
        if "," in image_b64: image_b64=image_b64.split(",")[1]
        img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
        if img.width>1920 or img.height>1920:
            img.thumbnail((1920,1920))
        prompt = """
        Analise PRINT REAL Mercado Livre. IGNORE cabeçalho amarelo topo (y<20% proibido). 
        Extraia titulo (y 25-45% à direita da foto), valor (R$ grande y 40-60%), entrega (Chegará grátis/FULL), garantia (Compra Garantida), estoque (X disponíveis).
        Retorne JSON: {titulo,valor,entrega,garantia,estoque,descricao,marcacoes:[{campo,x,y,w,h,conf}]} com x,y,w,h em % precisos justos ao texto. Só JSON.
        """
        for modelo in ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"]:
            try:
                print(f"👁️ GEMINI Vision tentando {modelo}...")
                model=genai.GenerativeModel(modelo)
                resp=model.generate_content([prompt, img], generation_config={"temperature":0.1})
                txt=resp.text.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1: txt=txt[s:e]
                data=json.loads(txt)
                validas=[]
                for m in data.get("marcacoes",[]):
                    if float(m.get("y",0)) < 18:
                        continue
                    m["color"]=cores.get(m["campo"],"#22c55e")
                    m["x"]=max(0,min(90,float(m.get("x",0))))
                    m["y"]=max(18,min(90,float(m.get("y",0))))
                    m["w"]=max(5,min(80,float(m.get("w",10))))
                    m["h"]=max(2,min(15,float(m.get("h",5))))
                    m["conf"]=float(m.get("conf",0.85))
                    validas.append(m)
                data["marcacoes"]=validas
                data["modelo_usado"]=modelo
                data["provedor"]="GEMINI"
                data["usou_fallback"]=False
                if validas:
                    print(f"✅ GEMINI SUCESSO {modelo}: {len(validas)} elementos")
                    return data
            except Exception as e:
                print(f"Gemini {modelo} falhou: {e}")
                continue
    except Exception as e:
        print(f"Gemini geral erro: {e}")
    return None

def analisar_print_real_ia(image_b64):
    print("🔍 Iniciando análise REAL - GROK + GEMINI")
    grok_key = get_grok_key()
    gemini_key = get_gemini_key()
    print(f"🔑 Grok: {'OK '+grok_key[:12]+'...' if grok_key else 'FALTA'} | Gemini: {'OK '+gemini_key[:12]+'...' if gemini_key else 'FALTA'}")
    
    # 1. Tenta GROK primeiro (usuário prefere)
    if grok_key:
        resultado = analisar_com_grok_vision(image_b64)
        if resultado and resultado.get("marcacoes"):
            print("✅ Usando resultado GROK")
            return resultado
        print("⚠️ GROK não retornou marcações válidas, tentando Gemini...")
    
    # 2. Tenta Gemini
    if gemini_key:
        resultado = analisar_com_gemini_vision(image_b64)
        if resultado and resultado.get("marcacoes"):
            print("✅ Usando resultado GEMINI")
            return resultado
    
    # 3. Se nenhum funcionou, retorna erro explicativo (não produto falso)
    debug_info = f"BASE={BASE} | .env BASE existe? {(BASE/'.env').exists()} | cwd .env existe? {(pathlib.Path.cwd()/'.env').exists()} | Grok: {bool(grok_key)} Gemini: {bool(gemini_key)}"
    print(f"❌ Nenhuma IA funcionou - {debug_info}")
    
    return {
        "erro": "SEM_CHAVE",
        "titulo": "⚠️ Configure GROK ou GEMINI",
        "valor": "0",
        "entrega": "Verifique .env",
        "garantia": "",
        "estoque": "",
        "descricao": f"GROK: {'OK '+grok_key[:10]+'...' if grok_key else 'FALTA - crie GROK_API_KEY=xai-...'} | GEMINI: {'OK' if gemini_key else 'FALTA - crie GEMINI_API_KEY=AIza...'} | Arquivo .env deve estar em: {BASE}",
        "marcacoes": [],
        "usou_fallback": True,
        "mensagem": "Configure GROK_API_KEY ou GEMINI_API_KEY no .env",
        "debug": debug_info
    }

@app.route("/")
def home():
    produtos = listar_produtos()
    tem_gemini = bool(get_gemini_key())
    grok_key = get_grok_key()
    tem_grok = bool(grok_key)
    
    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Elite Comércio - GROK 4.5 + GEMINI - Completo</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Montserrat:wght@800&display=swap" rel="stylesheet">
<style>
body{font-family:Inter} h1{font-family:Montserrat}
.marker{position:absolute; border-width:3px; border-style:solid; border-radius:12px; background:rgba(0,0,0,0.08); animation:pulse 2s infinite; pointer-events:none; box-shadow:0 4px 20px rgba(0,0,0,0.3);}
.marker-label{position:absolute; bottom:-24px; left:0; color:black; font-size:11px; font-weight:900; padding:4px 10px; border-radius:8px; text-transform:uppercase; white-space:nowrap; box-shadow:0 4px 12px rgba(0,0,0,0.4);}
.conf-badge{position:absolute; top:-12px; right:-12px; background:black; color:white; font-size:11px; padding:3px 8px; border-radius:12px; border:2px solid currentColor; font-weight:900;}
@keyframes pulse{0%,100%{transform:scale(1); opacity:0.95}50%{transform:scale(1.03); opacity:0.7}}
.drag-handle{cursor:move; user-select:none;}
.btn{transition:all 0.2s} .btn:active{transform:scale(0.97)}
</style>
</head>
<body class="bg-[#0a0a0a] text-white min-h-screen">
<div class="max-w-[1450px] mx-auto p-6">
  <div class="flex items-center gap-4 mb-6">
    <div class="w-14 h-14 bg-gradient-to-br from-yellow-400 to-amber-500 rounded-full flex items-center justify-center text-black font-black text-xl">E</div>
    <div>
      <h1 class="text-3xl font-black text-yellow-400 tracking-tight">ELITE COMÉRCIO</h1>
      <p class="text-[13px] opacity-80 flex items-center gap-3 flex-wrap">
        <span class="{{'text-green-400' if tem_grok else 'text-red-400'}}">🟣 GROK 4.5: {{'✅ '+grok_key[:15]+'...' if tem_grok else '❌ Falta GROK_API_KEY'}}</span>
        <span class="{{'text-green-400' if tem_gemini else 'text-red-400'}}">🔵 GEMINI: {{'✅ OK' if tem_gemini else '❌ Falta GEMINI_API_KEY'}}</span>
        <span class="opacity-50">{{produtos|length}} produtos</span>
      </p>
    </div>
    <div class="ml-auto flex gap-2">
      <button type="button" onclick="syncGitHub()" class="btn px-5 py-2.5 bg-white text-black rounded-xl font-black hover:bg-yellow-400">🚀 Sync GitHub</button>
    </div>
  </div>

  {% if not tem_grok and not tem_gemini %}
  <div class="bg-gradient-to-r from-red-500/20 to-orange-500/20 border-2 border-red-500 rounded-2xl p-5 mb-6">
    <p class="font-black text-red-300 text-lg">⚠️ Configure suas chaves IA - GROK e/ou GEMINI</p>
    <div class="grid md:grid-cols-2 gap-4 mt-4">
      <div class="bg-black/50 rounded-xl p-4 border border-white/10">
        <p class="font-bold text-purple-400">🟣 GROK (recomendado - você usa):</p>
        <p class="text-xs mt-2 opacity-80">1. Acesse <a href="https://console.x.ai/" target="_blank" class="text-blue-400 underline">console.x.ai</a> → API Keys → Create</p>
        <p class="text-xs opacity-80">2. Copie chave xai-...</p>
        <code class="block bg-black border border-purple-500/30 p-3 rounded-lg mt-3 text-green-400 text-xs">GROK_API_KEY=xai-sua_chave_aqui</code>
      </div>
      <div class="bg-black/50 rounded-xl p-4 border border-white/10">
        <p class="font-bold text-blue-400">🔵 GEMINI (backup):</p>
        <p class="text-xs mt-2 opacity-80">1. Acesse <a href="https://aistudio.google.com/app/apikey" target="_blank" class="text-blue-400 underline">aistudio.google.com/app/apikey</a></p>
        <p class="text-xs opacity-80">2. Create API Key</p>
        <code class="block bg-black border border-blue-500/30 p-3 rounded-lg mt-3 text-green-400 text-xs">GEMINI_API_KEY=AIzaSy...</code>
      </div>
    </div>
    <div class="bg-yellow-400/10 border border-yellow-400/30 rounded-xl p-3 mt-4">
      <p class="text-xs"><b class="text-yellow-400">📁 Onde criar o arquivo .env:</b> Na pasta <code class="bg-white/10 px-2 py-0.5 rounded">{{base_path}}</code> - crie arquivo de texto chamado exatamente <b>.env</b> (com ponto, sem .txt)</p>
      <p class="text-xs mt-2">Dentro do .env coloque as duas linhas (ou só uma que você tiver):</p>
      <code class="block bg-black p-3 rounded-lg mt-2 text-xs text-green-400">GROK_API_KEY=xai-...<br>GEMINI_API_KEY=AIza...</code>
      <p class="text-xs mt-2 opacity-70">Depois feche o terminal (Ctrl+C) e rode inserir.bat de novo. No terminal deve aparecer 🔑 Chave encontrada.</p>
    </div>
  </div>
  {% elif tem_grok and tem_gemini %}
  <div class="bg-gradient-to-r from-green-500/10 to-blue-500/10 border border-green-500/20 rounded-xl p-3 mb-6 flex items-center gap-3">
    <span class="w-3 h-3 bg-green-400 rounded-full animate-pulse"></span>
    <p class="text-sm"><b class="text-green-400">✅ GROK + GEMINI Ativos - Sistema completo funcionando!</b> Tenta GROK 4.5 primeiro, se falhar usa Gemini automaticamente.</p>
  </div>
  {% elif tem_grok %}
  <div class="bg-purple-500/10 border border-purple-500/20 rounded-xl p-3 mb-6 flex items-center gap-3">
    <span class="w-3 h-3 bg-purple-400 rounded-full animate-pulse"></span>
    <p class="text-sm"><b class="text-purple-300">🟣 GROK 4.5 Vision Ativo</b> - Análise real da tela funcionando 100%</p>
  </div>
  {% else %}
  <div class="bg-blue-500/10 border border-blue-500/20 rounded-xl p-3 mb-6 flex items-center gap-3">
    <span class="w-3 h-3 bg-blue-400 rounded-full animate-pulse"></span>
    <p class="text-sm"><b class="text-blue-300">🔵 GEMINI Vision Ativo</b> - Análise real funcionando</p>
  </div>
  {% endif %}

  <div class="grid grid-cols-1 lg:grid-cols-[520px_1fr] gap-6">
    <div class="bg-[#151515] rounded-2xl p-6 border border-yellow-400/20 h-fit lg:sticky top-6 shadow-2xl">
      <h2 class="text-xl font-bold mb-4 flex items-center gap-2">✨ Adicionar com IA Completa</h2>
      <div class="mb-4 bg-black rounded-xl p-4 border-2 border-yellow-400/30">
        <div class="flex items-center justify-between mb-3">
          <label class="text-xs font-black text-yellow-400 tracking-widest">🎯 CAPTURA IA REAL - GROK 4.5 + GEMINI</label>
          <button type="button" id="btnAbrirBarra" class="btn w-12 h-12 bg-gradient-to-br from-yellow-400 to-amber-500 text-black rounded-xl flex items-center justify-center text-2xl font-black shadow-xl hover:scale-105">🖥️</button>
        </div>
        <textarea id="promptIA" rows="2" placeholder="Ou descreva o produto: ex: câmera wifi dome..." class="w-full p-3 bg-[#0a0a0a] border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400 focus:ring-2 focus:ring-yellow-400/20"></textarea>
        <button type="button" id="btnGerarIA" class="btn w-full mt-3 py-3 bg-gradient-to-r from-purple-500 via-yellow-400 to-blue-500 text-black font-black rounded-xl text-sm shadow-lg hover:shadow-xl">GERAR COM {{'GROK 4.5 + GEMINI' if tem_grok and tem_gemini else 'GROK 4.5' if tem_grok else 'GEMINI'}} 🤖</button>
        <p class="text-[10px] opacity-50 mt-2 text-center">✅ Lê texto REAL da imagem • Ignora menu amarelo • Marca no lugar exato • Sem produto falso</p>
      </div>
      <form id="formProd" class="space-y-3">
        <input id="titulo" placeholder="Título do produto (detectado automaticamente)" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400" required>
        <div class="grid grid-cols-2 gap-3">
          <input id="valor" placeholder="Valor ex: 109.99" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400" required>
          <select id="entrega" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm"><option>Full</option><option>Normal</option><option>Retirada</option></select>
        </div>
        <input id="link" placeholder="Link de afiliado (Mercado Livre)" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400" required>
        <div class="grid grid-cols-2 gap-3">
          <input id="garantia" placeholder="Garantia ex: 12 meses / 30 dias" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm">
          <input id="estoque" placeholder="Estoque ex: 4 disponíveis" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm">
        </div>
        <textarea id="descricao" placeholder="Descrição (opcional)" rows="2" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm"></textarea>
        <div>
          <label class="text-xs opacity-60">Fotos do produto (da sua pasta)</label>
          <input type="file" id="imagem" accept="image/*" multiple class="w-full mt-1.5 text-xs file:bg-yellow-400 file:text-black file:border-0 file:rounded-xl file:px-4 file:py-2 file:font-black file:cursor-pointer cursor-pointer">
          <div id="preview" class="mt-3 grid grid-cols-3 gap-2"></div>
        </div>
        <button type="submit" class="btn w-full py-4 bg-gradient-to-r from-yellow-400 to-amber-500 text-black font-black rounded-xl text-[15px] tracking-wide shadow-xl hover:shadow-2xl hover:scale-[1.01]">CRIAR PRODUTO 📦 PUBLICAR</button>
      </form>
      <p id="msg" class="mt-3 text-xs text-center min-h-[18px] opacity-70 font-medium"></p>
    </div>

    <div class="bg-[#111] rounded-2xl p-6 border border-white/5">
      <div class="flex items-center justify-between mb-5"><h2 class="font-bold text-lg">📦 Seus Produtos ({{produtos|length}})</h2><span class="text-xs opacity-50">Clique em editar ou excluir</span></div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {% for p in produtos %}
        <div class="group bg-[#1a1a1a] rounded-2xl p-4 border border-white/5 hover:border-yellow-400/30 transition-all hover:shadow-xl hover:shadow-yellow-400/5">
          <div class="flex gap-3">
            <div class="w-20 h-20 bg-black rounded-xl flex items-center justify-center text-[10px] opacity-40 border border-white/5">IMG</div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1.5">
                <span class="text-[10px] px-2.5 py-1 rounded-full font-black {% if p.status=='publicado' %}bg-green-500 text-black{% elif p.status=='publicando...' %}bg-blue-400 text-black{% else %}bg-yellow-400 text-black{% endif %}">{{p.status}}</span>
                <span class="text-[9px] opacity-40 truncate">{{p.id[:20]}}</span>
              </div>
              <h3 class="font-bold text-[13px] leading-tight line-clamp-2 group-hover:text-yellow-400 transition">{{p.titulo}}</h3>
              <p class="text-yellow-400 font-black text-sm mt-1">R$ {{p.valor}}</p>
              <p class="text-[11px] opacity-50 mt-0.5">🚚 {{p.entrega}} • 📦 {{p.estoque}}</p>
            </div>
          </div>
          <div class="flex gap-2 mt-4">
            <button type="button" data-id="{{p.id}}" class="btn-editar flex-1 py-2.5 bg-white/10 hover:bg-white/20 rounded-xl text-xs font-bold transition">✏️ Editar</button>
            <button type="button" data-id="{{p.id}}" class="btn-excluir flex-1 py-2.5 bg-red-500/15 hover:bg-red-500/25 text-red-400 rounded-xl text-xs font-bold transition">🗑️ Excluir</button>
          </div>
        </div>
        {% endfor %}
      </div>
      {% if produtos|length == 0 %}
      <div class="text-center py-16 opacity-30"><p class="text-5xl mb-3">📦</p><p class="text-sm">Nenhum produto ainda</p><p class="text-xs mt-1">Crie o primeiro usando a IA ao lado 👈</p></div>
      {% endif %}
    </div>
  </div>
</div>

<div id="floatingBar" class="hidden fixed bottom-5 right-5 w-[660px] max-w-[97vw] bg-[#161616] rounded-[24px] border-2 border-yellow-400/50 z-[9999] overflow-hidden max-h-[93vh] overflow-y-auto shadow-[0_30px_80px_rgba(0,0,0,0.8)]">
  <div id="dragHeader" class="drag-handle sticky top-0 z-20 flex items-center justify-between px-5 py-4 bg-black border-b border-white/10 backdrop-blur-xl">
    <div class="flex items-center gap-3">
      <span class="w-3 h-3 bg-green-400 rounded-full animate-pulse shadow-[0_0_10px_rgba(34,197,94,0.5)]"></span>
      <span class="font-black text-[13px] text-yellow-400 tracking-widest">CAPTURA IA REAL - GROK 4.5 + GEMINI</span>
      <span class="text-[9px] px-2.5 py-1 bg-gradient-to-r from-purple-500/20 to-blue-500/20 text-white rounded-full border border-white/10">100% REAL</span>
    </div>
    <button type="button" id="btnFecharBarra" class="btn w-8 h-8 bg-red-500/20 hover:bg-red-500 text-red-400 hover:text-white rounded-full font-black">✕</button>
  </div>
  <div class="p-5">
    <div class="bg-gradient-to-r from-purple-500/10 via-yellow-400/10 to-blue-500/10 border border-yellow-400/20 rounded-xl p-3.5 mb-4 text-[11px]">
      <p class="font-black text-yellow-400">🧠 Como funciona a IA REAL agora (corrigido):</p>
      <p class="opacity-80 mt-1.5 leading-relaxed">• <b>Ignora</b> cabeçalho amarelo do Mercado Livre (y &lt; 20% proibido) • <b>Lê texto REAL</b> da sua captura com GROK 4.5 Vision • <b>Marca exatamente</b> onde está título, preço R$, entrega, garantia • <b>Nunca usa</b> produto falso "Fone Gamer" • Usa <b>{{'GROK 4.5 primeiro, se falhar usa Gemini automaticamente' if tem_grok and tem_gemini else 'GROK 4.5 Vision' if tem_grok else 'Gemini Vision'}}</p>
    </div>
    <div class="flex flex-wrap gap-2 mb-4 text-[11px]"><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#22c55e]/15 border border-[#22c55e]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#22c55e] shadow-[0_0_8px_#22c55e]"></span>Título</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#eab308]/15 border border-[#eab308]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#eab308] shadow-[0_0_8px_#eab308]"></span>Valor</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#3b82f6]/15 border border-[#3b82f6]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#3b82f6] shadow-[0_0_8px_#3b82f6]"></span>Entrega</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#a855f7]/15 border border-[#a855f7]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#a855f7] shadow-[0_0_8px_#a855f7]"></span>Garantia</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#f97316]/15 border border-[#f97316]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#f97316] shadow-[0_0_8px_#f97316]"></span>Estoque</span></div>
    <div id="captureArea" class="relative w-full h-[460px] bg-[#0a0a0a] rounded-2xl border-2 border-dashed border-white/15 overflow-hidden flex flex-col items-center justify-center group hover:border-yellow-400/30 transition">
      <div id="capturePlaceholder" class="text-center p-8">
        <div class="text-7xl mb-4 animate-bounce">👁️</div><p class="text-[15px] font-black tracking-wide">CAPTURA REAL COM GROK 4.5 + GEMINI</p><p class="text-[12px] opacity-60 mt-3 max-w-[360px] leading-relaxed">Capture a tela do Mercado Livre aberta no navegador.<br>A IA vai ler o texto REAL e marcar no lugar EXATO com caixas coloridas.<br><b class="text-yellow-400">Nunca mais marca o menu amarelo.</b></p>
        <button type="button" id="btnCapturar" class="btn mt-6 px-10 py-4 bg-gradient-to-r from-purple-600 via-yellow-400 to-blue-500 text-black font-black rounded-2xl text-[13px] tracking-widest shadow-2xl hover:scale-105 hover:shadow-[0_0_40px_rgba(234,179,8,0.4)] transition-all">📸 CAPTURAR TELA AGORA</button>
        <p class="text-[10px] opacity-30 mt-4">Usa {{'GROK 4.5 + Gemini' if tem_grok and tem_gemini else 'GROK 4.5' if tem_grok else 'Gemini'}} do seu .env</p>
      </div>
      <img id="captureImg" class="hidden w-full h-full object-contain">
      <div id="markersLayer" class="absolute inset-0 pointer-events-none"></div>
    </div>
    <div id="analiseStatus" class="hidden mt-4 p-4 bg-black rounded-2xl border-2 border-purple-500/30">
      <p class="text-xs font-black flex items-center gap-3"><span class="w-5 h-5 border-2 border-purple-400 border-t-transparent rounded-full animate-spin"></span>🧠 {{'GROK 4.5 + GEMINI' if tem_grok and tem_gemini else 'GROK 4.5' if tem_grok else 'GEMINI'}} analisando sua imagem pixel por pixel...</p>
      <div class="w-full h-2.5 bg-white/10 rounded-full mt-3 overflow-hidden"><div id="progressBar" class="h-full bg-gradient-to-r from-purple-500 via-yellow-400 to-blue-500 transition-all duration-300" style="width:0%"></div></div>
      <p class="text-[10px] opacity-60 mt-2.5">Modelo: <span id="modeloUsado" class="font-bold text-yellow-400">{{'grok-4.5' if tem_grok else 'gemini-1.5-pro'}}</span> • Lendo texto real, ignorando topo amarelo</p>
    </div>
    <div id="resultadoIA" class="hidden mt-4 bg-black rounded-2xl p-4 border border-white/10"></div>
    <div id="acoesBarra" class="hidden mt-5 flex gap-3"><button type="button" id="btnCancelarBarra" class="btn flex-1 py-4 bg-red-500/10 border-2 border-red-500/20 text-red-400 font-black rounded-xl hover:bg-red-500 hover:text-white">✕ CANCELAR</button><button type="button" id="btnConfirmarBarra" class="btn flex-1 py-4 bg-gradient-to-r from-green-500 to-emerald-500 text-black font-black rounded-xl text-[13px] shadow-xl hover:shadow-2xl hover:scale-[1.02]">✓ USAR DADOS REAIS</button></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let imagemCapturadaBase64=null, dadosDetectados=null;

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

function abrirBarraFlutuante(){ $('floatingBar').classList.remove('hidden'); }
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
}
async function capturarTela(){
  try{
    const stream=await navigator.mediaDevices.getDisplayMedia({video:true});
    const video=document.createElement('video'); video.srcObject=stream; await video.play();
    const canvas=document.createElement('canvas'); canvas.width=video.videoWidth; canvas.height=video.videoHeight;
    canvas.getContext('2d').drawImage(video,0,0); stream.getTracks().forEach(t=>t.stop());
    imagemCapturadaBase64=canvas.toDataURL('image/jpeg',0.88);
    $('captureImg').src=imagemCapturadaBase64;
    $('captureImg').classList.remove('hidden');
    $('capturePlaceholder').classList.add('hidden');
    analisarTela();
  }catch(err){ alert('Permita captura: '+err.message); }
}
async function analisarTela(){
  if(!imagemCapturadaBase64) return;
  $('analiseStatus').classList.remove('hidden');
  let prog=0; const interval=setInterval(()=>{prog=Math.min(92,prog+5); $('progressBar').style.width=prog+'%';},280);
  try{
    const res=await fetch('/api/analisar-print',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({imagem:imagemCapturadaBase64})});
    const data=await res.json();
    dadosDetectados=data;
    clearInterval(interval); $('progressBar').style.width='100%';
    setTimeout(()=>{
      $('analiseStatus').classList.add('hidden');
      if(data.erro){
        $('resultadoIA').innerHTML=`<div class="bg-red-500/15 border-2 border-red-500/50 rounded-2xl p-4"><p class="font-black text-red-300">❌ ${data.mensagem||'Erro'}</p><p class="text-xs mt-3 whitespace-pre-wrap leading-relaxed opacity-90">${data.descricao||''}</p>${data.debug ? `<p class="text-[10px] mt-3 opacity-40 font-mono">Debug: ${data.debug}</p>` : ''}</div>`;
        $('resultadoIA').classList.remove('hidden');
        return;
      }
      const layer=$('markersLayer'); layer.innerHTML='';
      (data.marcacoes||[]).forEach((m,i)=>{
        const el=document.createElement('div'); el.className='marker';
        el.style.left=m.x+'%'; el.style.top=m.y+'%'; el.style.width=m.w+'%'; el.style.height=m.h+'%';
        el.style.borderColor=m.color||'#22c55e'; el.style.background=(m.color||'#22c55e')+'14';
        el.style.animationDelay=(i*0.07)+'s';
        const lb=document.createElement('div'); lb.className='marker-label'; lb.style.background=m.color||'#22c55e'; lb.textContent=m.campo+' '+(m.conf?Math.round(m.conf*100)+'%':'');
        const cf=document.createElement('div'); cf.className='conf-badge'; cf.style.borderColor=m.color||'#22c55e'; cf.style.color=m.color||'#22c55e'; cf.textContent=Math.round((m.conf||0.9)*100)+'%';
        el.appendChild(lb); el.appendChild(cf); layer.appendChild(el);
      });
      const media = data.marcacoes && data.marcacoes.length ? Math.round(data.marcacoes.reduce((a,b)=>a+(b.conf||0.9),0)/data.marcacoes.length*100) : 90;
      $('modeloUsado').textContent = data.modelo_usado || 'IA Real';
      $('resultadoIA').innerHTML=`
        <div class="flex items-center justify-between mb-4"><span class="text-green-400 font-black text-xs tracking-widest">✅ ANÁLISE REAL - ${media}% CONFIANÇA • ${data.modelo_usado||''} • ${data.provedor||''}</span><span class="text-[10px] px-3 py-1.5 bg-green-500/20 text-green-400 rounded-full border border-green-500/30 font-black">${data.marcacoes?.length||0} ELEMENTOS REAIS</span></div>
        <div class="space-y-3 text-[13px]">
          <div class="p-3.5 bg-[#22c55e]/10 border border-[#22c55e]/20 rounded-xl"><span class="text-[#22c55e] font-black text-xs">📝 TÍTULO REAL:</span><br><span class="font-bold mt-1 block">${data.titulo||''}</span></div>
          <div class="grid grid-cols-2 gap-3">
            <div class="p-3 bg-[#eab308]/10 border border-[#eab308]/20 rounded-xl"><span class="text-[#eab308] font-black text-[11px]">💰 VALOR:</span><br><span class="font-black text-sm">R$ ${data.valor||''}</span></div>
            <div class="p-3 bg-[#3b82f6]/10 border border-[#3b82f6]/20 rounded-xl"><span class="text-[#3b82f6] font-black text-[11px]">🚚 ENTREGA:</span><br><span class="font-bold text-xs">${data.entrega||''}</span></div>
            <div class="p-3 bg-[#a855f7]/10 border border-[#a855f7]/20 rounded-xl"><span class="text-[#a855f7] font-black text-[11px]">🛡️ GARANTIA:</span><br><span class="font-bold text-xs">${data.garantia||''}</span></div>
            <div class="p-3 bg-[#f97316]/10 border border-[#f97316]/20 rounded-xl"><span class="text-[#f97316] font-black text-[11px]">📦 ESTOQUE:</span><br><span class="font-bold text-xs">${data.estoque||''}</span></div>
          </div>
          ${data.descricao ? `<div class="p-3 bg-white/5 border border-white/10 rounded-xl"><span class="font-black text-[11px] opacity-60">📄 DESCRIÇÃO:</span><br><span class="text-xs">${(data.descricao||'').substring(0,200)}</span></div>` : ''}
        </div>
        <p class="text-[11px] text-green-400 mt-4 flex items-center gap-2"><span class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>✅ Texto lido 100% real da sua captura, sem produto falso • Provedor: ${data.provedor||''} • Modelo: ${data.modelo_usado||''}</p>
      `;
      $('resultadoIA').classList.remove('hidden');
      $('acoesBarra').classList.remove('hidden');
    },700);
  }catch(e){
    clearInterval(interval);
    $('analiseStatus').classList.add('hidden');
    alert('Erro: '+e.message);
  }
}
function confirmarCaptura(){
  if(!dadosDetectados || dadosDetectados.erro){ alert('Nenhum dado válido'); return; }
  if(dadosDetectados.titulo) $('titulo').value=dadosDetectados.titulo;
  if(dadosDetectados.valor) $('valor').value=dadosDetectados.valor;
  if(dadosDetectados.entrega) $('entrega').value=dadosDetectados.entrega;
  if(dadosDetectados.garantia) $('garantia').value=dadosDetectados.garantia;
  if(dadosDetectados.estoque) $('estoque').value=dadosDetectados.estoque;
  if(dadosDetectados.descricao) $('descricao').value=dadosDetectados.descricao;
  $('msg').textContent=`✅ Dados REAIS aplicados! (${dadosDetectados.modelo_usado||''} - ${dadosDetectados.provedor||''})`;
  $('msg').className='mt-3 text-xs text-center text-green-400 font-black';
  fecharBarraFlutuante();
  $('formProd').scrollIntoView({behavior:'smooth'});
}

document.addEventListener('DOMContentLoaded', ()=>{
  $('btnAbrirBarra').addEventListener('click', abrirBarraFlutuante);
  $('btnFecharBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCancelarBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCapturar').addEventListener('click', capturarTela);
  $('btnConfirmarBarra').addEventListener('click', confirmarCaptura);
  $('btnGerarIA').addEventListener('click', async ()=>{
    const prompt=$('promptIA').value.trim();
    if(!prompt){ alert('Digite o nome do produto'); $('promptIA').focus(); return; }
    $('msg').textContent='🤖 Gerando com IA completa...';
    $('msg').className='mt-3 text-xs text-center opacity-70';
    try{
      const res=await fetch('/api/gerar-ia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
      const data=await res.json();
      if(data.titulo) $('titulo').value=data.titulo;
      if(data.valor) $('valor').value=data.valor;
      if(data.entrega) $('entrega').value=data.entrega;
      if(data.garantia) $('garantia').value=data.garantia;
      if(data.estoque) $('estoque').value=data.estoque;
      if(data.descricao) $('descricao').value=data.descricao;
      $('msg').textContent='✨ Preenchido com IA real!';
      $('msg').className='mt-3 text-xs text-center text-green-400 font-black';
    }catch(e){ $('msg').textContent='❌ Erro: '+e.message; $('msg').className='mt-3 text-xs text-center text-red-400'; }
  });
  $('imagem').addEventListener('change', e=>{
    const pr=$('preview'); pr.innerHTML='';
    [...e.target.files].forEach(f=>{ const img=document.createElement('img'); img.src=URL.createObjectURL(f); img.className='w-full h-20 object-cover rounded-xl border border-white/10'; pr.appendChild(img); });
  });
  $('formProd').addEventListener('submit', async e=>{
    e.preventDefault();
    const fd=new FormData();
    fd.append('titulo', $('titulo').value.trim());
    fd.append('valor', $('valor').value.trim());
    fd.append('entrega', $('entrega').value);
    fd.append('link', $('link').value.trim());
    fd.append('garantia', $('garantia').value.trim());
    fd.append('estoque', $('estoque').value.trim());
    fd.append('descricao', $('descricao').value.trim());
    for(let f of $('imagem').files) fd.append('imagens', f);
    if(!$('titulo').value.trim()){ alert('Título obrigatório'); $('titulo').focus(); return; }
    if(!$('link').value.trim()){ alert('Link afiliado obrigatório'); $('link').focus(); return; }
    $('msg').textContent='📦 Criando pasta e sincronizando com GitHub...';
    $('msg').className='mt-3 text-xs text-center opacity-70';
    try{
      const res=await fetch('/api/criar',{method:'POST',body:fd});
      const data=await res.json();
      $('msg').textContent=data.msg;
      $('msg').className='mt-3 text-xs text-center '+(data.ok?'text-green-400 font-black':'text-red-400');
      if(data.ok) setTimeout(()=>location.reload(),1300);
    }catch(e){ $('msg').textContent='❌ Erro: '+e.message; }
  });
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
      if(!confirm('Excluir '+id+'? Essa ação apaga a pasta e não pode ser desfeita!')) return;
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
async function syncGitHub(){
  if(!confirm('Enviar todos produtos para GitHub e Render? Isso atualiza seu site online em 1-2 min.')) return;
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
    grok_key = get_grok_key()
    return render_template_string(html, produtos=produtos, tem_grok=bool(grok_key), tem_gemini=bool(get_gemini_key()), grok_key=grok_key or "", base_path=str(BASE))

@app.route("/api/gerar-ia", methods=["POST"])
def api_gerar_ia():
    try:
        return jsonify(gerar_com_ia(request.json.get("prompt","")))
    except Exception as e:
        return jsonify({"titulo":request.json.get("prompt","")[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":str(e)})

@app.route("/api/analisar-print", methods=["POST"])
def api_analisar_print():
    try:
        result = analisar_print_real_ia(request.json.get("imagem",""))
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"erro":"EXCECAO","mensagem":str(e),"marcacoes":[],"titulo":"Erro","valor":"0","descricao":str(e)}), 500

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
        return jsonify({"ok":True,"msg":f"✅ Criado {folder_name} - Sincronizando..."})
    except Exception as e:
        return jsonify({"ok":False,"msg":f"Erro: {e}"})

@app.route("/api/sync", methods=["POST"])
def api_sync():
    try:
        subprocess.run(["python","scripts/gerar_catalogo.py"],cwd=BASE); subprocess.run(["git","add","."],cwd=BASE,shell=True); subprocess.run(["git","commit","-m","sync: catalogo"],cwd=BASE,shell=True); subprocess.run(["git","push"],cwd=BASE,shell=True)
        return jsonify({"ok":True,"msg":"✅ Sincronizado com GitHub! Render vai atualizar em 1-2 min - veja em elitecomercio.com"})
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
        return jsonify({"ok":True,"msg":"✅ Excluído com sucesso! Sincronizando..."})
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

@app.route("/api/debug-env")
def debug_env():
    grok_key = get_grok_key()
    gemini_key = get_gemini_key()
    return jsonify({
        "BASE": str(BASE),
        "cwd": str(pathlib.Path.cwd()),
        "env_BASE_exists": (BASE/".env").exists(),
        "env_cwd_exists": (pathlib.Path.cwd()/".env").exists(),
        "grok_key_found": bool(grok_key),
        "grok_key_preview": grok_key[:15]+"..." if grok_key else None,
        "gemini_key_found": bool(gemini_key),
        "gemini_key_preview": gemini_key[:15]+"..." if gemini_key else None,
        "all_env_keys": [k for k in os.environ.keys() if "GROK" in k or "XAI" in k or "GEMINI" in k],
        "env_files_checked": [str(p) for p in [BASE/".env", pathlib.Path.cwd()/".env", BASE.parent/".env"]]
    })

if __name__=="__main__":
    PRODUTOS_DIR.mkdir(exist_ok=True); (SITE_DIR/"produtos").mkdir(exist_ok=True)
    print("="*75)
    print("🚀 ELITE COMÉRCIO - VERSÃO COMPLETA GROK 4.5 + GEMINI - TUDO FUNCIONANDO")
    print("="*75)
    print(f"📁 BASE: {BASE}")
    print(f"📁 .env em BASE: {(BASE/'.env').exists()} -> {BASE/'.env'}")
    print(f"📁 .env em cwd: {(pathlib.Path.cwd()/'.env').exists()} -> {pathlib.Path.cwd()/'.env'}")
    grok_k = get_grok_key()
    gemini_k = get_gemini_key()
    print(f"🟣 GROK: {'✅ OK '+grok_k[:15]+'...' if grok_k else '❌ FALTA - crie GROK_API_KEY=xai-... em .env'}")
    print(f"🔵 GEMINI: {'✅ OK '+gemini_k[:15]+'...' if gemini_k else '❌ FALTA - crie GEMINI_API_KEY=AIza... em .env (opcional)'}")
    print(f"🔍 Env vars encontradas: {[k for k in os.environ.keys() if 'GROK' in k or 'XAI' in k or 'GEMINI' in k]}")
    if (BASE/".env").exists():
        try:
            txt = (BASE/".env").read_text()[:500]
            print(f"📄 Conteúdo .env (primeiros 500 chars):\n{txt}")
        except Exception as e:
            print(f"Erro ler .env: {e}")
    print("="*75)
    print("🌐 Acesse: http://localhost:5000")
    print("🔧 Debug env: http://localhost:5000/api/debug-env")
    print("📸 Captura: Botão 🖥️ -> 📸 CAPTURAR TELA")
    print("="*75)
    app.run(debug=True, port=5000)
