import json, os, re, subprocess, sys, time, base64, winreg
import urllib.request, urllib.error

# ============================================================
#  Configuration and Paths
# ============================================================

NOTE_OPTIONS = [
    "21 hours cooldown",
    "7 days cooldown",
    "30 days cooldown",
    "181 days cooldown",
]

COOLDOWN_SECONDS = {
    "21 hours cooldown":  21 * 3600,
    "7 days cooldown":    7  * 86400,
    "30 days cooldown":   30 * 86400,
    "181 days cooldown":  181 * 86400,
}

def app_dir():
    local_app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local'))
    path = os.path.join(local_app_data, "LarpSenseNFA")
    os.makedirs(path, exist_ok=True)
    
    old_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    old_acc = os.path.join(old_dir, "accounts.json")
    new_acc = os.path.join(path, "accounts.json")
    if os.path.exists(old_acc) and not os.path.exists(new_acc):
        try:
            import shutil
            shutil.copy2(old_acc, new_acc)
        except:
            pass
            
    return path

APP_DIR        = app_dir()
ACCOUNTS_FILE  = os.path.join(APP_DIR, "accounts.json")
BLOCKLIST_FILE = os.path.join(APP_DIR, "removed.json")
CACHE_DIR      = os.path.join(APP_DIR, "session_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# ============================================================
#  Utilities (Accounts, Cooldowns)
# ============================================================

def cooldown_status(acc):
    note     = acc.get("note", "")
    set_at   = acc.get("note_set_at", 0)
    if not note or note not in COOLDOWN_SECONDS: return "", False
    duration  = COOLDOWN_SECONDS[note]
    remaining = (set_at + duration) - time.time()
    if remaining <= 0:
        return "EXPIRED", True
    h = int(remaining // 3600)
    m = int((remaining % 3600) // 60)
    if h >= 24:
        d = h // 24; h = h % 24
        return f"{d}d {h}h left", False
    return f"{h}h {m}m left", False

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE): return []
    try:
        with open(ACCOUNTS_FILE) as f: return json.load(f)
    except: return []

def save_accounts(a):
    with open(ACCOUNTS_FILE,"w") as f: json.dump(a,f,indent=2)

def load_blocklist():
    if not os.path.exists(BLOCKLIST_FILE): return set()
    try:
        with open(BLOCKLIST_FILE) as f: return set(json.load(f))
    except: return set()

def add_to_blocklist(steam_id):
    bl = load_blocklist()
    bl.add(steam_id)
    with open(BLOCKLIST_FILE,"w") as f: json.dump(list(bl),f)

# ============================================================
#  Encryption and JWT Tokens
# ============================================================

def dpapi_encrypt(data, entropy):
    try:
        import win32crypt
        # Steam uses "BObfuscateBuffer" as the description and CRYPTPROTECT_UI_FORBIDDEN (1) as flags
        return win32crypt.CryptProtectData(
            data.encode(), "BObfuscateBuffer", entropy.encode(), None, None, 1).hex()
    except ImportError:
        # Fallback will not work for Steam, but we keep it for compilation safely
        return base64.b64encode(data.encode()).decode()

def compute_crc32(data):
    b = data.encode(); crc = 0xFFFFFFFF
    for byte in b:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xEDB88320 if (crc & 1) else crc >> 1
    return hex(crc ^ 0xFFFFFFFF)[2:].lstrip("0")

def parse_jwt(token):
    try:
        parts = token.split(".")
        if len(parts) != 3: return None
        pad = 4 - len(parts[1]) % 4
        return json.loads(base64.urlsafe_b64decode(parts[1] + "=" * pad))
    except: return None

def steam64_from_token(token):
    p = parse_jwt(token)
    return p.get("sub") if p else None

def check_token(token: str) -> dict:
    result = {"valid": False, "status": "", "detail": "", "steam_id": None, "expires": None}
    if not token or not token.strip():
        result.update(status="EMPTY", detail="No token provided.")
        return result
    payload = parse_jwt(token)
    if not payload:
        result.update(status="INVALID FORMAT", detail="Token is not a valid JWT.")
        return result
    steam_id = payload.get("sub")
    if not steam_id:
        result.update(status="NO STEAMID", detail="JWT payload missing 'sub' (SteamID) field.")
        return result
    result["steam_id"] = steam_id
    iss = payload.get("iss", "")
    if "steam" not in iss.lower():
        result.update(status="WRONG ISSUER", detail=f"Issuer: '{iss}'. Expected a Steam issuer.")
        return result
    aud = payload.get("aud", [])
    if isinstance(aud, str): aud = [aud]
    if not any(x in aud for x in ("client","renew","web","derive","machine")):
        result.update(status="WRONG AUDIENCE", detail=f"Audience {aud} — not a Steam client token.")
        return result
    exp = payload.get("exp")
    if exp:
        exp_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(exp))
        if time.time() > exp:
            result.update(status="EXPIRED", detail=f"Token expired on {exp_str}.")
            result["expires"] = exp_str
            return result
        days_left = int((exp - time.time()) / 86400)
        result["expires"] = f"{exp_str}  ({days_left}d left)"
    
    pass
    persona = ""
    try:
        url = f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
        req = urllib.request.Request(url, headers={"User-Agent":"Valve/Steam HTTP/1.1"})
        with urllib.request.urlopen(req, timeout=7) as r:
            xml = r.read().decode(errors="replace")
        if "<error>" in xml.lower():
            result.update(status="ACCOUNT NOT FOUND", detail=f"SteamID {steam_id} not found on Steam.")
            return result
        m = re.search(r'<steamID><!\[CDATA\[(.*?)\]\]>', xml)
        if m: persona = m.group(1)
    except Exception as e:
        result.update(valid=True, status="VALID (offline)", detail=f"JWT OK. Cloud not reach Steam: {e}")
        return result
        
    result.update(
        valid=True, status="VALID ✓",
        detail=(f"Account: {persona}  ·  SteamID: {steam_id}" if persona else f"Account found. SteamID: {steam_id}"),
    )
    return result

# ============================================================
#  File Operations and Steam Paths
# ============================================================

def find_steam():
    for reg in [r"SOFTWARE\WOW6432Node\Valve\Steam", r"SOFTWARE\Valve\Steam"]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg) as k:
                p, _ = winreg.QueryValueEx(k, "InstallPath")
                if os.path.exists(p): return p
        except: pass
    for p in [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", r"D:\Steam", r"E:\Steam"]:
        if os.path.exists(p): return p
    return None

def get_local_vdf():
    return os.path.join(os.environ.get("LOCALAPPDATA",""), "Steam", "local.vdf")

def kill_steam():
    for proc in ["steam.exe", "steamwebhelper.exe"]:
        subprocess.run(["taskkill","/f","/im",proc], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    time.sleep(2)

def remove_readonly(path):
    try:
        if os.path.exists(path): os.chmod(path, 0o666)
    except: pass

def get_steam_avatar_url(steam_id):
    try:
        url=f"https://steamcommunity.com/profiles/{steam_id}/?xml=1"
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=5) as r: xml=r.read().decode()
        m=re.search(r'<avatarFull><!\[CDATA\[(.*?)\]\]>',xml)
        if m: return m.group(1)
    except: pass
    return None

def read_steam_accounts(steam_path):
    lu=os.path.join(steam_path,"config","loginusers.vdf")
    if not os.path.exists(lu): return []
    try:
        with open(lu,"r",encoding="utf-8",errors="replace") as f: content=f.read()
        results=[]
        for m in re.finditer(r'"(\d{17})"\s*\{([^}]*)\}',content,re.DOTALL):
            sid=m.group(1); block=m.group(2)
            nm=re.search(r'"AccountName"\s+"([^"]+)"',block)
            if nm: results.append({"steamId":sid,"username":nm.group(1)})
        return results
    except: return []

def get_steam_persona(steam_id):
    try:
        url = f"https://steamcommunity.com/profiles/{steam_id}?xml=1"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            html = response.read().decode('utf-8')
            if '<steamID><![CDATA[' in html:
                return html.split('<steamID><![CDATA[')[1].split(']]></steamID>')[0]
    except: pass
    return ""

# ============================================================
#  VDF Files Parsing and Patching
# ============================================================

def remove_from_steam_files(steam_path, steam_id, account_name):
    lu_path = os.path.join(steam_path, "config", "loginusers.vdf")
    if os.path.exists(lu_path):
        try:
            with open(lu_path,"r",encoding="utf-8",errors="replace") as f: content=f.read()
            sid_pos = content.find(f'"{steam_id}"')
            if sid_pos != -1:
                bs = content.find("{", sid_pos); depth=1; i=bs+1
                while i<len(content) and depth>0:
                    if content[i]=='{': depth+=1
                    elif content[i]=='}': depth-=1
                    i+=1
                start = content.rfind("\n", 0, sid_pos)
                if start==-1: start=sid_pos
                content = content[:start] + content[i:]
            remove_readonly(lu_path)
            with open(lu_path,"w",encoding="utf-8") as f: f.write(content)
        except: pass
    cfg_path = os.path.join(steam_path, "config", "config.vdf")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path,"r",encoding="utf-8",errors="replace") as f: content=f.read()
            am = re.search(r'"Accounts"\s*\{', content)
            if am:
                pos=am.end(); depth=1; i=pos
                while i<len(content) and depth>0:
                    if content[i]=='{': depth+=1
                    elif content[i]=='}': depth-=1
                    i+=1
                ae=i-1; inner=content[pos:ae]
                um=re.search(rf'"{re.escape(account_name)}"\s*\{{',inner)
                if um:
                    us=pos+um.start(); ue_rel=um.end()
                    depth2=1; j=pos+ue_rel
                    while j<len(content) and depth2>0:
                        if content[j]=='{': depth2+=1
                        elif content[j]=='}': depth2-=1
                        j+=1
                    start=content.rfind("\n",0,us)
                    if start==-1: start=us
                    content=content[:start]+content[j:]
            remove_readonly(cfg_path)
            with open(cfg_path,"w",encoding="utf-8") as f: f.write(content)
        except: pass
    local_path = get_local_vdf()
    if os.path.exists(local_path):
        try:
            an=account_name.split("@")[0] if "@" in account_name else account_name
            key=compute_crc32(an)+"1"
            with open(local_path,"r",encoding="utf-8",errors="replace") as f: content=f.read()
            lines=[l for l in content.splitlines(keepends=True) if key not in l]
            remove_readonly(local_path)
            with open(local_path,"w",encoding="utf-8") as f: f.writelines(lines)
        except: pass

