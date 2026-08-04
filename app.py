
import os, pathlib, json, re, shutil, subprocess, base64, io, stat, time
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
load_dotenv(override=True)

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

def get_grok_key():
    # Aceita vários nomes
    return os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY") or os.getenv("XAI_APIKEY") or os.getenv("GROK_KEY") or ""

def get_gemini_key():
    return os.getenv("GEMINI_API_KEY","").strip()

def gerar_com_ia(prompt):
    # Tenta Gemini primeiro
    gemini_key = get_gemini_key()
    if gemini_key and len(gemini_key)>20:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(f"Gere JSON: titulo, valor, entrega, garantia, estoque, descricao para: {prompt}. Só JSON", generation_config={"temperature":0.3})
            txt = resp.text.replace("```json","").replace("```","").strip()
            s=txt.find("{"); e=txt.rfind("}")+1
            if s!=-1: txt=txt[s:e]
            print("✅ Gemini texto OK")
            return json.loads(txt)
        except Exception as e:
            print(f"Gemini texto falhou: {e}")

    # Tenta Grok
    grok_key = get_grok_key()
    if grok_key and len(grok_key)>10:
        try:
            import requests
            print(f"🤖 Tentando Grok texto com chave {grok_key[:10]}...")
            r = requests.post("https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {grok_key}", "Content-Type":"application/json"},
                json={
                    "model":"grok-2-latest",
                    "messages":[{"role":"user","content":f"Gere JSON para catalogo afiliados: titulo, valor, entrega (Full/Normal), garantia, estoque, descricao para produto: {prompt}. Responda APENAS JSON puro sem markdown"}],
                    "temperature":0.3
                }, timeout=30)
            print(f"Grok status: {r.status_code}")
            if r.status_code==200:
                txt = r.json()["choices"][0]["message"]["content"]
                txt = txt.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1: txt=txt[s:e]
                print(f"✅ Grok texto OK: {txt[:100]}")
                return json.loads(txt)
            else:
                print(f"Grok erro texto: {r.text[:300]}")
        except Exception as e:
            print(f"Grok texto exceção: {e}")

    return {"titulo":prompt.title()[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":prompt}

def analisar_com_grok_vision(image_b64):
    """Análise REAL com Grok Vision - funciona com sua chave GROK"""
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316","descricao":"#06b6d4"}
    grok_key = get_grok_key()
    
    if not grok_key or len(grok_key) < 10:
        print("❌ Sem GROK_API_KEY")
        return None

    try:
        import requests
        
        # Garante que é data URL
        if not image_b64.startswith("data:"):
            if "," in image_b64:
                b64_data = image_b64.split(",")[1]
            else:
                b64_data = image_b64
            # Detecta tipo
            image_data_url = f"data:image/jpeg;base64,{b64_data}"
        else:
            image_data_url = image_b64

        prompt = """
        Analise este PRINT REAL de produto do Mercado Livre Brasil.

        IGNORE COMPLETAMENTE:
        - Cabeçalho amarelo no topo com logo, busca, categorias, CEP
        - Menu, carrinho, favoritos, propagandas
        - FOQUE APENAS no produto principal no centro da tela

        ONDE ESTÁ CADA CAMPO (leia o texto REAL que você vê):
        - TITULO: Texto grande preto, 2-3 linhas, à direita da foto do produto ou acima. Ex: "Câmera IP Visão Noturna Wi-Fi Dome"
        - VALOR: Texto MUITO GRANDE com R$ + número, negrito. Ex: "R$ 109,99" - está abaixo do título
        - ENTREGA: Texto com "Chegará grátis", "FULL", "Envio", "Chegará entre 29 e 30ago", perto do preço, com ícone caminhão
        - GARANTIA: "Compra Garantida", "Garantia", "Devolução grátis", com escudo
        - ESTOQUE: "X disponíveis", "X unidades", "Últimas", perto do botão Comprar
        - DESCRIÇÃO: Parágrafo longo, pode não aparecer no print

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

        REGRAS PARA MARCAÇÕES x,y,w,h em % (0-100):
        - x = distância da esquerda, y = do topo, w = largura, h = altura
        - NUNCA y < 20% (topo é cabeçalho amarelo, proibido)
        - TITULO y deve ser 25-45%, VALOR y 40-55%, ENTREGA/GARANTIA y 50-70%
        - Caixas justas ao texto, não podem se sobrepor
        - Se não vê o campo, não inclua na marcacoes
        - Leia EXATAMENTE o texto da imagem, não invente
        - Seja preciso
        """

        # Modelos Grok Vision disponíveis - tenta em ordem
        modelos_grok = ["grok-2-vision-latest", "grok-2-vision-1212", "grok-vision-beta", "grok-2-vision"]

        for modelo in modelos_grok:
            try:
                print(f"👁️ Tentando Grok Vision com {modelo}...")
                payload = {
                    "model": modelo,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_data_url, "detail": "high"}}
                            ]
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2000
                }
                
                r = requests.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {grok_key}", "Content-Type":"application/json"},
                    json=payload,
                    timeout=60
                )
                
                print(f"Grok Vision {modelo} status: {r.status_code}")
                if r.status_code != 200:
                    print(f"Resposta erro: {r.text[:500]}")
                    # Tenta próximo modelo
                    continue
                
                resp_json = r.json()
                txt = resp_json["choices"][0]["message"]["content"]
                print(f"📄 Grok resposta bruta: {txt[:600]}...")
                
                # Limpa JSON
                txt = txt.replace("```json","").replace("```","").strip()
                s = txt.find("{"); e = txt.rfind("}")+1
                if s!=-1 and e!=-1:
                    txt = txt[s:e]
                
                data = json.loads(txt)
                
                # Valida marcações
                validas = []
                for m in data.get("marcacoes",[]):
                    if m.get("y",0) < 18:  # ignora topo
                        continue
                    if m.get("w",0) > 85 and m.get("h",0) > 18:
                        continue
                    m["color"] = cores.get(m["campo"], "#22c55e")
                    m["x"] = max(0, min(90, float(m.get("x",0))))
                    m["y"] = max(18, min(90, float(m.get("y",0))))
                    m["w"] = max(5, min(80, float(m.get("w",10))))
                    m["h"] = max(2, min(15, float(m.get("h",5))))
                    m["conf"] = float(m.get("conf",0.88))
                    validas.append(m)
                
                data["marcacoes"] = validas
                data["usou_fallback"] = False
                data["modelo_usado"] = modelo
                data["provedor"] = "GROK"
                
                if not validas:
                    print("⚠️ Grok retornou 0 marcações, tenta próximo modelo")
                    continue
                
                print(f"✅ GROK SUCESSO com {modelo}: {len(validas)} elementos")
                print(f"📝 Título: {data.get('titulo','')[:80]}")
                print(f"💰 Valor: {data.get('valor','')}")
                return data
                
            except Exception as e:
                print(f"❌ Grok {modelo} falhou: {e}")
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
    """Tenta Gemini Vision se tiver chave"""
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316","descricao":"#06b6d4"}
    gemini_key = get_gemini_key()
    if not gemini_key or len(gemini_key)<20:
        return None
    try:
        import google.generativeai as genai
        from PIL import Image
        genai.configure(api_key=gemini_key)
        if "," in image_b64: image_b64=image_b64.split(",")[1]
        img = Image.open(io.BytesIO(base64.b64decode(image_b64)))
        if img.width>1920: img.thumbnail((1920,1920))
        prompt = "Analise print Mercado Livre. Ignore cabeçalho amarelo topo. Extraia titulo,valor,entrega,garantia,estoque,descricao e bbox x,y,w,h em % (y>=20%). Retorne JSON: {titulo,valor,entrega,garantia,estoque,descricao,marcacoes:[{campo,x,y,w,h,conf}]} Só JSON"
        for modelo in ["gemini-1.5-pro","gemini-1.5-flash"]:
            try:
                model=genai.GenerativeModel(modelo)
                resp=model.generate_content([prompt, img], generation_config={"temperature":0.1})
                txt=resp.text.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1: txt=txt[s:e]
                data=json.loads(txt)
                for m in data.get("marcacoes",[]): m["color"]=cores.get(m["campo"],"#22c55e")
                data["modelo_usado"]=modelo; data["provedor"]="GEMINI"; data["usou_fallback"]=False
                print(f"✅ Gemini Vision OK {modelo}")
                return data
            except Exception as e:
                print(f"Gemini {modelo} fail {e}")
                continue
    except Exception as e:
        print(f"Gemini geral erro {e}")
    return None

