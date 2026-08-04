
import os, pathlib, json, re, shutil, subprocess, base64, io, stat, time, threading, webbrowser, sys
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv

BASE = pathlib.Path(__file__).parent
PRODUTOS_DIR = BASE / "produtos"
SITE_DIR = BASE / "site"
IS_EXE = getattr(sys, 'frozen', False)

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

def get_gemini_key():
    v = os.getenv("GEMINI_API_KEY","").strip()
    if v and len(v) > 20:
        return v
    for env_path in [BASE / ".env", pathlib.Path.cwd() / ".env"]:
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if "GEMINI_API_KEY" in line and "=" in line:
                        k, val = line.split("=",1)
                        val = val.strip().strip('"').strip("'")
                        if len(val) > 20:
                            return val
            except:
                pass
    return ""

app = Flask(__name__)

auto_sync_config = {
    "enabled": True,
    "auto_push": True,
    "auto_pull": True,
    "pull_interval": 120,
    "last_sync": None,
    "last_pull": None,
    "last_push": None,
    "status": "inativo",
    "syncing": False,
    "mensagem": "",
    "total_pushes": 0,
    "total_pulls": 0
}

def run_cmd(cmd, cwd=BASE, timeout=60):
    try:
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout, startupinfo=startupinfo)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)

def slugify(text):
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii','ignore').decode()
    text = re.sub(r'[^a-z0-9]+','-', text.lower()).strip('-')
    return text[:50] or "produto"

def get_status(pasta):
    try:
        ok, out = run_cmd(f'git status --porcelain "{pasta}"')
        if not out.strip():
            ok2, _ = run_cmd(f'git ls-files --error-unmatch "{pasta}"')
            return "publicado" if ok2 else "local"
        return "modificado"
    except:
        return "local"

def listar_produtos():
    lista=[]
    if PRODUTOS_DIR.exists():
        for p in sorted(PRODUTOS_DIR.iterdir(), reverse=True):
            if p.is_dir() and not p.name.startswith("."):
                def rd(n,d=""):
                    f=p/f"{n}.txt"
                    return f.read_text(encoding="utf-8").strip() if f.exists() else d
                imgs = list(p.glob("*.jpg"))+list(p.glob("*.png"))+list(p.glob("*.jpeg"))+list(p.glob("*.webp"))
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
                    "status": get_status(p),
                    "total_fotos": len(imgs)
                })
    return lista

def auto_git_push_background(mensagem="auto: atualiza catalogo"):
    if not auto_sync_config["enabled"] or not auto_sync_config["auto_push"]:
        return
    def _push():
        try:
            auto_sync_config["syncing"] = True
            auto_sync_config["status"] = "enviando"
            auto_sync_config["mensagem"] = f"Enviando: {mensagem[:40]}..."
            print(f"🔄 [AUTO PUSH] {mensagem}")
            run_cmd("python scripts/gerar_catalogo.py")
            time.sleep(0.5)
            ok, out = run_cmd("git add .")
            if not ok:
                auto_sync_config["status"] = "erro"
                auto_sync_config["mensagem"] = f"Erro add: {out[:100]}"
                return
            ok, out = run_cmd(f'git commit -m "{mensagem}"')
            if "nothing to commit" in out.lower() or "no changes" in out.lower():
                auto_sync_config["status"] = "sincronizado"
                auto_sync_config["mensagem"] = "Tudo sincronizado"
                auto_sync_config["last_sync"] = datetime.now().isoformat()
                return
            ok, out = run_cmd("git push")
            if ok:
                print(f"✅ [AUTO PUSH] Sucesso")
                auto_sync_config["status"] = "sincronizado"
                auto_sync_config["mensagem"] = f"Enviado: {mensagem[:30]}"
                auto_sync_config["last_push"] = datetime.now().isoformat()
                auto_sync_config["last_sync"] = datetime.now().isoformat()
                auto_sync_config["total_pushes"] += 1
            else:
                print(f"❌ [AUTO PUSH] Falhou: {out[:300]}")
                auto_sync_config["status"] = "erro"
                auto_sync_config["mensagem"] = f"Erro push: {out[:100]}"
        except Exception as e:
            auto_sync_config["status"] = "erro"
            auto_sync_config["mensagem"] = str(e)[:100]
        finally:
            auto_sync_config["syncing"] = False
    threading.Thread(target=_push, daemon=True).start()

def auto_git_pull_background():
    if not auto_sync_config["enabled"] or not auto_sync_config["auto_pull"]:
        return False, "Auto pull desabilitado"
    try:
        auto_sync_config["syncing"] = True
        auto_sync_config["status"] = "puxando"
        auto_sync_config["mensagem"] = "Verificando atualizações..."
        ok, out = run_cmd("git fetch origin")
        if not ok:
            auto_sync_config["status"] = "erro"
            auto_sync_config["mensagem"] = "Erro fetch"
            return False, out
        ok, out = run_cmd("git rev-list --count HEAD..origin/main")
        if not ok or not out.strip().isdigit():
            ok, out = run_cmd("git rev-list --count HEAD..origin/master")
        try:
            count = int(out.strip()) if out.strip().isdigit() else 0
        except:
            count = 0
        if count > 0:
            auto_sync_config["mensagem"] = f"{count} atualizações encontradas..."
            ok, out = run_cmd("git pull --autostash")
            if ok:
                run_cmd("python scripts/gerar_catalogo.py")
                auto_sync_config["status"] = "sincronizado"
                auto_sync_config["mensagem"] = f"{count} atualizações baixadas"
                auto_sync_config["last_pull"] = datetime.now().isoformat()
                auto_sync_config["last_sync"] = datetime.now().isoformat()
                auto_sync_config["total_pulls"] += 1
                return True, f"{count} atualizações"
            else:
                auto_sync_config["status"] = "erro"
                auto_sync_config["mensagem"] = f"Erro pull: {out[:100]}"
                return False, out
        else:
            auto_sync_config["status"] = "sincronizado"
            auto_sync_config["mensagem"] = "Tudo atualizado"
            auto_sync_config["last_sync"] = datetime.now().isoformat()
            return False, "Nenhuma atualização"
    except Exception as e:
        auto_sync_config["status"] = "erro"
        auto_sync_config["mensagem"] = str(e)[:100]
        return False, str(e)
    finally:
        auto_sync_config["syncing"] = False

def auto_sync_worker():
    print("🤖 [AUTO SYNC WORKER] Iniciado - 2 min")
    time.sleep(3)
    if auto_sync_config["auto_pull"]:
        auto_git_pull_background()
    while True:
        try:
            time.sleep(auto_sync_config["pull_interval"])
            if auto_sync_config["enabled"] and auto_sync_config["auto_pull"]:
                auto_git_pull_background()
        except Exception as e:
            print(f"❌ Worker erro: {e}")
            time.sleep(30)

threading.Thread(target=auto_sync_worker, daemon=True).start()

