
# ELITE COMÉRCIO - Catálogo com IA

Projeto: VSCode > GitHub > Render

## Como funciona:
1. `inserir.bat` abre o APP LOCAL (Flask em http://localhost:5000)
2. No app você adiciona produtos com IA (Gemini ou Grok) - campos: titulo, valor, entrega, link, garantia, estoque, imagens
3. Ao clicar em CRIAR PRODUTO, ele cria:
   `produtos/001_meu-produto/titulo.txt, valor.txt, entrega.txt, link.txt, garantia.txt, estoque.txt, descricao.txt, imagem.jpg`
4. O app gera automaticamente `site/produtos.json` e faz `git push` pro GitHub
5. O Render detecta o push e publica o site automaticamente

## Configuração inicial no VSCode:
```bash
git init
git init https://github.com/SEUUSER/elite-comercio-catalogo.git
# Crie .env a partir do .env.example e coloque sua GEMINI_API_KEY
python -m venv venv
./venv/Scripts/activate
pip install -r requirements.txt
```

## Render:
- Tipo: Static Site
- Root: site
- Build Command: (vazio)
- Publish Directory: site
Ou Web Service se quiser Python: `python scripts/gerar_catalogo.py`

## Status dos produtos:
- não publicado: pasta existe mas não foi pro git
- publicando...: fazendo push agora
- publicado: já no GitHub/Render
- erro: faltou imagem ou link

Marca: @elite_comercio_ | Irecê - BA