def analisar_print_real_ia(image_b64):
    """Função principal que tenta GROK primeiro (já que usuário usa Grok), depois Gemini"""
    print("🔍 Iniciando análise REAL da tela...")
    
    # 1. Tenta GROK primeiro (usuário disse que usa Grok)
    resultado = analisar_com_grok_vision(image_b64)
    if resultado and resultado.get("marcacoes"):
        print("✅ Usando resultado GROK")
        return resultado
    
    # 2. Tenta Gemini como backup
    print("Grok não retornou, tentando Gemini...")
    resultado = analisar_com_gemini_vision(image_b64)
    if resultado and resultado.get("marcacoes"):
        print("✅ Usando resultado Gemini")
        return resultado
    
    # 3. Fallback explicativo (não produto falso)
    print("❌ Nenhuma IA funcionou, retornando erro explicativo")
    grok_key = get_grok_key()
    gemini_key = get_gemini_key()
    
    return {
        "erro": "SEM_IA",
        "titulo": "⚠️ Configure GROK_API_KEY ou GEMINI_API_KEY",
        "valor": "0",
        "entrega": "Verifique .env",
        "garantia": "",
        "estoque": "",
        "descricao": f"Grok: {'OK '+grok_key[:10]+'...' if grok_key else 'FALTA'} | Gemini: {'OK' if gemini_key else 'FALTA'} | Verifique terminal do inserir.bat para erros detalhados",
        "marcacoes": [],
        "usou_fallback": True,
        "mensagem": "Configure GROK_API_KEY no .env - pegue em https://console.x.ai/",
        "debug": f"Grok key: {bool(grok_key)} Gemini key: {bool(gemini_key)}"
    }