def gerar_com_ia_gemini(prompt):
    gemini_key = get_gemini_key()
    if not gemini_key:
        return {"titulo":prompt.title()[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":prompt}
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=gemini_key)
        system_prompt = f"""Gere JSON catálogo: titulo 70 chars, valor ex 129.90, entrega Full/Normal, garantia ex 12 meses, estoque ex 27 disponíveis, descricao curta venda para: {prompt}. Só JSON: {{"titulo":"","valor":"","entrega":"","garantia":"","estoque":"","descricao":""}}"""
        for modelo in ["gemini-2.0-flash-lite", "gemini-1.5-flash-8b", "gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                resp = client.models.generate_content(
                    model=modelo,
                    contents=system_prompt,
                    config=types.GenerateContentConfig(temperature=0.7, max_output_tokens=500, response_mime_type="application/json")
                )
                txt = resp.text.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1: txt=txt[s:e]
                data = json.loads(txt)
                data["modelo_usado"]=modelo
                return data
            except:
                continue
    except Exception as e:
        print(f"Erro IA: {e}")
    return {"titulo":prompt.title()[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":prompt}

def analisar_print_gemini_vision(image_b64):
    gemini_key = get_gemini_key()
    if not gemini_key:
        return {"erro": "SEM_CHAVE", "mensagem": "Configure GEMINI_API_KEY"}
    cores = {"titulo":"#22c55e","valor":"#eab308","entrega":"#3b82f6","garantia":"#a855f7","estoque":"#f97316"}
    try:
        from google import genai
        from google.genai import types
        from PIL import Image
        client = genai.Client(api_key=gemini_key)
        if "," in image_b64:
            image_b64 = image_b64.split(",")[1]
        img_data = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(img_data))
        if img.width > 1920 or img.height > 1920:
            img.thumbnail((1920, 1920))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        prompt = """Analise PRINT REAL Mercado Livre. IGNORE cabeçalho amarelo topo y<20%. TITULO y 25-45% texto grande preto direita da foto, VALOR R$ grande negrito y 40-60%, ENTREGA Chegará grátis/FULL, GARANTIA Compra Garantida, ESTOQUE X disponíveis. JSON: {titulo,valor,entrega,garantia,estoque,descricao,marcacoes:[{campo,x,y,w,h,conf}]} x,y,w,h em % justos. Só JSON."""
        for modelo in ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-1.5-flash-8b", "gemini-1.5-flash"]:
            try:
                image_part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
                resp = client.models.generate_content(
                    model=modelo,
                    contents=[prompt, image_part],
                    config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=2500, response_mime_type="application/json")
                )
                txt = resp.text.replace("```json","").replace("```","").strip()
                s=txt.find("{"); e=txt.rfind("}")+1
                if s!=-1 and e!=-1:
                    txt=txt[s:e]
                data = json.loads(txt)
                validas=[]
                for m in data.get("marcacoes",[]):
                    if float(m.get("y",0)) < 18:
                        continue
                    m["color"]=cores.get(m["campo"],"#22c55e")
                    m["x"]=max(0,min(92,float(m.get("x",0))))
                    m["y"]=max(18,min(92,float(m.get("y",0))))
                    m["w"]=max(4,min(75,float(m.get("w",10))))
                    m["h"]=max(2,min(14,float(m.get("h",5))))
                    m["conf"]=max(0.1,min(1.0,float(m.get("conf",0.85))))
                    validas.append(m)
                data["marcacoes"]=validas
                data["modelo_usado"]=modelo
                data["provedor"]="GEMINI"
                if validas:
                    return data
            except Exception as e:
                err=str(e)
                if "429" in err or "quota" in err.lower():
                    if "limit: 0" in err.lower():
                        return {"erro": "GEMINI_QUOTA_ZERO", "mensagem": f"Quota zerada. Crie nova chave em novo projeto"}
                    return {"erro": "GEMINI_QUOTA", "mensagem": err[:500]}
                continue
        return {"erro": "SEM_IA", "mensagem": "Falhou"}
    except Exception as e:
        return {"erro": "EXCECAO", "mensagem": str(e)[:800]}

@app.route("/")
def home():
    produtos = listar_produtos()
    tem_gemini = bool(get_gemini_key())
    gemini_key = get_gemini_key()
    
    html = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Elite Comércio - Liquid Sync</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800;900&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<style>
*{font-family:'Outfit',sans-serif}
h1,h2{font-family:'Space Grotesk',sans-serif}
body{background:#080808;color:white;overflow-x:hidden}
.glass{background:rgba(255,255,255,0.03);backdrop-filter:blur(20px);border:1px solid rgba(255,255,255,0.06)}
.glass-gold{background:linear-gradient(135deg,rgba(255,215,0,0.08),rgba(255,165,0,0.03));backdrop-filter:blur(20px);border:1px solid rgba(255,215,0,0.15)}
.gold-gradient{background:linear-gradient(135deg,#FFD700 0%,#FFA500 100%)}
.mesh-bg{position:fixed;inset:0;z-index:-1;overflow:hidden}
.mesh-orb{position:absolute;border-radius:50%;filter:blur(80px);opacity:0.15;animation:float 20s ease-in-out infinite}
.orb1{width:800px;height:800px;background:radial-gradient(circle,#FFD700,transparent);top:-200px;left:-200px}
.orb2{width:600px;height:600px;background:radial-gradient(circle,#3b82f6,transparent);top:50%;right:-100px;animation-delay:-7s}
.orb3{width:700px;height:700px;background:radial-gradient(circle,#a855f7,transparent);bottom:-200px;left:30%;animation-delay:-14s}
@keyframes float{0%,100%{transform:translate(0,0) scale(1)}33%{transform:translate(30px,-30px) scale(1.05)}66%{transform:translate(-20px,20px) scale(0.95)}}
.card-hover{transition:all 0.4s cubic-bezier(0.4,0,0.2,1)}
.card-hover:hover{transform:translateY(-4px);box-shadow:0 20px 40px rgba(0,0,0,0.4),0 0 0 1px rgba(255,215,0,0.1)}
.marker{position:absolute;border-width:3px;border-style:solid;border-radius:14px;background:rgba(0,0,0,0.06);animation:markerPulse 2.5s ease-in-out infinite;pointer-events:none}
.marker-label{position:absolute;bottom:-26px;left:0;color:black;font-size:11px;font-weight:900;padding:5px 12px;border-radius:10px;text-transform:uppercase;white-space:nowrap}
.conf-badge{position:absolute;top:-14px;right:-14px;background:black;color:white;font-size:11px;padding:4px 10px;border-radius:20px;border:2.5px solid currentColor;font-weight:900}
@keyframes markerPulse{0%,100%{transform:scale(1);opacity:0.95}50%{transform:scale(1.02);opacity:0.8}}
.drag-handle{cursor:grab;user-select:none}
.btn{transition:all 0.3s cubic-bezier(0.4,0,0.2,1)}
.btn:active{transform:scale(0.97)}
.scrollbar-thin::-webkit-scrollbar{width:6px}
.scrollbar-thin::-webkit-scrollbar-track{background:rgba(255,255,255,0.05);border-radius:10px}
.scrollbar-thin::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#FFD700,#FFA500);border-radius:10px}

/* ===== LIQUID FILL BUTTONS - ANIMAÇÃO PREMIUM ===== */
.liquid-btn{
  position:relative;
  overflow:hidden;
  isolation:isolate;
  border-radius:14px;
  transition:all 0.3s ease;
}
.liquid-btn .btn-content{
  position:relative;
  z-index:10;
  transition:all 0.3s ease;
}
.liquid-fill{
  position:absolute;
  bottom:0;
  left:0;
  width:100%;
  height:0%;
  z-index:1;
  transition:height 0.8s cubic-bezier(0.4,0,0.2,1), background 0.5s ease;
  overflow:hidden;
  display:flex;
  align-items:flex-end;
  justify-content:center;
}
.liquid-fill.liquid-blue{
  background:linear-gradient(180deg, #60a5fa 0%, #3b82f6 30%, #2563eb 70%, #1e40af 100%);
  box-shadow:inset 0 2px 10px rgba(255,255,255,0.3), inset 0 -2px 10px rgba(0,0,0,0.2);
}
.liquid-fill.liquid-yellow{
  background:linear-gradient(180deg, #fde047 0%, #facc15 20%, #eab308 50%, #ca8a04 100%);
  box-shadow:inset 0 2px 10px rgba(255,255,255,0.4), inset 0 -2px 10px rgba(0,0,0,0.2);
}
.liquid-fill.liquid-green{
  background:linear-gradient(180deg, #4ade80 0%, #22c55e 30%, #16a34a 70%, #15803d 100%) !important;
  box-shadow:inset 0 2px 15px rgba(255,255,255,0.4), 0 0 20px rgba(34,197,94,0.5) !important;
}
.liquid-fill.liquid-red{
  background:linear-gradient(180deg, #fca5a5 0%, #ef4444 30%, #dc2626 70%, #991b1b 100%) !important;
  box-shadow:inset 0 2px 15px rgba(255,255,255,0.3), 0 0 20px rgba(239,68,68,0.5) !important;
  animation:shake 0.5s ease-in-out;
}
@keyframes shake{
  0%,100%{transform:translateX(0)}
  20%,60%{transform:translateX(-4px)}
  40%,80%{transform:translateX(4px)}
}

/* Ondas no topo do líquido */
.liquid-wave{
  position:absolute;
  top:-20px;
  left:-50%;
  width:200%;
  height:40px;
  background:inherit;
  border-radius:45%;
  animation:waveRotate 3s linear infinite;
  opacity:0.8;
}
.liquid-wave.wave2{
  top:-25px;
  border-radius:40%;
  animation:waveRotate 4s linear infinite reverse;
  opacity:0.5;
}
@keyframes waveRotate{
  from{transform:rotate(0deg)}
  to{transform:rotate(360deg)}
}

/* Bolhas subindo */
.bubbles-container{
  position:absolute;
  inset:0;
  overflow:hidden;
  pointer-events:none;
}
.bubble{
  position:absolute;
  background:radial-gradient(circle at 30% 30%, rgba(255,255,255,0.9), rgba(255,255,255,0.3));
  border-radius:50%;
  box-shadow:inset -1px -1px 2px rgba(0,0,0,0.1), 0 0 4px rgba(255,255,255,0.5);
  animation:rise linear infinite;
}
.bubble::after{
  content:'';
  position:absolute;
  top:15%;
  left:20%;
  width:30%;
  height:30%;
  background:rgba(255,255,255,0.8);
  border-radius:50%;
}
@keyframes rise{
  0%{transform:translateY(100%) translateX(0) scale(0); opacity:0}
  10%{opacity:0.9}
  50%{transform:translateY(50%) translateX(var(--drift, 10px)) scale(1)}
  90%{opacity:0.6}
  100%{transform:translateY(-20px) translateX(calc(var(--drift, 10px) * 2)) scale(1.3); opacity:0}
}

/* Estados do botão */
.liquid-btn.filling .btn-content{
  color:white !important;
  text-shadow:0 1px 3px rgba(0,0,0,0.5);
  transform:scale(0.95);
}
.liquid-btn.complete .btn-content{
  color:white !important;
  animation:pop 0.5s cubic-bezier(0.68,-0.55,0.265,1.55);
}
@keyframes pop{
  0%{transform:scale(1)}
  50%{transform:scale(1.15)}
  100%{transform:scale(1)}
}
.liquid-btn .btn-content i{
  transition:all 0.3s ease;
}
.liquid-btn.filling .btn-content i{
  animation:spin 1s linear infinite;
}
@keyframes spin{
  from{transform:rotate(0deg)}
  to{transform:rotate(360deg)}
}

/* Brilho no líquido */
.liquid-shine{
  position:absolute;
  top:0;
  left:10%;
  width:30%;
  height:100%;
  background:linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent);
  transform:skewX(-20deg);
  animation:shine 2s ease-in-out infinite;
}
@keyframes shine{
  0%{transform:translateX(-100%) skewX(-20deg)}
  100%{transform:translateX(400%) skewX(-20deg)}
}
</style>
</head>
<body class="min-h-screen">
<div class="mesh-bg"><div class="mesh-orb orb1"></div><div class="mesh-orb orb2"></div><div class="mesh-orb orb3"></div></div>

<header class="sticky top-0 z-40 glass border-b border-white/5 backdrop-blur-2xl">
  <div class="max-w-[1600px] mx-auto px-6 py-4 flex items-center justify-between">
    <div class="flex items-center gap-5">
      <div class="relative"><div class="w-14 h-14 gold-gradient rounded-2xl flex items-center justify-center shadow-[0_8px_32px_rgba(255,215,0,0.3)]"><span class="text-black font-black text-2xl">E</span></div><div class="absolute -top-1 -right-1 w-4 h-4 bg-green-500 rounded-full border-2 border-black animate-pulse"></div></div>
      <div><h1 class="text-2xl font-black tracking-tight">ELITE COMÉRCIO</h1><p class="text-[11px] opacity-60 font-medium tracking-widest flex items-center gap-2">LIQUID SYNC • GEMINI VISION • v7.0 <span id="syncIndicator" class="flex items-center gap-1.5 ml-2 px-2.5 py-0.5 bg-green-500/20 border border-green-500/30 rounded-full text-[9px] font-black"><span class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span> AUTO SYNC ON</span></p></div>
    </div>
    <div class="flex items-center gap-3">
      <div class="hidden lg:flex items-center gap-2 glass px-4 py-2 rounded-full"><i class="fas fa-sync-alt text-[10px] opacity-60"></i><span class="text-[11px] font-bold" id="syncStatusText">Sincronizado</span><span class="text-[9px] opacity-50" id="syncTimeText"></span></div>
      <button type="button" onclick="toggleAutoSync()" id="btnAutoSync" class="btn glass px-4 py-2.5 rounded-xl text-[11px] font-black border border-green-500/30 bg-green-500/10 text-green-400"><i class="fas fa-robot"></i> AUTO ON</button>
      
      <!-- BOTÃO PUXAR COM LÍQUIDO AMARELO -->
      <button type="button" onclick="pullGitHub()" id="btnPuxar" class="liquid-btn glass px-5 py-2.5 rounded-xl text-xs font-black hover:bg-white/10 min-w-[110px] h-[42px] border border-white/10">
        <div class="liquid-fill liquid-yellow" id="liquidPuxar" style="height:0%">
          <div class="liquid-wave"></div>
          <div class="liquid-wave wave2"></div>
          <div class="liquid-shine"></div>
          <div class="bubbles-container" id="bubblesPuxar"></div>
        </div>
        <span class="btn-content relative z-10 flex items-center justify-center gap-2"><i class="fas fa-cloud-download-alt"></i> PUXAR</span>
      </button>
      
      <!-- BOTÃO ENVIAR COM LÍQUIDO AZUL -->
      <button type="button" onclick="syncGitHub()" id="btnEnviar" class="liquid-btn gold-gradient text-black px-6 py-2.5 rounded-xl text-xs font-black shadow-[0_8px_24px_rgba(255,215,0,0.3)] min-w-[130px] h-[42px] flex items-center justify-center gap-2">
        <div class="liquid-fill liquid-blue" id="liquidEnviar" style="height:0%">
          <div class="liquid-wave"></div>
          <div class="liquid-wave wave2"></div>
          <div class="liquid-shine"></div>
          <div class="bubbles-container" id="bubblesEnviar"></div>
        </div>
        <span class="btn-content relative z-10 flex items-center justify-center gap-2"><i class="fas fa-rocket"></i> ENVIAR</span>
      </button>
    </div>
  </div>
</header>

<div class="max-w-[1600px] mx-auto p-6 grid grid-cols-1 xl:grid-cols-[560px_1fr] gap-6">
  <div class="glass-gold rounded-[28px] p-7 h-fit xl:sticky top-[88px] shadow-[0_20px_80px_rgba(0,0,0,0.5)]">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-black flex items-center gap-3"><span class="w-8 h-8 gold-gradient rounded-xl flex items-center justify-center text-black text-sm"><i class="fas fa-sparkles"></i></span> CRIAR COM IA</h2>
      <span class="text-[10px] px-3 py-1 gold-gradient text-black rounded-full font-black">LIQUID SYNC</span>
    </div>

    {% if not tem_gemini %}
    <div class="bg-red-500/10 border border-red-500/20 rounded-2xl p-4 mb-6">
      <p class="font-black text-red-300 text-sm"><i class="fas fa-exclamation-triangle"></i> Configure GEMINI_API_KEY</p>
      <code class="block bg-black/50 border border-white/10 p-3 rounded-xl mt-3 text-green-400 text-xs">GEMINI_API_KEY=AIza...</code>
    </div>
    {% else %}
    <div class="bg-green-500/10 border border-green-500/20 rounded-2xl p-3 mb-6 flex items-center gap-3">
      <div class="w-8 h-8 bg-green-500 rounded-xl flex items-center justify-center text-black"><i class="fas fa-check"></i></div>
      <div class="flex-1"><p class="text-xs font-black text-green-400">GEMINI + LIQUID SYNC ATIVO</p><p class="text-[11px] opacity-60">Azul enchendo = enviando | Amarelo = recebendo | Verde = ok | Vermelho = erro</p></div>
      <div class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
    </div>
    {% endif %}

    <div class="bg-black/50 rounded-2xl p-4 border border-white/10 mb-6">
      <div class="flex items-center justify-between mb-3">
        <label class="text-[11px] font-black tracking-widest opacity-80 flex items-center gap-2"><i class="fas fa-eye text-yellow-400"></i> CAPTURA GEMINI VISION</label>
        <button type="button" id="btnAbrirBarra" class="btn w-11 h-11 gold-gradient text-black rounded-xl flex items-center justify-center shadow-lg hover:scale-105"><i class="fas fa-desktop text-lg"></i></button>
      </div>
      <textarea id="promptIA" rows="2" placeholder="Descreva o produto..." class="w-full p-4 bg-[#0a0a0a] border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400/50 resize-none"></textarea>
      <button type="button" id="btnGerarIA" class="btn w-full mt-3 py-3.5 gold-gradient text-black font-black rounded-xl text-[13px] flex items-center justify-center gap-2"><i class="fas fa-magic"></i> GERAR COM GEMINI</button>
    </div>

    <form id="formProd" class="space-y-4">
      <input id="titulo" placeholder="Título do produto" class="w-full p-4 bg-black/70 border border-white/10 rounded-xl text-sm outline-none focus:border-yellow-400/50" required>
      <div class="grid grid-cols-2 gap-3"><div class="relative"><span class="absolute left-4 top-1/2 -translate-y-1/2 text-yellow-400 font-black text-sm">R$</span><input id="valor" placeholder="109.99" class="w-full p-4 pl-10 bg-black/70 border border-white/10 rounded-xl text-sm font-bold"></div><select id="entrega" class="w-full p-4 bg-black/70 border border-white/10 rounded-xl text-sm"><option>🚚 Full</option><option>📦 Normal</option></select></div>
      <input id="link" placeholder="Link afiliado" class="w-full p-4 bg-black/70 border border-white/10 rounded-xl text-sm" required>
      <div class="grid grid-cols-2 gap-3"><input id="garantia" placeholder="Garantia" class="w-full p-4 bg-black/70 border border-white/10 rounded-xl text-sm"><input id="estoque" placeholder="Estoque" class="w-full p-4 bg-black/70 border border-white/10 rounded-xl text-sm"></div>
      <textarea id="descricao" placeholder="Descrição" rows="2" class="w-full p-4 bg-black/70 border border-white/10 rounded-xl text-sm resize-none"></textarea>
      <div><label class="text-[11px] font-bold tracking-widest opacity-60 flex items-center gap-2 mb-2"><i class="fas fa-images text-yellow-400"></i> FOTOS</label><div class="relative border-2 border-dashed border-white/10 rounded-xl p-4 hover:border-yellow-400/30 transition group bg-black/30"><input type="file" id="imagem" accept="image/*" multiple class="absolute inset-0 w-full h-full opacity-0 cursor-pointer"><div class="text-center pointer-events-none"><i class="fas fa-cloud-upload-alt text-2xl opacity-20"></i><p class="text-xs mt-2 opacity-60">Arraste ou clique</p></div></div><div id="preview" class="mt-3 grid grid-cols-4 gap-2"></div></div>
      <button type="submit" class="btn w-full py-4 gold-gradient text-black font-black rounded-xl text-[14px] tracking-widest shadow-[0_12px_32px_rgba(255,215,0,0.3)] flex items-center justify-center gap-3"><i class="fas fa-box"></i> CRIAR + AUTO ENVIAR <i class="fas fa-rocket"></i></button>
    </form>
    <p id="msg" class="mt-4 text-xs text-center min-h-[18px] font-medium"></p>
  </div>

  <div class="glass rounded-[28px] p-7 border border-white/5">
    <div class="flex items-center justify-between mb-6">
      <h2 class="font-black text-xl flex items-center gap-3"><span class="w-8 h-8 bg-white/10 rounded-xl flex items-center justify-center"><i class="fas fa-boxes text-yellow-400"></i></span> CATÁLOGO <span class="text-xs px-3 py-1 bg-yellow-400 text-black rounded-full font-black">{{produtos|length}}</span></h2>
      <button onclick="location.reload()" class="btn glass w-9 h-9 rounded-xl flex items-center justify-center hover:bg-white/10"><i class="fas fa-sync text-xs"></i></button>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 max-h-[80vh] overflow-y-auto scrollbar-thin pr-2">
      {% for p in produtos %}
      <div class="group glass rounded-2xl p-4 border border-white/5 hover:border-yellow-400/20 card-hover">
        <div class="flex gap-4"><div class="relative w-20 h-20 bg-black rounded-xl overflow-hidden border border-white/10 flex-shrink-0"><div class="w-full h-full flex items-center justify-center text-[10px] opacity-30"><i class="fas fa-image text-xl"></i></div></div><div class="flex-1 min-w-0"><div class="flex items-center gap-2 mb-1.5"><span class="text-[9px] px-2.5 py-1 rounded-full font-black bg-green-500 text-black">{{p.status}}</span><span class="text-[9px] opacity-30 truncate font-mono">{{p.id[:18]}}</span></div><h3 class="font-bold text-[13px] leading-tight line-clamp-2 group-hover:text-yellow-400 transition-colors">{{p.titulo}}</h3><p class="text-yellow-400 font-black text-[15px] mt-1">R$ {{p.valor}}</p><p class="text-[11px] opacity-50 mt-1">{{p.entrega}} • {{p.estoque}}</p></div></div>
        <div class="flex gap-2 mt-4"><button type="button" data-id="{{p.id}}" class="btn-editar flex-1 py-2.5 bg-white/[0.06] hover:bg-white/[0.10] border border-white/5 rounded-xl text-[11px] font-bold">✏️ EDITAR</button><button type="button" data-id="{{p.id}}" class="btn-excluir flex-1 py-2.5 bg-red-500/10 hover:bg-red-500/20 border border-red-500/10 text-red-400 rounded-xl text-[11px] font-bold">🗑️ EXCLUIR</button></div>
      </div>
      {% endfor %}
    </div>
  </div>
</div>

<div id="floatingBar" class="hidden fixed bottom-6 right-6 w-[700px] max-w-[96vw] bg-[#121212] rounded-[28px] border border-white/10 z-[9999] overflow-hidden max-h-[92vh] overflow-y-auto shadow-[0_40px_100px_rgba(0,0,0,0.9)]">
  <div id="dragHeader" class="drag-handle sticky top-0 z-20 flex items-center justify-between px-6 py-4 bg-black/80 backdrop-blur-2xl border-b border-white/5"><div class="flex items-center gap-3"><div class="w-8 h-8 gold-gradient rounded-xl flex items-center justify-center"><i class="fas fa-eye text-black text-sm"></i></div><div><p class="font-black text-[13px]">GEMINI VISION 2.0</p><p class="text-[10px] opacity-50">LIQUID SYNC • AUTO</p></div></div><button type="button" id="btnFecharBarra" class="btn w-9 h-9 bg-white/5 hover:bg-red-500/20 rounded-xl flex items-center justify-center"><i class="fas fa-times"></i></button></div>
  <div class="p-6">
    <div id="captureArea" class="relative w-full h-[480px] bg-[#080808] rounded-2xl border-2 border-dashed border-white/10 overflow-hidden flex flex-col items-center justify-center"><div id="capturePlaceholder" class="text-center p-8"><div class="w-20 h-20 mx-auto gold-gradient rounded-2xl flex items-center justify-center mb-5"><i class="fas fa-camera text-2xl text-black"></i></div><p class="text-[15px] font-black">CAPTURA COM LIQUID SYNC</p><p class="text-[12px] opacity-50 mt-3 max-w-[380px]">Azul = enviando pro GitHub | Amarelo = recebendo | Verde = sucesso | Vermelho = erro</p><button type="button" id="btnCapturar" class="btn mt-6 px-8 py-4 gold-gradient text-black font-black rounded-xl text-[12px] flex items-center gap-3 mx-auto"><i class="fas fa-bolt"></i> CAPTURAR TELA</button></div><img id="captureImg" class="hidden w-full h-full object-contain"><div id="markersLayer" class="absolute inset-0 pointer-events-none"></div></div>
    <div id="analiseStatus" class="hidden mt-5 p-4 bg-black rounded-2xl border border-yellow-400/20"><p class="text-xs font-black flex items-center gap-3"><span class="w-5 h-5 border-2 border-yellow-400 border-t-transparent rounded-full animate-spin"></span>🧠 GEMINI analisando...</p><div class="w-full h-2 bg-white/5 rounded-full mt-4 overflow-hidden"><div id="progressBar" class="h-full gold-gradient transition-all duration-300" style="width:0%"></div></div></div>
    <div id="resultadoIA" class="hidden mt-5"></div>
    <div id="acoesBarra" class="hidden mt-6 flex gap-3"><button type="button" id="btnCancelarBarra" class="btn flex-1 py-4 bg-white/5 border border-white/10 text-white/70 font-black rounded-xl">✕ CANCELAR</button><button type="button" id="btnConfirmarBarra" class="btn flex-1 py-4 gold-gradient text-black font-black rounded-xl"><i class="fas fa-check"></i> USAR + AUTO ENVIAR</button></div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
let imagemCapturadaBase64=null, dadosDetectados=null;

(function(){
  const bar=$('floatingBar'), handle=$('dragHeader');
  let drag=false,sx,sy,il,it;
  handle.addEventListener('mousedown',e=>{
    if(e.target.closest('button')) return;
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

function abrirBarraFlutuante(){ $('floatingBar').classList.remove('hidden'); document.body.style.overflow='hidden'; }
function fecharBarraFlutuante(){
  $('floatingBar').classList.add('hidden'); document.body.style.overflow='';
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
    const stream=await navigator.mediaDevices.getDisplayMedia({video:{displaySurface:"browser"},audio:false});
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
  let prog=0; const interval=setInterval(()=>{prog=Math.min(92,prog+4); $('progressBar').style.width=prog+'%';},250);
  try{
    const res=await fetch('/api/analisar-print',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({imagem:imagemCapturadaBase64})});
    const data=await res.json();
    dadosDetectados=data;
    clearInterval(interval); $('progressBar').style.width='100%';
    setTimeout(()=>{
      $('analiseStatus').classList.add('hidden');
      if(data.erro){
        $('resultadoIA').innerHTML=`<div class="bg-red-500/10 border-2 border-red-500/20 rounded-2xl p-5"><p class="font-black text-red-300">❌ ${data.mensagem||data.erro}</p></div>`;
        $('resultadoIA').classList.remove('hidden');
        return;
      }
      const layer=$('markersLayer'); layer.innerHTML='';
      (data.marcacoes||[]).forEach((m,i)=>{
        const el=document.createElement('div'); el.className='marker';
        el.style.left=m.x+'%'; el.style.top=m.y+'%'; el.style.width=m.w+'%'; el.style.height=m.h+'%';
        el.style.borderColor=m.color||'#22c55e'; el.style.background=(m.color||'#22c55e')+'12';
        el.style.animationDelay=(i*0.08)+'s';
        const lb=document.createElement('div'); lb.className='marker-label'; lb.style.background=m.color||'#22c55e'; lb.textContent=m.campo;
        const cf=document.createElement('div'); cf.className='conf-badge'; cf.style.borderColor=m.color||'#22c55e'; cf.style.color=m.color||'#22c55e'; cf.textContent=Math.round((m.conf||0.9)*100)+'%';
        el.appendChild(lb); el.appendChild(cf); layer.appendChild(el);
      });
      $('resultadoIA').innerHTML=`<div class="glass rounded-2xl p-5 border border-white/5"><div class="flex items-center justify-between mb-4"><span class="text-green-400 font-black text-[11px]">✅ GEMINI • ${data.marcacoes?.length||0} detectados</span></div><div class="space-y-3"><div class="p-4 bg-[#22c55e]/10 border border-[#22c55e]/20 rounded-xl"><span class="text-[#22c55e] font-black text-[11px]">📝 TÍTULO</span><p class="font-bold mt-1">${data.titulo||''}</p></div><div class="grid grid-cols-2 gap-3"><div class="p-3 bg-[#eab308]/10 border border-[#eab308]/20 rounded-xl"><span class="text-[#eab308] font-black text-[10px]">💰 VALOR</span><p class="font-black text-lg">R$ ${data.valor||''}</p></div><div class="p-3 bg-[#3b82f6]/10 border border-[#3b82f6]/20 rounded-xl"><span class="text-[#3b82f6] font-black text-[10px]">🚚 ENTREGA</span><p class="font-bold text-xs mt-1">${data.entrega||''}</p></div></div></div></div>`;
      $('resultadoIA').classList.remove('hidden');
      $('acoesBarra').classList.remove('hidden');
    },800);
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
  $('msg').innerHTML=`<span class="text-green-400 font-black">✅ Dados aplicados! Crie que já envia com líquido azul</span>`;
  fecharBarraFlutuante();
}

// ===== LIQUID ANIMATION SYSTEM =====
function createBubbles(containerId, count=12){
  const container = $(containerId);
  if(!container) return;
  container.innerHTML = '';
  for(let i=0; i<count; i++){
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    const size = 3 + Math.random()*8;
    const left = Math.random()*100;
    const duration = 1.5 + Math.random()*2.5;
    const delay = Math.random()*2;
    const drift = (Math.random()-0.5)*40;
    bubble.style.width = size+'px';
    bubble.style.height = size+'px';
    bubble.style.left = left+'%';
    bubble.style.bottom = '0';
    bubble.style.animationDuration = duration+'s';
    bubble.style.animationDelay = delay+'s';
    bubble.style.setProperty('--drift', drift+'px');
    container.appendChild(bubble);
  }
}

function startLiquidFill(buttonType, mode='fill'){
  // buttonType: 'enviar' ou 'puxar'
  const liquidId = buttonType === 'enviar' ? 'liquidEnviar' : 'liquidPuxar';
  const bubblesId = buttonType === 'enviar' ? 'bubblesEnviar' : 'bubblesPuxar';
  const btnId = buttonType === 'enviar' ? 'btnEnviar' : 'btnPuxar';
  
  const liquid = $(liquidId);
  const btn = $(btnId);
  if(!liquid || !btn) return;
  
  btn.classList.add('filling');
  btn.classList.remove('complete','error');
  liquid.className = 'liquid-fill ' + (buttonType === 'enviar' ? 'liquid-blue' : 'liquid-yellow');
  liquid.style.height = '0%';
  
  // Cria bolhas
  createBubbles(bubblesId, buttonType === 'enviar' ? 15 : 12);
  
  // Anima enchendo
  let height = 0;
  const interval = setInterval(()=>{
    height += 2 + Math.random()*3;
    if(height >= 95) height = 95;
    liquid.style.height = height+'%';
    
    // Cria bolhas extras durante enchimento
    if(Math.random() > 0.7){
      createBubbles(bubblesId, 2);
    }
  }, 80);
  
  // Salva interval para poder parar
  liquid.dataset.interval = interval;
  
  // Atualiza ícone para loading
  const content = btn.querySelector('.btn-content');
  if(content){
    content.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${buttonType === 'enviar' ? 'ENVIANDO...' : 'RECEBENDO...'}`;
  }
}

function completeLiquidFill(buttonType, success=true){
  const liquidId = buttonType === 'enviar' ? 'liquidEnviar' : 'liquidPuxar';
  const btnId = buttonType === 'enviar' ? 'btnEnviar' : 'btnPuxar';
  const bubblesId = buttonType === 'enviar' ? 'bubblesEnviar' : 'bubblesPuxar';
  
  const liquid = $(liquidId);
  const btn = $(btnId);
  if(!liquid || !btn) return;
  
  // Para animação de enchimento
  if(liquid.dataset.interval){
    clearInterval(parseInt(liquid.dataset.interval));
  }
  
  if(success){
    // Sucesso - enche 100% e fica verde
    liquid.style.height = '100%';
    liquid.className = 'liquid-fill liquid-green';
    btn.classList.remove('filling');
    btn.classList.add('complete');
    
    // Bolhas verdes comemorativas
    createBubbles(bubblesId, 20);
    
    const content = btn.querySelector('.btn-content');
    if(content){
      content.innerHTML = `<i class="fas fa-check"></i> ${buttonType === 'enviar' ? 'ENVIADO!' : 'RECEBIDO!'}`;
    }
    
    // Após 2.5s, esvazia com animação
    setTimeout(()=>{
      liquid.style.height = '0%';
      btn.classList.remove('complete','filling');
      const origContent = buttonType === 'enviar' ? '<i class="fas fa-rocket"></i> ENVIAR' : '<i class="fas fa-cloud-download-alt"></i> PUXAR';
      if(content) content.innerHTML = origContent;
      setTimeout(()=>{ liquid.innerHTML = '<div class="liquid-wave"></div><div class="liquid-wave wave2"></div><div class="liquid-shine"></div><div class="bubbles-container" id="'+bubblesId+'"></div>'; }, 500);
    }, 2500);
    
  } else {
    // Erro - fica vermelho
    liquid.style.height = '100%';
    liquid.className = 'liquid-fill liquid-red';
    btn.classList.remove('filling');
    btn.classList.add('error');
    
    const content = btn.querySelector('.btn-content');
    if(content){
      content.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ERRO`;
    }
    
    setTimeout(()=>{
      liquid.style.height = '0%';
      btn.classList.remove('error','filling');
      const origContent = buttonType === 'enviar' ? '<i class="fas fa-rocket"></i> ENVIAR' : '<i class="fas fa-cloud-download-alt"></i> PUXAR';
      if(content) content.innerHTML = origContent;
    }, 2500);
  }
}

async function checkAutoSyncStatus(){
  try{
    const res = await fetch('/api/sync-status');
    const data = await res.json();
    const statusText = $('syncStatusText');
    const timeText = $('syncTimeText');
    const indicator = $('syncIndicator');
    const btnAuto = $('btnAutoSync');
    
    // Detecta transição de estados para animar líquido
    const wasEnviando = window.lastSyncState === 'enviando';
    const wasPuxando = window.lastSyncState === 'puxando';
    const nowEnviando = data.status === 'enviando';
    const nowPuxando = data.status === 'puxando';
    const nowSincronizado = data.status === 'sincronizado';
    const nowErro = data.status === 'erro';
    
    // Inicia animação líquido quando começa a enviar/puxar
    if(!wasEnviando && nowEnviando){
      console.log('🔵 Iniciando animação líquido AZUL - enviando');
      startLiquidFill('enviar', 'fill');
    }
    if(!wasPuxando && nowPuxando){
      console.log('🟡 Iniciando animação líquido AMARELO - recebendo');
      startLiquidFill('puxar', 'fill');
    }
    
    // Completa animação quando termina
    if((wasEnviando && nowSincronizado) || (wasEnviando && nowErro)){
      console.log(nowErro ? '🔴 Erro enviar' : '🟢 Sucesso enviar - líquido verde');
      completeLiquidFill('enviar', !nowErro);
    }
    if((wasPuxando && nowSincronizado) || (wasPuxando && nowErro)){
      console.log(nowErro ? '🔴 Erro puxar' : '🟢 Sucesso puxar - líquido verde');
      completeLiquidFill('puxar', !nowErro);
    }
    
    window.lastSyncState = data.status;
    
    if(data.enabled){
      if(data.syncing){
        statusText.textContent = data.mensagem || 'Sincronizando...';
        indicator.innerHTML = `<span class="w-2 h-2 ${data.status==='enviando' ? 'bg-blue-400' : 'bg-yellow-400'} rounded-full animate-pulse"></span> ${data.status==='enviando' ? 'ENVIANDO...' : 'RECEBENDO...'}`;
        indicator.className = `flex items-center gap-1.5 ml-2 px-2.5 py-0.5 ${data.status==='enviando' ? 'bg-blue-500/20 border-blue-500/30 text-blue-400' : 'bg-yellow-500/20 border-yellow-500/30 text-yellow-400'} border rounded-full text-[9px] font-black`;
      } else {
        if(data.status === 'sincronizado'){
          statusText.textContent = data.mensagem || 'Sincronizado';
          timeText.textContent = data.last_sync ? new Date(data.last_sync).toLocaleTimeString() : '';
          indicator.innerHTML = `<span class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span> AUTO SYNC ON`;
          indicator.className = 'flex items-center gap-1.5 ml-2 px-2.5 py-0.5 bg-green-500/20 border border-green-500/30 rounded-full text-[9px] font-black';
        } else if(data.status === 'erro'){
          statusText.textContent = 'Erro: ' + (data.mensagem||'').substring(0,30);
          indicator.innerHTML = `<span class="w-2 h-2 bg-red-400 rounded-full"></span> ERRO`;
          indicator.className = 'flex items-center gap-1.5 ml-2 px-2.5 py-0.5 bg-red-500/20 border border-red-500/30 rounded-full text-[9px] font-black text-red-400';
        } else {
          statusText.textContent = data.mensagem || data.status || 'Inativo';
        }
      }
      btnAuto.innerHTML = '<i class="fas fa-robot"></i> AUTO ON';
      btnAuto.className = 'btn glass px-4 py-2.5 rounded-xl text-[11px] font-black border border-green-500/30 bg-green-500/10 text-green-400';
    } else {
      statusText.textContent = 'Auto sync OFF';
      indicator.innerHTML = `<span class="w-2 h-2 bg-gray-400 rounded-full"></span> OFF`;
      indicator.className = 'flex items-center gap-1.5 ml-2 px-2.5 py-0.5 bg-gray-500/20 border border-gray-500/30 rounded-full text-[9px] font-black text-gray-400';
      btnAuto.innerHTML = '<i class="fas fa-robot"></i> AUTO OFF';
      btnAuto.className = 'btn glass px-4 py-2.5 rounded-xl text-[11px] font-black border border-gray-500/30 bg-gray-500/10 text-gray-400';
    }
    
    if(data.just_pulled){
      console.log('🎉 Novas atualizações!');
      setTimeout(()=>location.reload(), 1500);
    }
  }catch(e){
    console.log('Erro check sync:', e);
  }
}

async function toggleAutoSync(){
  try{
    const res = await fetch('/api/toggle-autosync', {method:'POST'});
    const data = await res.json();
    alert(data.msg);
    checkAutoSyncStatus();
  }catch(e){ alert('Erro: '+e.message); }
}

document.addEventListener('DOMContentLoaded', ()=>{
  $('btnAbrirBarra').addEventListener('click', abrirBarraFlutuante);
  $('btnFecharBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCancelarBarra').addEventListener('click', fecharBarraFlutuante);
  $('btnCapturar').addEventListener('click', capturarTela);
  $('btnConfirmarBarra').addEventListener('click', confirmarCaptura);
  $('btnGerarIA').addEventListener('click', async ()=>{
    const prompt=$('promptIA').value.trim();
    if(!prompt){ alert('Descreva o produto'); return; }
    $('msg').textContent='🤖 Gemini gerando...';
    try{
      const res=await fetch('/api/gerar-ia',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
      const data=await res.json();
      if(data.titulo) $('titulo').value=data.titulo;
      if(data.valor) $('valor').value=data.valor;
      if(data.entrega) $('entrega').value=data.entrega;
      if(data.garantia) $('garantia').value=data.garantia;
      if(data.estoque) $('estoque').value=data.estoque;
      if(data.descricao) $('descricao').value=data.descricao;
      $('msg').innerHTML=`<span class="text-green-400 font-black">✨ Preenchido! Crie que já envia com líquido azul 💙</span>`;
    }catch(e){ $('msg').textContent='❌ Erro: '+e.message; }
  });
  $('imagem').addEventListener('change', e=>{
    const pr=$('preview'); pr.innerHTML='';
    [...e.target.files].forEach(f=>{
      const wrap=document.createElement('div'); wrap.className='relative group';
      const img=document.createElement('img'); img.src=URL.createObjectURL(f); img.className='w-full h-20 object-cover rounded-xl border border-white/10';
      const rm=document.createElement('button'); rm.innerHTML='✕'; rm.className='absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full text-[10px] font-black opacity-0 group-hover:opacity-100 transition';
      rm.onclick=()=>wrap.remove();
      wrap.appendChild(img); wrap.appendChild(rm); pr.appendChild(wrap);
    });
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
    if(!$('link').value.trim()){ alert('Link obrigatório'); return; }
    $('msg').innerHTML='<span class="flex items-center justify-center gap-2"><i class="fas fa-spinner fa-spin"></i> Criando + Líquido azul enchendo...</span>';
    startLiquidFill('enviar');
    try{
      const res=await fetch('/api/criar',{method:'POST',body:fd});
      const data=await res.json();
      $('msg').innerHTML=`<span class="${data.ok?'text-green-400 font-black':'text-red-400'}">${data.msg} 💙 Líquido azul enchendo...</span>`;
      if(data.ok){
        setTimeout(()=>checkAutoSyncStatus(), 500);
        setTimeout(()=>location.reload(), 3000);
      } else {
        completeLiquidFill('enviar', false);
      }
    }catch(e){
      completeLiquidFill('enviar', false);
      $('msg').textContent='❌ Erro: '+e.message;
    }
  });
  document.querySelectorAll('.btn-editar').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id=btn.getAttribute('data-id');
      const novo=prompt('Novo título para '+id+' :');
      if(!novo) return;
      startLiquidFill('enviar');
      await fetch('/api/editar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,titulo:novo})});
      setTimeout(()=>completeLiquidFill('enviar', true), 1000);
      setTimeout(()=>location.reload(), 2000);
    });
  });
  document.querySelectorAll('.btn-excluir').forEach(btn=>{
    btn.addEventListener('click', async ()=>{
      const id=btn.getAttribute('data-id');
      if(!confirm('Excluir '+id+'? Vai enviar com líquido azul!')) return;
      btn.textContent='⏳...'; btn.disabled=true;
      startLiquidFill('enviar');
      const res=await fetch('/api/deletar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id})});
      const data=await res.json();
      completeLiquidFill('enviar', data.ok);
      alert(data.msg + (data.ok ? ' 💙💚 Líquido azul → verde!' : ' 🔴 Erro'));
      setTimeout(()=>location.reload(), 1500);
    });
  });
  
  checkAutoSyncStatus();
  setInterval(checkAutoSyncStatus, 3000);
  
  if(Notification && Notification.permission === 'default'){
    Notification.requestPermission();
  }
});

async function syncGitHub(){
  if(!confirm('🚀 Enviar manual com líquido azul? (Normalmente já envia automático)')) return;
  startLiquidFill('enviar');
  const btn=$('btnEnviar');
  try{
    const res=await fetch('/api/sync',{method:'POST'});
    const data=await res.json();
    if(data.ok){
      completeLiquidFill('enviar', true);
      setTimeout(()=>{ alert('✅ '+data.msg+' 💙→💚'); location.reload(); }, 1500);
    } else {
      completeLiquidFill('enviar', false);
      alert('❌ '+data.msg+' 🔴');
    }
  }catch(e){
    completeLiquidFill('enviar', false);
    alert('Erro: '+e.message);
  }
}

async function pullGitHub(){
  if(!confirm('📥 Puxar manual com líquido amarelo? (Normalmente puxa automático)')) return;
  startLiquidFill('puxar');
  try{
    const res=await fetch('/api/pull',{method:'POST'});
    const data=await res.json();
    if(data.ok && data.msg.includes('atualizações baixadas')){
      completeLiquidFill('puxar', true);
      setTimeout(()=>{ alert('✅ '+data.msg+' 💛→💚'); location.reload(); }, 1500);
    } else if(data.ok){
      completeLiquidFill('puxar', true);
      setTimeout(()=>{ alert('ℹ️ '+data.msg); }, 1000);
      setTimeout(()=>{ const liquid=$('liquidPuxar'); if(liquid) liquid.style.height='0%'; }, 2500);
    } else {
      completeLiquidFill('puxar', false);
      alert('❌ '+data.msg);
    }
  }catch(e){
    completeLiquidFill('puxar', false);
    alert('Erro: '+e.message);
  }
}
</script>
</body>
</html>
    """
    gemini_key = get_gemini_key()
    return render_template_string(html, produtos=produtos, tem_gemini=bool(gemini_key), grok_key=gemini_key or "", base_path=str(BASE))

@app.route("/api/gerar-ia", methods=["POST"])
def api_gerar_ia():
    try:
        return jsonify(gerar_com_ia_gemini(request.json.get("prompt","")))
    except Exception as e:
        return jsonify({"titulo":request.json.get("prompt","")[:80],"valor":"97.90","entrega":"Full","garantia":"12 meses","estoque":"27","descricao":str(e)[:200]})

@app.route("/api/analisar-print", methods=["POST"])
def api_analisar_print():
    try:
        result = analisar_print_gemini_vision(request.json.get("imagem",""))
        return jsonify(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"erro":"EXCECAO","mensagem":str(e),"marcacoes":[]}), 500

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
        run_cmd("python scripts/gerar_catalogo.py")
        auto_git_push_background(f"feat: {titulo} - auto sync")
        return jsonify({"ok":True,"msg":f"✅ Criado {folder_name} - 💙 Líquido azul enchendo..."})
    except Exception as e:
        return jsonify({"ok":False,"msg":f"Erro: {e}"})

@app.route("/api/sync", methods=["POST"])
def api_sync():
    try:
        run_cmd("python scripts/gerar_catalogo.py")
        ok, out = run_cmd("git add . && git commit -m 'sync: manual liquid blue' && git push")
        if ok:
            auto_sync_config["last_push"] = datetime.now().isoformat()
            auto_sync_config["last_sync"] = datetime.now().isoformat()
            auto_sync_config["total_pushes"] += 1
            auto_sync_config["status"] = "sincronizado"
            auto_sync_config["mensagem"] = "Enviado manual - líquido verde!"
            return jsonify({"ok":True,"msg":"✅ Enviado! Líquido azul → verde 💙💚"})
        else:
            auto_sync_config["status"] = "erro"
            return jsonify({"ok":False,"msg":f"Erro push: {out[:500]}"})
    except Exception as e:
        return jsonify({"ok":False,"msg":str(e)})

@app.route("/api/pull", methods=["POST"])
def api_pull():
    try:
        has_update, msg = auto_git_pull_background()
        if has_update:
            return jsonify({"ok":True,"msg":f"✅ {msg} baixadas! Líquido amarelo → verde 💛💚"})
        else:
            return jsonify({"ok":True,"msg":f"ℹ️ {msg}"})
    except Exception as e:
        return jsonify({"ok":False,"msg":str(e)})

@app.route("/api/sync-status")
def api_sync_status():
    just_pulled = False
    if auto_sync_config["last_pull"]:
        try:
            last_pull_time = datetime.fromisoformat(auto_sync_config["last_pull"])
            if (datetime.now() - last_pull_time).total_seconds() < 15 and auto_sync_config["total_pulls"] > 0:
                just_pulled = True
        except:
            pass
    return jsonify({
        "enabled": auto_sync_config["enabled"],
        "auto_push": auto_sync_config["auto_push"],
        "auto_pull": auto_sync_config["auto_pull"],
        "status": auto_sync_config["status"],
        "syncing": auto_sync_config["syncing"],
        "mensagem": auto_sync_config["mensagem"],
        "last_sync": auto_sync_config["last_sync"],
        "last_push": auto_sync_config["last_push"],
        "last_pull": auto_sync_config["last_pull"],
        "total_pushes": auto_sync_config["total_pushes"],
        "total_pulls": auto_sync_config["total_pulls"],
        "just_pulled": just_pulled,
        "pull_interval": auto_sync_config["pull_interval"]
    })

@app.route("/api/toggle-autosync", methods=["POST"])
def api_toggle_autosync():
    auto_sync_config["enabled"] = not auto_sync_config["enabled"]
    status = "ativado" if auto_sync_config["enabled"] else "desativado"
    return jsonify({"ok":True,"msg":f"Auto Sync {status}!", "enabled": auto_sync_config["enabled"]})

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
        run_cmd("python scripts/gerar_catalogo.py")
        auto_git_push_background(f"remove: {id_} - auto sync")
        return jsonify({"ok":True,"msg":"✅ Excluído! Líquido azul enchendo..."})
    except Exception as e:
        return jsonify({"ok":False,"msg":f"Erro: {e}"})

@app.route("/api/editar", methods=["POST"])
def api_edit():
    id_=request.json.get("id"); titulo=request.json.get("titulo")
    p=PRODUTOS_DIR/id_
    if p.exists() and titulo:
        (p/"titulo.txt").write_text(titulo,encoding="utf-8")
        run_cmd("python scripts/gerar_catalogo.py")
        auto_git_push_background(f"edit: {id_} - auto sync")
    return jsonify({"ok":True, "msg": "Editado e líquido azul enchendo..."})

if __name__=="__main__":
    PRODUTOS_DIR.mkdir(exist_ok=True)
    (SITE_DIR/"produtos").mkdir(exist_ok=True)
    print("="*80)
    print("🚀 ELITE COMÉRCIO v7.0 LIQUID SYNC - BOTÕES COM LÍQUIDO E BOLHAS")
    print("="*80)
    print("💙 ENVIAR: líquido azul enchendo com bolhas → verde sucesso / vermelho erro")
    print("💛 PUXAR: líquido amarelo enchendo com bolhas → verde sucesso / vermelho erro")
    print(f"📁 BASE: {BASE}")
    print(f"🔑 GEMINI: {'✅ OK' if get_gemini_key() else '❌ FALTA'}")
    print("🌐 http://localhost:5000")
    print("="*80)
    app.run(host="127.0.0.1", port=5000, debug=True)