def patch_loginusers(path, steam_id, account_name):
    ts=int(time.time()); existing=""
    if os.path.exists(path):
        try:
            with open(path,"r",encoding="utf-8",errors="replace") as f: existing=f.read()
        except: pass
    if not existing.strip():
        result=(f'"users"\n{{\n\t"{steam_id}"\n\t{{\n'
                f'\t\t"AccountName"\t\t"{account_name}"\n\t\t"PersonaName"\t\t"LarpSense"\n'
                f'\t\t"RememberPassword"\t\t"1"\n\t\t"WantsOfflineMode"\t\t"0"\n'
                f'\t\t"SkipOfflineModeWarning"\t\t"0"\n\t\t"AllowAutoLogin"\t\t"1"\n'
                f'\t\t"MostRecent"\t\t"1"\n\t\t"Timestamp"\t\t"{ts}"\n\t}}\n}}\n')
    else:
        result=re.sub(r'("MostRecent"\s+)"1"',r'\g<1>"0"',existing)
        if steam_id in result:
            sp=result.find(f'"{steam_id}"'); bs=result.find("{",sp); d=1; i=bs+1
            while i<len(result) and d>0:
                if result[i]=='{': d+=1
                elif result[i]=='}': d-=1
                i+=1
            be=i-1; blk=result[bs:be+1]
            for field,val in [("RememberPassword","1"),("AllowAutoLogin","1"),("MostRecent","1")]:
                if f'"{field}"' in blk:
                    blk=re.sub(rf'("{re.escape(field)}"\s+)"[^"]*"',rf'\g<1>"{val}"',blk)
                else:
                    blk=blk[:-1].rstrip()+f'\n\t\t"{field}"\t\t"{val}"\n\t}}'
            result=result[:bs]+blk+result[be+1:]
        else:
            entry=(f'\n\t"{steam_id}"\n\t{{\n\t\t"AccountName"\t\t"{account_name}"\n'
                   f'\t\t"PersonaName"\t\t"LarpSense"\n\t\t"RememberPassword"\t\t"1"\n'
                   f'\t\t"WantsOfflineMode"\t\t"0"\n\t\t"SkipOfflineModeWarning"\t\t"0"\n'
                   f'\t\t"AllowAutoLogin"\t\t"1"\n\t\t"MostRecent"\t\t"1"\n'
                   f'\t\t"Timestamp"\t\t"{ts}"\n\t}}\n')
            close=result.rfind("}"); result=result[:close]+entry+result[close:]
    remove_readonly(path)
    with open(path,"w",encoding="utf-8") as f: f.write(result)