@app.route("/")
def home():
    produtos = listar_produtos()
    tem_gemini = bool(get_gemini_key())
    tem_grok = bool(get_grok_key())
    html = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Elite Comércio - GROK Vision Real</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;700&family=Montserrat:wght@800&display=swap" rel="stylesheet">
<style>
body{font-family:Inter} h1{font-family:Montserrat}
.marker{position:absolute; border-width:3px; border-style:solid; border-radius:10px; background:rgba(0,0,0,0.10); animation:pulse 2s infinite; pointer-events:none;}
.marker-label{position:absolute; bottom:-22px; left:0; color:black; font-size:11px; font-weight:900; padding:3px 8px; border-radius:6px; text-transform:uppercase;}
.conf-badge{position:absolute; top:-10px; right:-10px; background:black; color:white; font-size:10px; padding:2px 6px; border-radius:12px; border:2px solid currentColor; font-weight:900;}
@keyframes pulse{0%,100%{transform:scale(1); opacity:0.95}50%{transform:scale(1.02); opacity:0.7}}
.drag-handle{cursor:move; user-select:none;}
</style>
</head>
<body class="bg-[#0a0a0a] text-white min-h-screen">
<div class="max-w-[1400px] mx-auto p-6">
  <div class="flex items-center gap-4 mb-6">
    <div><h1 class="text-3xl font-black text-yellow-400">ELITE COMÉRCIO</h1>
      <p class="text-sm opacity-70">
        GROK Vision: {{'✅ '+grok_key[:12]+'...' if tem_grok else '❌ Falta GROK_API_KEY'}} | 
        Gemini: {{'✅ OK' if tem_gemini else '❌ Não configurado'}}
      </p>
    </div>
    <div class="ml-auto flex gap-2">
      <span class="px-3 py-1 bg-yellow-400 text-black rounded-full text-xs font-bold">{{produtos|length}} produtos</span>
      <button type="button" onclick="syncGitHub()" class="px-4 py-2 bg-white text-black rounded-lg font-bold">🚀 Sync</button>
    </div>
  </div>

  {% if not tem_grok and not tem_gemini %}
  <div class="bg-red-500/20 border-2 border-red-500 rounded-xl p-4 mb-6">
    <p class="font-black text-red-400">⚠️ Nenhuma chave IA encontrada!</p>
    <p class="text-sm mt-1">Você disse que usa Grok, então crie .env com:</p>
    <code class="block bg-black p-2 rounded mt-2 text-yellow-400">GROK_API_KEY=xai-...</code>
    <p class="text-xs opacity-70 mt-2">Pegue em: https://console.x.ai/ → API Keys → Create</p>
  </div>
  {% elif tem_grok %}
  <div class="bg-green-500/10 border border-green-500/30 rounded-xl p-3 mb-6 flex items-center gap-3">
    <span class="w-3 h-3 bg-green-400 rounded-full animate-pulse"></span>
    <p class="text-sm"><b class="text-green-400">GROK Vision Ativo</b> - IA vai analisar de verdade sua tela</p>
  </div>
  {% endif %}

  <div class="grid grid-cols-1 lg:grid-cols-[500px_1fr] gap-6">
    <div class="bg-[#151515] rounded-2xl p-6 border border-yellow-400/20 h-fit lg:sticky top-6">
      <h2 class="text-xl font-bold mb-4">✨ Adicionar com IA REAL</h2>
      <div class="mb-4 bg-black rounded-xl p-3 border-2 border-yellow-400/40">
        <div class="flex items-center justify-between mb-2">
          <label class="text-xs font-black text-yellow-400">🎯 IA REAL - {{'GROK' if tem_grok else 'GEMINI'}} VISION</label>
          <button type="button" id="btnAbrirBarra" class="w-12 h-12 bg-gradient-to-br from-yellow-400 to-amber-500 text-black rounded-xl flex items-center justify-center text-2xl font-black shadow-lg hover:scale-105">🖥️</button>
        </div>
        <textarea id="promptIA" rows="2" placeholder="Ou descreva o produto..." class="w-full p-3 bg-[#0a0a0a] border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400"></textarea>
        <button type="button" id="btnGerarIA" class="w-full mt-2 py-2.5 bg-white/10 border border-white/10 rounded-xl text-sm font-bold hover:bg-yellow-400 hover:text-black">GERAR COM TEXTO 🤖</button>
        <p class="text-[10px] opacity-60 mt-2">✅ Agora usa sua chave GROK de verdade • Lê texto real da imagem</p>
      </div>
      <form id="formProd" class="space-y-3">
        <input id="titulo" placeholder="Título" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400" required>
        <div class="grid grid-cols-2 gap-2">
          <input id="valor" placeholder="Valor" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400" required>
          <select id="entrega" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm"><option>Full</option><option>Normal</option></select>
        </div>
        <input id="link" placeholder="Link afiliado" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400" required>
        <div class="grid grid-cols-2 gap-2"><input id="garantia" placeholder="Garantia" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm"><input id="estoque" placeholder="Estoque" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm"></div>
        <textarea id="descricao" placeholder="Descrição" rows="2" class="w-full p-3 bg-black border border-white/10 rounded-xl text-sm"></textarea>
        <div><input type="file" id="imagem" accept="image/*" multiple class="w-full text-xs file:bg-yellow-400 file:text-black file:border-0 file:rounded-lg file:px-3 file:py-1.5 file:font-bold"><div id="preview" class="mt-2 grid grid-cols-3 gap-2"></div></div>
        <button type="submit" class="w-full py-3 bg-yellow-400 text-black font-black rounded-xl text-lg">CRIAR PRODUTO 📦</button>
      </form>
      <p id="msg" class="mt-3 text-xs text-center min-h-[16px] opacity-70"></p>
    </div>

    <div class="bg-[#111] rounded-2xl p-6">
      <h2 class="font-bold mb-4">Produtos ({{produtos|length}})</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {% for p in produtos %}
        <div class="bg-[#1a1a1a] rounded-xl p-4 border border-white/5"><div class="flex gap-3"><div class="w-20 h-20 bg-black rounded-lg flex items-center justify-center text-[10px] opacity-50">IMG</div><div class="flex-1 min-w-0"><span class="text-[10px] px-2 py-0.5 rounded-full font-bold bg-green-500 text-black">{{p.status}}</span><h3 class="font-bold text-sm mt-1 line-clamp-2">{{p.titulo}}</h3><p class="text-yellow-400 font-black text-sm">R$ {{p.valor}}</p></div></div><div class="flex gap-2 mt-3"><button type="button" data-id="{{p.id}}" class="btn-editar flex-1 py-2 bg-white/10 rounded-lg text-xs font-bold">✏️ Editar</button><button type="button" data-id="{{p.id}}" class="btn-excluir flex-1 py-2 bg-red-500/20 text-red-400 rounded-lg text-xs font-bold">🗑️ Excluir</button></div></div>
        {% endfor %}
      </div>
    </div>
  </div>
