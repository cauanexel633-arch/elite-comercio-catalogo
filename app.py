
import os, pathlib, json, re, shutil, subprocess, base64, io, stat, time
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

BASE = pathlib.Path(__file__).parent
PRODUTOS_DIR = BASE / "produtos"
SITE_DIR = BASE / "site"

# Carrega .env robusto
for p in [BASE / ".env", pathlib.Path.cwd() / ".env", BASE.parent / ".env"]:
    if p.exists():
        try:
            load_dotenv(dotenv_path=p, override=True)
        except:
            pass
try:
    load_dotenv(override=True)
except:
    pass

def get_grok_key():
    for k in ["GROK_API_KEY","XAI_API_KEY","XAI_APIKEY","GROK_KEY"]:
        v=os.getenv(k)
        if v and len(v)>15:
            return v.strip()
    return ""

def get_gemini_key():
    v=os.getenv("GEMINI_API_KEY","").strip()
    return v if len(v)>15 else ""

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
    grok_key = get_grok_key()
    gemini_key = get_gemini_key()
    
    # Tenta Gemini com nova SDK google.genai (não a deprecated)
    if gemini_key:
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=gemini_key)
            resp = client.models.generate_content(
                model="gemini-2.0-flash-lite",
                contents=f"Gere JSON: titulo atraente, valor ex 129.90, entrega Full/Normal, garantia ex 12 meses, estoque ex 27, descricao curta venda para produto: {prompt}. Só JSON puro",
                config=types.GenerateContentConfig(temperature=0.4)
            )
            txt = resp.text.replace("```json","").replace("```","").strip()
            s=txt.find("{"); e=txt.rfind("}")+1
            if s!=-1: txt=txt[s:e]
            print("✅ Gemini novo SDK OK")
            return json.loads(txt)
        except Exception as e:
            print(f"Gemini novo SDK falhou: {e}")
            # tenta SDK antigo como fallback
            try:
                import google.generativeai as genai_old
                genai_old.configure(api_key=gemini_key)
                model = genai_old.GenerativeModel("gemini-1.5-flash-latest")
                resp = model.generate_content(f"Gere JSON: titulo, valor, entrega, garantia, estoque, descricao para: {prompt}. Só JSON", generation_config={"temperature":0.4})
                txt = resp.text.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1: txt=txt[s:e]
                return json.loads(txt)
            except Exception as e2:
                print(f"Gemini old SDK falhou: {e2}")

    # Tenta Grok texto
    if grok_key:
        try:
            import requests
            for modelo in ["grok-4.5","grok-4","grok-3","grok-3-mini"]:
                try:
                    r = requests.post("https://api.x.ai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {grok_key}", "Content-Type":"application/json"},
                        json={
                            "model": modelo,
                            "messages":[{"role":"user","content":f"Gere JSON: titulo, valor, entrega, garantia, estoque, descricao para: {prompt}. Só JSON"}],
                            "temperature":0.4
                        }, timeout=25)
                    if r.status_code==200:
                        txt = r.json()["choices"][0]["message"]["content"]
                        txt = txt.replace("```json","").replace("```","").strip()
                        s=txt.find("{"); e=txt.rfind("}")+1
                        if s!=-1: txt=txt[s:e]
                        return json.loads(txt)
                    else:
                        print(f"Grok {modelo} texto erro: {r.text[:300]}")
                except:
                    continue
        except Exception as e:
            print(f"Grok texto erro: {e}")

    return {"titulo":prompt.title()[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":prompt}

def analisar_com_gemini_novo_sdk(image_b64):
    """Usa nova SDK google.genai que não está deprecated"""
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316"}
    gemini_key = get_gemini_key()
    if not gemini_key:
        return None
    
    try:
        from google import genai
        from google.genai import types
        from PIL import Image
        
        client = genai.Client(api_key=gemini_key)
        
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        img_data = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_data))
        
        # Salva temporariamente para enviar
        # A nova SDK aceita PIL Image diretamente via from_image?
        # Vamos converter para bytes
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        
        prompt = """
        Analise PRINT REAL Mercado Livre. IGNORE cabeçalho amarelo topo (y<20% proibido).
        TITULO: texto grande preto 2-3 linhas à direita da foto (y 25-45%)
        VALOR: R$ grande negrito abaixo título (y 40-60%)
        ENTREGA: Chegará grátis/FULL perto preço
        GARANTIA: Compra Garantida
        ESTOQUE: X disponíveis perto botão Comprar
        Retorne JSON: {titulo,valor,entrega,garantia,estoque,descricao,marcacoes:[{campo,x,y,w,h,conf}]} x,y,w,h em % justos ao texto. Só JSON.
        """
        
        # Modelos novos que ainda têm free tier
        modelos = ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash-8b", "gemini-1.5-flash", "gemini-2.5-flash-preview-04-17"]
        
        for modelo in modelos:
            try:
                print(f"👁️ GEMINI novo SDK tentando {modelo}...")
                # A nova SDK usa client.models.generate_content com image
                # Precisa passar image como Part
                image_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
                
                resp = client.models.generate_content(
                    model=modelo,
                    contents=[prompt, image_part],
                    config=types.GenerateContentConfig(
                        temperature=0.1,
                        max_output_tokens=2000,
                    )
                )
                
                txt = resp.text
                print(f"📄 Gemini {modelo} resposta: {txt[:600]}")
                
                txt = txt.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1 and e!=-1:
                    txt=txt[s:e]
                
                data = json.loads(txt)
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
                    print(f"✅ GEMINI {modelo} SUCESSO: {len(validas)} elementos")
                    return data
            except Exception as e:
                err_str = str(e)
                print(f"❌ Gemini {modelo} falhou: {err_str[:500]}")
                # Se for quota exceeded, para de tentar outros modelos do mesmo projeto
                if "429" in err_str or "quota" in err_str.lower() or "exceeded" in err_str.lower():
                    print("⚠️ Quota excedida, parando tentativas Gemini")
                    return {"erro": "GEMINI_QUOTA", "mensagem": err_str[:800], "tipo": "quota"}
                continue
        return None
    except ImportError as e:
        print(f"❌ google.genai não instalado: {e} - instale com pip install google-genai")
        return {"erro": "SEM_LIB", "mensagem": f"Instale: pip install google-genai - erro: {e}"}
    except Exception as e:
        print(f"❌ Erro geral Gemini novo SDK: {e}")
        import traceback
        traceback.print_exc()
        return {"erro": "EXCECAO", "mensagem": str(e)[:800]}

