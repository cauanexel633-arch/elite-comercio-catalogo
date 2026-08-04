
import pathlib, json, shutil, os
BASE = pathlib.Path(__file__).parent.parent
PRODUTOS_DIR = BASE / "produtos"
SITE_DIR = BASE / "site"
SITE_PRODUTOS_JSON = SITE_DIR / "produtos.json"
SITE_IMG_DIR = SITE_DIR / "produtos"

def slugify(t):
    import re, unicodedata
    t = unicodedata.normalize('NFKD', t).encode('ascii','ignore').decode()
    t = re.sub(r'[^a-zA-Z0-9]+','-', t.lower()).strip('-')
    return t[:40]

def ler_produto(pasta):
    def read_txt(nome, default=""):
        f = pasta / f"{nome}.txt"
        return f.read_text(encoding="utf-8").strip() if f.exists() else default
    imgs = list(pasta.glob("imagem*.*")) + list(pasta.glob("*.jpg")) + list(pasta.glob("*.png"))
    img_name = ""
    if imgs:
        dest = SITE_IMG_DIR / f"{pasta.name}_{imgs[0].name}"
        SITE_IMG_DIR.mkdir(exist_ok=True)
        shutil.copy(imgs[0], dest)
        img_name = f"produtos/{dest.name}"
    return {
        "id": pasta.name,
        "titulo": read_txt("titulo", pasta.name),
        "valor": read_txt("valor", "0"),
        "entrega": read_txt("entrega", "Normal"),
        "link": read_txt("link", "#"),
        "garantia": read_txt("garantia", "30 dias"),
        "estoque": read_txt("estoque", "10"),
        "descricao": read_txt("descricao", ""),
        "imagem": img_name
    }

def limpar_imagens_orfas(produtos_validos):
    if not SITE_IMG_DIR.exists():
        return
    nomes_validos = {p["id"] for p in produtos_validos}
    for img in SITE_IMG_DIR.iterdir():
        if img.is_file():
            # se a imagem não pertence a nenhum produto válido, apaga
            pertence = any(img.name.startswith(f"{pid}_") for pid in nomes_validos)
            if not pertence:
                try:
                    img.unlink()
                    print(f"Removida órfã: {img.name}")
                except:
                    pass

def main():
    produtos = []
    if not PRODUTOS_DIR.exists():
        PRODUTOS_DIR.mkdir()
    for pasta in sorted(PRODUTOS_DIR.iterdir()):
        if pasta.is_dir():
            try:
                produtos.append(ler_produto(pasta))
            except Exception as e:
                print(f"Erro em {pasta}: {e}")
    SITE_DIR.mkdir(exist_ok=True)
    limpar_imagens_orfas(produtos)
    SITE_PRODUTOS_JSON.write_text(json.dumps(produtos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Gerado {len(produtos)} produtos em {SITE_PRODUTOS_JSON}")

if __name__ == "__main__":
    main()