def patch_config(path, steam_id, account_name):
    existing=""
    if os.path.exists(path):
        try:
            with open(path,"r",encoding="utf-8",errors="replace") as f: existing=f.read()
        except: pass
    if not existing.strip():
        import random; mtbf=''.join([str(random.randint(0,9)) for _ in range(9)])
        result=(f'"InstallConfigStore"\n{{\n\t"Software"\n\t{{\n\t\t"Valve"\n\t\t{{\n\t\t\t"Steam"\n\t\t\t{{\n'
                f'\t\t\t\t"AutoUpdateWindowEnabled"\t\t"0"\n\t\t\t\t"Accounts"\n\t\t\t\t{{\n'
                f'\t\t\t\t\t"{account_name}"\n\t\t\t\t\t{{\n\t\t\t\t\t\t"SteamID"\t\t"{steam_id}"\n'
                f'\t\t\t\t\t}}\n\t\t\t\t}}\n\t\t\t\t"MTBF"\t\t"{mtbf}"\n\t\t\t}}\n\t\t}}\n\t}}\n}}\n')
    else:
        result=existing; am=re.search(r'"Accounts"\s*\{',result)
        if am:
            pos=am.end(); d=1; i=pos
            while i<len(result) and d>0:
                if result[i]=='{': d+=1
                elif result[i]=='}': d-=1
                i+=1
            ae=i-1; inner=result[pos:ae]
            um=re.search(rf'"{re.escape(account_name)}"\s*\{{',inner)
            if um:
                us=pos+um.end(); d2=1; j=us
                while j<len(result) and d2>0:
                    if result[j]=='{': d2+=1
                    elif result[j]=='}': d2-=1
                    j+=1
                ue=j-1; ublk=result[us:ue]
                if '"SteamID"' in ublk:
                    ublk=re.sub(r'"SteamID"\s+"[^"]*"',f'"SteamID"\t\t"{steam_id}"',ublk)
                else:
                    ublk=ublk.rstrip()+f'\n\t\t\t\t\t\t"SteamID"\t\t"{steam_id}"\n\t\t\t\t\t'
                result=result[:us]+ublk+result[ue:]
            else:
                nu=(f'\n\t\t\t\t\t"{account_name}"\n\t\t\t\t\t{{\n'
                    f'\t\t\t\t\t\t"SteamID"\t\t"{steam_id}"\n\t\t\t\t\t}}\n\t\t\t\t')
                result=result[:ae]+nu+result[ae:]
        else:
            sm=re.search(r'"Steam"\s*\{',result)
            if sm:
                sp=sm.end(); d=1; i=sp
                while i<len(result) and d>0:
                    if result[i]=='{': d+=1
                    elif result[i]=='}': d-=1
                    i+=1
                ab=(f'\n\t\t\t\t"Accounts"\n\t\t\t\t{{\n\t\t\t\t\t"{account_name}"\n\t\t\t\t\t{{\n'
                    f'\t\t\t\t\t\t"SteamID"\t\t"{steam_id}"\n\t\t\t\t\t}}\n\t\t\t\t}}\n\t\t\t')
                result=result[:i-1]+ab+result[i-1:]
    remove_readonly(path)
    with open(path,"w",encoding="utf-8") as f: f.write(result)