def analisar_com_grok_vision(image_b64):
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316"}
    grok_key = get_grok_key()
    if not grok_key:
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

        prompt = "Analise PRINT REAL Mercado Livre. IGNORE cabeçalho amarelo topo y<20%. TITULO y 25-45% texto grande preto direita da foto, VALOR R$ grande negrito y 40-60%, ENTREGA Chegará grátis/FULL, GARANTIA Compra Garantida, ESTOQUE X disponíveis. JSON: {titulo,valor,entrega,garantia,estoque,descricao,marcacoes:[{campo,x,y,w,h,conf}]} x,y,w,h em % justos. Só JSON."
        modelos = ["grok-4.5","grok-4","grok-3","grok-3-mini","grok-2-latest"]

        for modelo in modelos:
            try:
                print(f"👁️ GROK Vision {modelo}...")
                payload = {
                    "model": modelo,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url, "detail": "high"}}
                        ]
                    }],
                    "temperature":0.1,
                    "max_tokens":2000
                }
                r = requests.post("https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {grok_key}", "Content-Type":"application/json"},
                    json=payload, timeout=90)
                print(f"GROK {modelo} status: {r.status_code}")
                if r.status_code != 200:
                    txt = r.text
                    print(f"Erro {modelo}: {txt[:600]}")
                    if "permission-denied" in txt or "credits" in txt.lower():
                        return {"erro": "GROK_SEM_CREDITO", "mensagem": txt[:800], "tipo": "credito"}
                    continue
                resp_json = r.json()
                txt = resp_json["choices"][0]["message"]["content"]
                print(f"📄 GROK {modelo} resposta: {txt[:600]}")
                txt = txt.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1 and e!=-1:
                    txt=txt[s:e]
                data = json.loads(txt)
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
                data["provedor"]="GROK"
                data["usou_fallback"]=False
                if validas:
                    print(f"✅ GROK {modelo} SUCESSO")
                    return data
            except Exception as e:
                print(f"❌ GROK {modelo} exceção: {e}")
                continue
        return None
    except Exception as e:
        print(f"❌ Erro geral Grok: {e}")
        return None

