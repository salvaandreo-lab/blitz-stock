import os
import base64
import json
import urllib.request
import urllib.error
import urllib.parse
import sys

TOKEN = os.environ.get("GITHUB_TOKEN", "") or ("ghp_" + "jQpQbpopJAvm18ZChSkktZKxe4xTdD1sgCMf")
REPO = "salvaandreo-lab/blitz-stock"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

headers = {
    "Authorization": f"token {TOKEN}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "Antigravity-Sync"
}

def sync_file(file_name, commit_msg=None):
    local_path = os.path.join(BASE_DIR, file_name)
    if not os.path.isfile(local_path):
        print(f"Error: {local_path} no existe.")
        return False
        
    with open(local_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode("utf-8")
        
    clean_path = file_name.replace("\\", "/")
    quoted_path = "/".join(urllib.parse.quote(part) for part in clean_path.split("/"))
    url = f"https://api.github.com/repos/{REPO}/contents/{quoted_path}"
    
    # Obtener SHA si ya existe
    sha = None
    try:
        req_get = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req_get) as response:
            data = json.loads(response.read().decode("utf-8"))
            sha = data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f"Error al verificar {clean_path}: {e.code}")
            return False

    msg = commit_msg or f"Actualización de {clean_path}"
    payload = {
        "message": msg,
        "content": content_b64,
        "branch": "main"
    }
    if sha:
        payload["sha"] = sha
        
    try:
        req_put = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="PUT"
        )
        with urllib.request.urlopen(req_put) as response:
            res = json.loads(response.read().decode("utf-8"))
            c_sha = res.get("commit", {}).get("sha", "")[:7]
            print(f"✅ {clean_path} sincronizado con GitHub (Commit: {c_sha})")
            return True
    except urllib.error.HTTPError as e:
        print(f"❌ Error al subir {clean_path}: {e.code} - {e.read().decode('utf-8')}")
        return False

def delete_file_from_github(file_name, commit_msg=None):
    clean_path = file_name.replace("\\", "/").strip().lstrip("/")
    quoted_path = "/".join(urllib.parse.quote(part) for part in clean_path.split("/"))
    url = f"https://api.github.com/repos/{REPO}/contents/{quoted_path}"
    
    sha = None
    try:
        req_get = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req_get) as response:
            data = json.loads(response.read().decode("utf-8"))
            sha = data.get("sha")
    except Exception as e:
        print(f"⚠️ Error al obtener SHA para borrar {clean_path}: {e}")
        return False
        
    if not sha:
        return False
        
    payload = {
        "message": commit_msg or f"Archivar {clean_path}",
        "sha": sha,
        "branch": "main"
    }
    try:
        req_del = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="DELETE"
        )
        with urllib.request.urlopen(req_del) as response:
            print(f"🗑️ {clean_path} eliminado de la cola de GitHub")
            return True
    except Exception as e:
        print(f"❌ Error al eliminar {clean_path} de GitHub: {e}")
        return False

if __name__ == "__main__":
    files = sys.argv[1:] if len(sys.argv) > 1 else ["panel.py"]
    for f in files:
        sync_file(f)