def cache_path_for(username):
    safe=re.sub(r'[^a-zA-Z0-9_\-]','_',username)
    return os.path.join(CACHE_DIR,f"{safe}.cache")

def save_session_for(username, token):
    an=username
    key=compute_crc32(an)+"1"; enc=dpapi_encrypt(token,an)
    with open(cache_path_for(username),"w") as f: json.dump({"key":key,"enc":enc},f)

def patch_local_vdf(username, token):
    an=username
    key=compute_crc32(an)+"1"; enc=dpapi_encrypt(token,an)
    dst=get_local_vdf(); os.makedirs(os.path.dirname(dst),exist_ok=True)
    existing=""
    if os.path.exists(dst):
        try:
            with open(dst,"r",encoding="utf-8",errors="replace") as f: existing=f.read()
        except: pass
    if not existing.strip():
        result=(f'"MachineUserConfigStore"\n{{\n\t"Software"\n\t{{\n\t\t"Valve"\n\t\t{{\n\t\t\t"Steam"\n\t\t\t{{\n'
                f'\t\t\t\t"ConnectCache"\n\t\t\t\t{{\n\t\t\t\t\t"{key}"\t\t"{enc}"\n'
                f'\t\t\t\t}}\n\t\t\t}}\n\t\t}}\n\t}}\n}}\n')
    else:
        cc=re.search(r'"ConnectCache"\s*\{',existing)
        if cc:
            pos=cc.end(); d=1; i=pos
            while i<len(existing) and d>0:
                if existing[i]=='{': d+=1
                elif existing[i]=='}': d-=1
                i+=1
            ce=i-1; inner=existing[pos:ce]
            if key in inner:
                inner=re.sub(rf'({re.escape(key)}\s+)"[^"]*"',rf'\g<1>"{enc}"',inner)
            else:
                inner=inner.rstrip()+f'\n\t\t\t\t\t"{key}"\t\t"{enc}"\n\t\t\t\t'
            result=existing[:pos]+inner+existing[ce:]
        else:
            cb=(f'\n\t\t\t\t"ConnectCache"\n\t\t\t\t{{\n\t\t\t\t\t"{key}"\t\t"{enc}"\n\t\t\t\t}}\n\t\t\t')
            sm=re.search(r'"Steam"\s*\{',existing)
            if sm:
                sp=sm.end(); d=1; i=sp
                while i<len(existing) and d>0:
                    if existing[i]=='{': d+=1
                    elif existing[i]=='}': d-=1
                    i+=1
                result=existing[:i-1]+cb+existing[i-1:]
            else:
                result=existing[:existing.rfind("}")]+cb+existing[existing.rfind("}"):]
    remove_readonly(dst)
    with open(dst,"w",encoding="utf-8") as f: f.write(result)