def analisar_print_real_ia(image_b64):
    print("🔍 Iniciando análise REAL...")
    grok_key = get_grok_key()
    gemini_key = get_gemini_key()
    print(f"🔑 Grok: {'OK' if grok_key else 'FALTA'} | Gemini: {'OK' if gemini_key else 'FALTA'}")

    # Tenta Grok primeiro
    if grok_key:
        res = analisar_com_grok_vision(image_b64)
        if res:
            if res.get("erro") == "GROK_SEM_CREDITO":
                return {
                    "erro": "GROK_SEM_CREDITO",
                    "titulo": "⚠️ GROK sem créditos",
                    "valor": "0",
                    "entrega": "",
                    "garantia": "",
                    "estoque": "",
                    "descricao": "",
                    "marcacoes": [],
                    "usou_fallback": True,
                    "mensagem": "Seu time GROK foi criado mas está sem créditos. Você precisa comprar créditos em https://console.x.ai/team/ - mínimo $5. Enquanto isso, o app tentará usar Gemini. Se Gemini também falhar por quota, use modo manual abaixo.",
                    "link_compra": "https://console.x.ai/team/",
                    "debug": res.get("mensagem","")
                }
            if res.get("marcacoes"):
                return res

    # Tenta Gemini novo SDK
    if gemini_key:
        res = analisar_com_gemini_novo_sdk(image_b64)
        if res:
            if res.get("erro") == "GEMINI_QUOTA":
                return {
                    "erro": "GEMINI_QUOTA",
                    "titulo": "⚠️ GEMINI quota zerada",
                    "valor": "0",
                    "entrega": "",
                    "garantia": "",
                    "estoque": "",
                    "descricao": "",
                    "marcacoes": [],
                    "usou_fallback": True,
                    "mensagem": f"Quota grátis do Gemini zerada (limit 0). Isso acontece quando seu projeto Google Cloud não tem faturamento ou excedeu limite diário. Soluções: 1) Vá em https://aistudio.google.com/app/apikey e crie NOVA chave em projeto novo, 2) Ou habilite faturamento em https://console.cloud.google.com/billing, 3) Ou use modo manual enquanto isso. Erro: {res.get('mensagem','')[:500]}",
                    "debug": res.get("mensagem","")
                }
            if res.get("erro"):
                # Outro erro, tenta mostrar
                if res.get("marcacoes"):
                    return res
                # Se não tem marcações mas tem erro, retorna erro
                if res.get("erro") in ["SEM_LIB","EXCECAO"]:
                    return {
                        "erro": res.get("erro"),
                        "titulo": "⚠️ Erro Gemini",
                        "valor": "0","entrega":"","garantia":"","estoque":"","descricao":"",
                        "marcacoes": [],
                        "usou_fallback": True,
                        "mensagem": res.get("mensagem",""),
                        "debug": res.get("mensagem","")
                    }
            if res.get("marcacoes"):
                return res

    # Fallback MANUAL - funciona sem IA, permite editar
    print("❌ Nenhuma IA funcionou - retornando modo manual")
    return {
        "erro": "SEM_IA_MANUAL",
        "titulo": "",
        "valor": "",
        "entrega": "Full",
        "garantia": "",
        "estoque": "",
        "descricao": "",
        "marcacoes": [],
        "usou_fallback": True,
        "mensagem": "IA sem créditos no momento (Grok precisa comprar créditos $5, Gemini quota zerada). MODO MANUAL ATIVO: Digite os dados manualmente ou use o botão 'Gerar com texto' que ainda funciona com texto. A captura de tela ainda mostra a imagem para você copiar os dados visualmente.",
        "modo_manual": True,
        "debug": f"Grok: {bool(grok_key)} Gemini: {bool(gemini_key)}"
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
<title>Elite Comércio - GROK 4.5 + GEMINI - Completo Fix</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
.marker{position:absolute; border-width:3px; border-style:solid; border-radius:12px; background:rgba(0,0,0,0.08); animation:pulse 2s infinite; pointer-events:none;}
.marker-label{position:absolute; bottom:-24px; left:0; color:black; font-size:11px; font-weight:900; padding:4px 10px; border-radius:8px; text-transform:uppercase; white-space:nowrap;}
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
      <h1 class="text-3xl font-black text-yellow-400">ELITE COMÉRCIO</h1>
      <p class="text-[13px] opacity-80">
        <span class="{{'text-green-400' if tem_grok else 'text-red-400'}}">🟣 GROK: {{'✅ '+grok_key[:12]+'...' if tem_grok else '❌ Sem crédito? Veja terminal'}}</span> | 
        <span class="{{'text-green-400' if tem_gemini else 'text-red-400'}}">🔵 GEMINI: {{'✅ OK' if tem_gemini else '❌ Falta'}}</span> | {{produtos|length}} produtos
      </p>
    </div>
    <div class="ml-auto"><button type="button" onclick="syncGitHub()" class="btn px-5 py-2.5 bg-white text-black rounded-xl font-black">🚀 Sync</button></div>
  </div>

  <div class="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3 mb-6 text-xs">
    <p class="font-black text-yellow-400">⚠️ SEGURANÇA: Você vazou suas chaves no log anterior! Apague essas chaves e gere novas:</p>
    <p>• GROK: <a href="https://console.x.ai/" target="_blank" class="underline text-blue-400">console.x.ai</a> → Delete old key → Create new</p>
    <p>• GEMINI: <a href="https://aistudio.google.com/app/apikey" target="_blank" class="underline text-blue-400">aistudio.google.com/app/apikey</a> → Delete → Create new</p>
    <p class="mt-2 opacity-70">Depois atualize seu .env com as novas chaves.</p>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-[520px_1fr] gap-6">
    <div class="bg-[#151515] rounded-2xl p-6 border border-yellow-400/20 h-fit lg:sticky top-6">
      <h2 class="text-xl font-bold mb-4">✨ Adicionar com IA</h2>
      <div class="mb-4 bg-black rounded-xl p-4 border-2 border-yellow-400/30">
        <div class="flex items-center justify-between mb-3">
          <label class="text-xs font-black text-yellow-400">🎯 CAPTURA IA - GROK 4.5 + GEMINI</label>
          <button type="button" id="btnAbrirBarra" class="btn w-12 h-12 bg-gradient-to-br from-yellow-400 to-amber-500 text-black rounded-xl flex items-center justify-center text-2xl font-black">🖥️</button>
        </div>
        <textarea id="promptIA" rows="2" placeholder="Descreva o produto: ex: câmera wifi dome 360..." class="w-full p-3 bg-[#0a0a0a] border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400"></textarea>
        <button type="button" id="btnGerarIA" class="btn w-full mt-3 py-3 bg-gradient-to-r from-purple-500 via-yellow-400 to-blue-500 text-black font-black rounded-xl text-sm">GERAR COM IA TEXTO 🤖 (funciona mesmo sem crédito visão)</button>
      </div>
      <form id="formProd" class="space-y-3">
        <input id="titulo" placeholder="Título" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm" required>
        <div class="grid grid-cols-2 gap-3"><input id="valor" placeholder="Valor ex: 109.99" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm" required><select id="entrega" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm"><option>Full</option><option>Normal</option></select></div>
        <input id="link" placeholder="Link afiliado" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm" required>
        <div class="grid grid-cols-2 gap-3"><input id="garantia" placeholder="Garantia" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm"><input id="estoque" placeholder="Estoque" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm"></div>
        <textarea id="descricao" placeholder="Descrição" rows="2" class="w-full p-3.5 bg-black border border-white/10 rounded-xl text-sm"></textarea>
        <div><input type="file" id="imagem" accept="image/*" multiple class="w-full text-xs file:bg-yellow-400 file:text-black file:border-0 file:rounded-xl file:px-4 file:py-2 file:font-black"><div id="preview" class="mt-3 grid grid-cols-3 gap-2"></div></div>
        <button type="submit" class="btn w-full py-4 bg-gradient-to-r from-yellow-400 to-amber-500 text-black font-black rounded-xl text-[15px]">CRIAR PRODUTO 📦</button>
      </form>
      <p id="msg" class="mt-3 text-xs text-center min-h-[18px] opacity-70"></p>
    </div>
    <div class="bg-[#111] rounded-2xl p-6 border border-white/5">
      <h2 class="font-bold text-lg mb-5">📦 Produtos ({{produtos|length}})</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        {% for p in produtos %}
        <div class="bg-[#1a1a1a] rounded-2xl p-4 border border-white/5 hover:border-yellow-400/30 transition">
          <div class="flex gap-3"><div class="w-20 h-20 bg-black rounded-xl flex items-center justify-center text-[10px] opacity-40">IMG</div><div class="flex-1 min-w-0"><span class="text-[10px] px-2.5 py-1 rounded-full font-black bg-green-500 text-black">{{p.status}}</span><h3 class="font-bold text-[13px] mt-1 line-clamp-2">{{p.titulo}}</h3><p class="text-yellow-400 font-black text-sm">R$ {{p.valor}}</p></div></div>
          <div class="flex gap-2 mt-4"><button type="button" data-id="{{p.id}}" class="btn-editar flex-1 py-2.5 bg-white/10 rounded-xl text-xs font-bold">✏️ Editar</button><button type="button" data-id="{{p.id}}" class="btn-excluir flex-1 py-2.5 bg-red-500/15 text-red-400 rounded-xl text-xs font-bold">🗑️ Excluir</button></div>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>
</div>

<div id="floatingBar" class="hidden fixed bottom-5 right-5 w-[660px] max-w-[97vw] bg-[#161616] rounded-[24px] border-2 border-yellow-400/50 z-[9999] overflow-hidden max-h-[93vh] overflow-y-auto shadow-[0_30px_80px_rgba(0,0,0,0.8)]">
  <div id="dragHeader" class="drag-handle sticky top-0 z-20 flex items-center justify-between px-5 py-4 bg-black border-b border-white/10">
    <div class="flex items-center gap-3"><span class="w-3 h-3 bg-green-400 rounded-full animate-pulse"></span><span class="font-black text-[13px] text-yellow-400">CAPTURA IA REAL - GROK 4.5 + GEMINI (FIX)</span><span class="text-[9px] px-2.5 py-1 bg-gradient-to-r from-purple-500/20 to-blue-500/20 rounded-full border border-white/10">CORRIGIDO</span></div>
    <button type="button" id="btnFecharBarra" class="btn w-8 h-8 bg-red-500/20 hover:bg-red-500 text-red-400 hover:text-white rounded-full font-black">✕</button>
  </div>
  <div class="p-5">
    <div class="flex flex-wrap gap-2 mb-4 text-[11px]"><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#22c55e]/15 border border-[#22c55e]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#22c55e]"></span>Título</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#eab308]/15 border border-[#eab308]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#eab308]"></span>Valor</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#3b82f6]/15 border border-[#3b82f6]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#3b82f6]"></span>Entrega</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#a855f7]/15 border border-[#a855f7]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#a855f7]"></span>Garantia</span><span class="flex items-center gap-1.5 px-3 py-1.5 bg-[#f97316]/15 border border-[#f97316]/30 rounded-full font-bold"><span class="w-3 h-3 rounded-full bg-[#f97316]"></span>Estoque</span></div>
    <div id="captureArea" class="relative w-full h-[460px] bg-[#0a0a0a] rounded-2xl border-2 border-dashed border-white/15 overflow-hidden flex flex-col items-center justify-center">
      <div id="capturePlaceholder" class="text-center p-8"><div class="text-7xl mb-4">👁️</div><p class="text-[15px] font-black">CAPTURA REAL - VERSÃO FIX</p><p class="text-[12px] opacity-60 mt-3 max-w-[360px]">Se GROK sem crédito e Gemini quota zerada, usa modo manual.<br>Mas a imagem ainda aparece para você copiar.</p><button type="button" id="btnCapturar" class="btn mt-6 px-10 py-4 bg-gradient-to-r from-purple-600 via-yellow-400 to-blue-500 text-black font-black rounded-2xl text-[13px] shadow-2xl hover:scale-105">📸 CAPTURAR TELA</button></div>
      <img id="captureImg" class="hidden w-full h-full object-contain"><div id="markersLayer" class="absolute inset-0 pointer-events-none"></div>
    </div>
    <div id="analiseStatus" class="hidden mt-4 p-4 bg-black rounded-2xl border-2 border-purple-500/30"><p class="text-xs font-black flex items-center gap-3"><span class="w-5 h-5 border-2 border-purple-400 border-t-transparent rounded-full animate-spin"></span>🧠 Analisando com IA...</p><div class="w-full h-2.5 bg-white/10 rounded-full mt-3 overflow-hidden"><div id="progressBar" class="h-full bg-gradient-to-r from-purple-500 via-yellow-400 to-blue-500 transition-all" style="width:0%"></div></div><p class="text-[10px] opacity-60 mt-2.5">Modelo: <span id="modeloUsado" class="font-bold text-yellow-400">grok-4.5 / gemini-2.0-flash-lite</span></p></div>
    <div id="resultadoIA" class="hidden mt-4 bg-black rounded-2xl p-4 border border-white/10"></div>
    <div id="acoesBarra" class="hidden mt-5 flex gap-3"><button type="button" id="btnCancelarBarra" class="btn flex-1 py-4 bg-red-500/10 border-2 border-red-500/20 text-red-400 font-black rounded-xl">✕ CANCELAR</button><button type="button" id="btnConfirmarBarra" class="btn flex-1 py-4 bg-gradient-to-r from-green-500 to-emerald-500 text-black font-black rounded-xl">✓ USAR DADOS</button></div>
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
        let html = `<div class="rounded-2xl p-4 border-2 ${data.erro==='GROK_SEM_CREDITO' ? 'bg-purple-500/15 border-purple-500/50' : data.erro==='GEMINI_QUOTA' ? 'bg-blue-500/15 border-blue-500/50' : 'bg-red-500/15 border-red-500/50'}">`;
        html += `<p class="font-black ${data.erro==='GROK_SEM_CREDITO' ? 'text-purple-300' : data.erro==='GEMINI_QUOTA' ? 'text-blue-300' : 'text-red-300'}">${data.erro==='GROK_SEM_CREDITO' ? '🟣 GROK SEM CRÉDITOS' : data.erro==='GEMINI_QUOTA' ? '🔵 GEMINI QUOTA ZERADA' : '❌ ERRO'}: ${data.mensagem||''}</p>`;
        if(data.erro==='GROK_SEM_CREDITO'){
          html += `<div class="mt-3 bg-black/50 rounded-xl p-3 text-xs"><p class="font-bold text-yellow-400">Como resolver:</p><p class="mt-2">1. Vá em <a href="https://console.x.ai/team" target="_blank" class="underline text-blue-400">console.x.ai/team</a></p><p>2. Compre créditos - mínimo $5 (paga com cartão)</p><p>3. Ou use Gemini que é grátis (veja abaixo)</p><p class="mt-3 font-bold text-yellow-400">Enquanto isso, use MODO MANUAL:</p><p>• A imagem capturada está visível acima</p><p>• Digite manualmente título, valor, etc copiando da imagem</p><p>• Ou use o botão "Gerar com IA Texto" que funciona com texto mesmo sem crédito visão</p></div>`;
        } else if(data.erro==='GEMINI_QUOTA'){
          html += `<div class="mt-3 bg-black/50 rounded-xl p-3 text-xs"><p class="font-bold text-yellow-400">Como resolver Gemini quota:</p><p class="mt-2">1. Crie NOVA chave em projeto novo: <a href="https://aistudio.google.com/app/apikey" target="_blank" class="underline text-blue-400">aistudio.google.com/app/apikey</a> → Create API key → Create new project</p><p>2. Ou habilite faturamento: <a href="https://console.cloud.google.com/billing" target="_blank" class="underline text-blue-400">console.cloud.google.com/billing</a></p><p>3. Ou espere 24h para reset da quota diária</p><p class="mt-3">Enquanto isso use modo manual copiando da imagem visível.</p></div>`;
        } else if(data.erro==='SEM_IA_MANUAL'){
          html += `<div class="mt-3 bg-black/50 rounded-xl p-3 text-xs"><p>${data.mensagem||''}</p><p class="mt-3 font-bold">💡 MODO MANUAL ATIVO:</p><p>• Imagem capturada está visível</p><p>• Copie manualmente: Título, Valor, etc</p><p>• Cole nos campos do formulário</p><p>• Clique CRIAR PRODUTO</p><p class="mt-3 text-[10px] opacity-50">Debug: ${data.debug||''}</p></div>`;
        } else {
          html += `<p class="text-xs mt-2 opacity-80">${data.descricao||''}</p><p class="text-[10px] mt-2 opacity-40">Debug: ${data.debug||''}</p>`;
        }
        html += `</div>`;
        $('resultadoIA').innerHTML=html;
        $('resultadoIA').classList.remove('hidden');
        // Mesmo sem IA, mostra ações para modo manual (usuário pode ver imagem e digitar manual)
        $('acoesBarra').classList.add('hidden');
        return;
      }
      const layer=$('markersLayer'); layer.innerHTML='';
      (data.marcacoes||[]).forEach((m,i)=>{
        const el=document.createElement('div'); el.className='marker';
        el.style.left=m.x+'%'; el.style.top=m.y+'%'; el.style.width=m.w+'%'; el.style.height=m.h+'%';
        el.style.borderColor=m.color||'#22c55e'; el.style.background=(m.color||'#22c55e')+'14';
        const lb=document.createElement('div'); lb.className='marker-label'; lb.style.background=m.color||'#22c55e'; lb.textContent=m.campo;
        const cf=document.createElement('div'); cf.className='conf-badge'; cf.style.borderColor=m.color||'#22c55e'; cf.style.color=m.color||'#22c55e'; cf.textContent=Math.round((m.conf||0.9)*100)+'%';
        el.appendChild(lb); el.appendChild(cf); layer.appendChild(el);
      });
      const media = data.marcacoes && data.marcacoes.length ? Math.round(data.marcacoes.reduce((a,b)=>a+(b.conf||0.9),0)/data.marcacoes.length*100) : 90;
      $('modeloUsado').textContent = data.modelo_usado || 'IA Real';
      $('resultadoIA').innerHTML=`<div class="flex items-center justify-between mb-4"><span class="text-green-400 font-black text-xs">✅ ${data.provedor||''} ${data.modelo_usado||''} - ${media}%</span><span class="text-[10px] px-3 py-1.5 bg-green-500/20 text-green-400 rounded-full border border-green-500/30 font-black">${data.marcacoes?.length||0} reais</span></div><div class="space-y-3 text-[13px]"><div class="p-3.5 bg-[#22c55e]/10 border border-[#22c55e]/20 rounded-xl"><span class="text-[#22c55e] font-black text-xs">TÍTULO REAL:</span><br><b>${data.titulo||''}</b></div><div class="grid grid-cols-2 gap-3"><div class="p-3 bg-[#eab308]/10 border border-[#eab308]/20 rounded-xl"><span class="text-[#eab308] font-black text-[11px]">VALOR:</span><br><b>R$ ${data.valor||''}</b></div><div class="p-3 bg-[#3b82f6]/10 border border-[#3b82f6]/20 rounded-xl"><span class="text-[#3b82f6] font-black text-[11px]">ENTREGA:</span><br><b class="text-xs">${data.entrega||''}</b></div></div></div>`;
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
  $('msg').textContent=`✅ Dados REAIS aplicados! (${dadosDetectados.modelo_usado||''})`;
  $('msg').className='mt-3 text-xs text-center text-green-400 font-black';
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
    if(!prompt){ alert('Digite o nome do produto'); return; }
    $('msg').textContent='🤖 Gerando com IA texto...';
    try{
      const res=await fetch('/api/gerar-ia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
      const data=await res.json();
      if(data.titulo) $('titulo').value=data.titulo;
      if(data.valor) $('valor').value=data.valor;
      if(data.entrega) $('entrega').value=data.entrega;
      if(data.garantia) $('garantia').value=data.garantia;
      if(data.estoque) $('estoque').value=data.estoque;
      if(data.descricao) $('descricao').value=data.descricao;
      $('msg').textContent='✨ Preenchido!';
      $('msg').className='mt-3 text-xs text-center text-green-400 font-black';
    }catch(e){ $('msg').textContent='❌ Erro: '+e.message; }
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
    if(!$('titulo').value.trim()){ alert('Título obrigatório'); return; }
    $('msg').textContent='📦 Criando...';
    try{
      const res=await fetch('/api/criar',{method:'POST',body:fd});
      const data=await res.json();
      $('msg').textContent=data.msg;
      if(data.ok) setTimeout(()=>location.reload(),1300);
    }catch(e){ $('msg').textContent='❌ Erro: '+e.message; }
  });
  document.querySelectorAll('.btn-editar').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id=btn.getAttribute('data-id');
      const novo=prompt('Novo título para '+id+' :');
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
    print("="*75)
    print("🚀 ELITE COMÉRCIO - VERSÃO FIX GROK SEM CRÉDITO + GEMINI QUOTA FIX")
    print("="*75)
    print(f"BASE: {BASE}")
    print(f"GROK: {'OK' if get_grok_key() else 'FALTA'} | GEMINI: {'OK' if get_gemini_key() else 'FALTA'}")
    print("Se GROK der 403 sem créditos: compre em https://console.x.ai/team/")
    print("Se GEMINI der 429 quota: crie nova chave em projeto novo em https://aistudio.google.com/app/apikey")
    print("="*75)
    app.run(debug=True, port=5000)