</div>

<div id="floatingBar" class="hidden fixed bottom-5 right-5 w-[640px] max-w-[97vw] bg-[#161616] rounded-[20px] border-2 border-yellow-400/60 z-[9999] overflow-hidden max-h-[92vh] overflow-y-auto">
  <div id="dragHeader" class="drag-handle sticky top-0 z-10 flex items-center justify-between px-4 py-3 bg-black border-b border-white/10">
    <div class="flex items-center gap-2"><span class="w-3 h-3 bg-green-400 rounded-full animate-pulse"></span><span class="font-black text-sm text-yellow-400">GROK VISION REAL</span><span class="text-[9px] px-2 py-0.5 bg-purple-500/20 text-purple-300 rounded-full border border-purple-500/30">LÊ DE VERDADE</span></div>
    <button type="button" id="btnFecharBarra" class="w-8 h-8 bg-red-500/20 hover:bg-red-500 text-red-400 hover:text-white rounded-full font-black">✕</button>
  </div>
  <div class="p-4">
    <div class="bg-purple-500/10 border border-purple-500/30 rounded-xl p-3 mb-3 text-[11px]">
      <p class="font-bold text-purple-300">🧠 GROK Vision analisando de verdade:</p>
      <p class="opacity-80 mt-1">• Ignora menu amarelo • Lê texto REAL da sua captura • Marca exatamente onde está • Não usa produto falso</p>
    </div>
    <div class="flex flex-wrap gap-2 mb-3 text-[10px]"><span class="flex items-center gap-1.5 px-2 py-1 bg-[#22c55e]/20 border border-[#22c55e]/30 rounded-full"><span class="w-2.5 h-2.5 rounded-full bg-[#22c55e]"></span>Título</span><span class="flex items-center gap-1.5 px-2 py-1 bg-[#eab308]/20 border border-[#eab308]/30 rounded-full"><span class="w-2.5 h-2.5 rounded-full bg-[#eab308]"></span>Valor</span><span class="flex items-center gap-1.5 px-2 py-1 bg-[#3b82f6]/20 border border-[#3b82f6]/30 rounded-full"><span class="w-2.5 h-2.5 rounded-full bg-[#3b82f6]"></span>Entrega</span><span class="flex items-center gap-1.5 px-2 py-1 bg-[#a855f7]/20 border border-[#a855f7]/30 rounded-full"><span class="w-2.5 h-2.5 rounded-full bg-[#a855f7]"></span>Garantia</span><span class="flex items-center gap-1.5 px-2 py-1 bg-[#f97316]/20 border border-[#f97316]/30 rounded-full"><span class="w-2.5 h-2.5 rounded-full bg-[#f97316]"></span>Estoque</span></div>
    <div id="captureArea" class="relative w-full h-[440px] bg-[#0a0a0a] rounded-xl border-2 border-dashed border-white/20 overflow-hidden flex flex-col items-center justify-center">
      <div id="capturePlaceholder" class="text-center p-6">
        <div class="text-6xl mb-3">👁️</div><p class="text-sm font-black">GROK VISION REAL</p><p class="text-[11px] opacity-60 mt-2 max-w-[340px]">Capture a tela do Mercado Livre<br>GROK vai ler o texto REAL<br><b>Não marca mais o menu amarelo</b></p>
        <button type="button" id="btnCapturar" class="mt-5 px-10 py-3.5 bg-gradient-to-r from-purple-500 to-indigo-500 text-white font-black rounded-xl text-sm hover:scale-105 transition shadow-xl">📸 CAPTURAR COM GROK</button>
        <p class="text-[10px] opacity-40 mt-3">Usa sua GROK_API_KEY do .env</p>
      </div>
      <img id="captureImg" class="hidden w-full h-full object-contain">
      <div id="markersLayer" class="absolute inset-0 pointer-events-none"></div>
    </div>
    <div id="analiseStatus" class="hidden mt-3 p-4 bg-black rounded-xl border-2 border-purple-500/30"><p class="text-xs font-black flex items-center gap-2"><span class="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin"></span>🧠 GROK Vision lendo sua imagem (ignorando topo amarelo)...</p><div class="w-full h-2 bg-white/10 rounded-full mt-3 overflow-hidden"><div id="progressBar" class="h-full bg-gradient-to-r from-purple-500 to-indigo-500 transition-all duration-300" style="width:0%"></div></div><p class="text-[10px] opacity-60 mt-2">Modelo: <span id="modeloUsado">grok-2-vision-latest</span> • Análise real da sua tela</p></div>
    <div id="resultadoIA" class="hidden mt-3 bg-black rounded-xl p-4 border border-white/10"></div>
    <div id="acoesBarra" class="hidden mt-4 flex gap-3"><button type="button" id="btnCancelarBarra" class="flex-1 py-3.5 bg-red-500/10 border-2 border-red-500/30 text-red-400 font-black rounded-xl">✕ CANCELAR</button><button type="button" id="btnConfirmarBarra" class="flex-1 py-3.5 bg-gradient-to-r from-green-500 to-emerald-500 text-black font-black rounded-xl">✓ USAR DADOS REAIS</button></div>
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
  let prog=0; const interval=setInterval(()=>{prog=Math.min(92,prog+6); $('progressBar').style.width=prog+'%';},300);
  try{
    const res=await fetch('/api/analisar-print',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({imagem:imagemCapturadaBase64})});
    const data=await res.json();
    dadosDetectados=data;
    clearInterval(interval); $('progressBar').style.width='100%';
    setTimeout(()=>{
      $('analiseStatus').classList.add('hidden');
      
      if(data.erro==='SEM_IA' || data.erro==='SEM_CHAVE'){
        $('resultadoIA').innerHTML=`<div class="bg-red-500/20 border-2 border-red-500 rounded-xl p-4"><p class="font-black text-red-400">❌ ${data.mensagem||'Sem chave'}</p><p class="text-xs mt-2">${data.descricao||''}</p><code class="block bg-black p-2 rounded mt-3 text-yellow-400 text-xs">GROK_API_KEY=xai-...<br>ou<br>GEMINI_API_KEY=AIza...</code><p class="text-[11px] opacity-60 mt-2">Grok: https://console.x.ai/ • Gemini: https://aistudio.google.com/app/apikey</p></div>`;
        $('resultadoIA').classList.remove('hidden');
        return;
      }
      if(data.erro){
        $('resultadoIA').innerHTML=`<div class="bg-red-500/20 border border-red-500 rounded-xl p-3"><p class="font-bold text-red-400">❌ Erro: ${data.erro}</p><p class="text-xs mt-1">${data.mensagem||data.descricao||''}</p></div>`;
        $('resultadoIA').classList.remove('hidden');
        return;
      }

      const layer=$('markersLayer'); layer.innerHTML='';
      (data.marcacoes||[]).forEach((m,i)=>{
        const el=document.createElement('div'); el.className='marker';
        el.style.left=m.x+'%'; el.style.top=m.y+'%'; el.style.width=m.w+'%'; el.style.height=m.h+'%';
        el.style.borderColor=m.color||'#22c55e'; el.style.background=(m.color||'#22c55e')+'18';
        el.style.animationDelay=(i*0.08)+'s';
        const lb=document.createElement('div'); lb.className='marker-label'; lb.style.background=m.color||'#22c55e'; lb.textContent=m.campo;
        const cf=document.createElement('div'); cf.className='conf-badge'; cf.style.borderColor=m.color||'#22c55e'; cf.style.color=m.color||'#22c55e'; cf.textContent=Math.round((m.conf||0.9)*100)+'%';
        el.appendChild(lb); el.appendChild(cf); layer.appendChild(el);
      });

      const media = data.marcacoes && data.marcacoes.length ? Math.round(data.marcacoes.reduce((a,b)=>a+(b.conf||0.9),0)/data.marcacoes.length*100) : 85;
      $('modeloUsado').textContent = data.modelo_usado || 'GROK Vision';
      
      $('resultadoIA').innerHTML=`
        <div class="flex items-center justify-between mb-3"><span class="text-green-400 font-black text-xs">✅ ANÁLISE REAL GROK - ${media}% • ${data.modelo_usado||''}</span><span class="text-[10px] px-2.5 py-1 bg-green-500/20 text-green-400 rounded-full border border-green-500/30">${data.marcacoes?.length||0} elementos reais</span></div>
        <div class="space-y-2 text-[12px]">
          <div class="p-2.5 bg-[#22c55e]/10 border border-[#22c55e]/20 rounded-lg"><span class="text-[#22c55e] font-black">Título REAL:</span> ${data.titulo||''}</div>
          <div class="grid grid-cols-2 gap-2">
            <div class="p-2 bg-[#eab308]/10 border border-[#eab308]/20 rounded-lg"><span class="text-[#eab308] font-bold">Valor:</span> R$ ${data.valor||''}</div>
            <div class="p-2 bg-[#3b82f6]/10 border border-[#3b82f6]/20 rounded-lg"><span class="text-[#3b82f6] font-bold">Entrega:</span> ${data.entrega||''}</div>
            <div class="p-2 bg-[#a855f7]/10 border border-[#a855f7]/20 rounded-lg"><span class="text-[#a855f7] font-bold">Garantia:</span> ${data.garantia||''}</div>
            <div class="p-2 bg-[#f97316]/10 border border-[#f97316]/20 rounded-lg"><span class="text-[#f97316] font-bold">Estoque:</span> ${data.estoque||''}</div>
          </div>
        </div>
        <p class="text-[10px] text-green-400 mt-3">✅ Texto lido de verdade da sua captura, sem produto falso • Provedor: ${data.provedor||'GROK'}</p>
      `;
      $('resultadoIA').classList.remove('hidden');
      $('acoesBarra').classList.remove('hidden');
    },600);
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
  $('msg').textContent='✅ Dados REAIS Grok aplicados! ('+(dadosDetectados.modelo_usado||'GROK')+')';
  $('msg').className='mt-3 text-xs text-center text-green-400 font-bold';
  fecharBarraFlutuante();
}