# ============================================================
#  Main Execution Logic
# ============================================================

def do_login(account_name, token):
    """
    Function invoked by the main GUI (main.py).
    Accepts raw account name and token from Flet.
    """
    username = account_name.strip()
    token = token.strip()
        
    payload = parse_jwt(token)
    if not payload: 
        raise Exception("Invalid JWT token.")
        
    steam_id = payload.get("sub", "")
    steam_path = find_steam()
    
    if not steam_path: 
        raise Exception("Steam installation not found.")
        
    kill_steam()
    os.makedirs(os.path.join(steam_path, "config"), exist_ok=True)
    
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "AutoLoginUser", 0, winreg.REG_SZ, username)
    except: pass
    
    patch_config(os.path.join(steam_path, "config", "config.vdf"), steam_id, username)
    patch_loginusers(os.path.join(steam_path, "config", "loginusers.vdf"), steam_id, username)
    
    save_session_for(username, token)
    patch_local_vdf(username, token)
    
    subprocess.Popen([os.path.join(steam_path, "steam.exe")], creationflags=0x00000008)

if __name__ == "__main__":
    pass


def sync_steam_accounts():
    """
    Retrieves accounts from Steam files and merges them with local accounts.json.
    The Flet frontend must invoke this on startup.
    """
    steam_path = find_steam()
    if not steam_path: 
        return
        
    accounts = load_accounts()
    blocklist = load_blocklist()
    changed = False
    
    for sa in read_steam_accounts(steam_path):
        # Skip blocked/removed accounts
        if sa["steamId"] in blocklist: 
            continue
            
        # Add if does not exist
        if not any(a.get("steamId") == sa["steamId"] for a in accounts):
            accounts.append({
                "id": str(int(time.time() * 1000) + len(accounts)),
                "username": sa["username"],
                "displayName": sa["username"],
                "token": "",
                "steamId": sa["steamId"],
                "addedAt": int(time.time()),
                "noToken": True
            })
            changed = True
            
    if changed: 
        save_accounts(accounts)

