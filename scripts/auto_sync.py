
import subprocess, pathlib, time
BASE = pathlib.Path(__file__).parent.parent

def git(cmd):
    return subprocess.run(cmd, cwd=BASE, shell=True, capture_output=True, text=True)

def sync():
    print("Gerando catalogo...")
    subprocess.run(["python", "scripts/gerar_catalogo.py"], cwd=BASE)
    print("Git add...")
    git("git add .")
    status = git("git status --porcelain").stdout
    if not status.strip():
        print("Nada novo para publicar")
        return
    git('git commit -m "auto: novo produto Elite Comercio"')
    print("Push GitHub...")
    result = git("git push")
    print(result.stdout, result.stderr)
    print("Publicado! Render vai atualizar em 1-2 min")

if __name__ == "__main__":
    sync()