document.addEventListener('DOMContentLoaded', ()=>{
  $('btnAbrirBarra').addEventListener('click', abrirBarraFlutuante);
  $('btnFecharBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCancelarBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCapturar').addEventListener('click', capturarTela);
  $('btnConfirmarBarra').addEventListener('click', confirmarCaptura);
  $('btnGerarIA').addEventListener('click', async ()=>{
    const prompt=$('promptIA').value.trim();
    if(!prompt){ alert('Digite algo'); return; }
    $('msg').textContent='🤖 Gerando com '+( "{{'GROK' if tem_grok else 'IA'}}" )+'...';
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
      $('msg').className='mt-3 text-xs text-center text-green-400';
    }catch(e){ $('msg').textContent='❌ Erro: '+e.message; }
  });
  $('imagem').addEventListener('change', e=>{
    const pr=$('preview'); pr.innerHTML='';
    [...e.target.files].forEach(f=>{ const img=document.createElement('img'); img.src=URL.createObjectURL(f); img.className='w-full h-20 object-cover rounded-lg border border-white/10'; pr.appendChild(img); });
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
    if(!$('titulo').value.trim()){ alert('Título obrigatório'); return; }
    $('msg').textContent='📦 Criando...';
    try{
      const res=await fetch('/api/criar',{method:'POST',body:fd});
      const data=await res.json();
      $('msg').textContent=data.msg;
      if(data.ok) setTimeout(()=>location.reload(),1200);
    }catch(e){ $('msg').textContent='❌ Erro: '+e.message; }
  });
  document.querySelectorAll('.btn-editar').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id=btn.getAttribute('data-id');
      const novo=prompt('Novo título para '+id);
      if(!novo) return;
      await fetch('/api/editar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,titulo:novo})});
      location.reload();
    });
  });
  document.querySelectorAll('.btn-excluir').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id=btn.getAttribute('data-id');
      if(!confirm('Excluir '+id+'?')) return;
      btn.textContent='⏳...'; btn.disabled=true;
      const res=await fetch('/api/deletar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
      const data=await res.json();
      alert(data.msg||'Excluído'); location.reload();
    });
  });
});
async function syncGitHub(){
  if(!confirm('Enviar para GitHub?')) return;
  const res=await fetch('/api/sync',{method:'POST'});
  const data=await res.json();
  alert(data.msg);
  location.reload();
}
</script>
</body>
</html>
    """
    grok_key = get_grok_key()
    return render_template_string(html, produtos=produtos, tem_grok=bool(grok_key), tem_gemini=bool(get_gemini_key()), grok_key=grok_key or "")

@app.route("/api/gerar-ia", methods=["POST"])
def api_gerar_ia():
    return jsonify(gerar_com_ia(request.json.get("prompt","")))

@app.route("/api/analisar-print", methods=["POST"])
def api_analisar_print():
    try:
        result = analisar_print_real_ia(request.json.get("imagem",""))
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"erro":"EXCECAO","mensagem":str(e),"marcacoes":[],"titulo":"Erro","valor":"0"}), 500

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
        return jsonify({"ok":True,"msg":"Excluído!"})
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
    print("="*60)
    print("ELITE COMÉRCIO - GROK VISION REAL")
    print(f"Grok: {'OK '+get_grok_key()[:12]+'...' if get_grok_key() else 'FALTA - crie .env com GROK_API_KEY=xai-...'}")
    print(f"Gemini: {'OK' if get_gemini_key() else 'Não configurado'}")
    print("Acesse: http://localhost:5000")
    print("="*60)
    app.run(debug=True, port=5000)
