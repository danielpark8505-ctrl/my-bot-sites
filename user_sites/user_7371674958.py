import threading, sqlite3, requests, os, time, subprocess, sys, signal, datetime, re, secrets, string
from flask import Flask, render_template_string, request, session, redirect, jsonify, flash

app = Flask(__name__)
app.secret_key = "adii_hub_premium_v7_ultra_secure"

# --- SYSTEM SETUP ---
DB_PATH = os.path.abspath("adii_hub_system.db")
UPLOAD_FOLDER = os.path.abspath("uploads")
BOTS_FOLDER = os.path.abspath("active_bots")

for folder in [UPLOAD_FOLDER, BOTS_FOLDER]:
    if not os.path.exists(folder): os.makedirs(folder)

MASTER_PASS = "ffloveff"

def install_libs_from_code(code):
    libs = re.findall(r'^(?:import|from)\s+([a-zA-Z0-9_]+)', code, re.MULTILINE)
    std_libs = ['os', 'sys', 'time', 'datetime', 're', 'sqlite3', 'threading', 'subprocess', 'json', 'math', 'random', 'signal', 'requests', 'flask']
    for lib in set(libs):
        if lib not in std_libs:
            try: __import__(lib)
            except ImportError: subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def add_log(username, message, color="#7868e6"):
    ts_db = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("DELETE FROM logs WHERE ts < datetime('now', '-1 day')")
        conn.execute('INSERT INTO logs (username, msg, ts, color) VALUES (?,?,?,?)', (username, message, ts_db, color))
        conn.commit()

def init_db():
    with get_db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS accounts (username TEXT PRIMARY KEY, password TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS templates (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, code TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS user_bots (token TEXT PRIMARY KEY, owner_user TEXT, bot_username TEXT, admin_id TEXT, template_id INTEGER, status TEXT DEFAULT "LIVE", pid INTEGER)')
        conn.execute('CREATE TABLE IF NOT EXISTS bot_users (bot_token TEXT, user_id TEXT, PRIMARY KEY(bot_token, user_id))')
        conn.execute('CREATE TABLE IF NOT EXISTS logs (username TEXT, msg TEXT, ts TEXT, color TEXT)')
        # NEW: Table for One-Time Keys
        conn.execute('CREATE TABLE IF NOT EXISTS access_keys (key_code TEXT PRIMARY KEY, bound_user TEXT, created_at TEXT)')
        conn.commit()

init_db()

# --- BROADCAST ENGINE ---
def broadcast_worker(tokens, msg, f_path, f_type, username, delay):
    sc, fl = 0, 0
    # Loop through every bot token provided
    for tk in tokens:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                # Get all users who started this specific bot
                users = [r[0] for r in conn.execute('SELECT DISTINCT user_id FROM bot_users WHERE bot_token=?', (tk,)).fetchall()]
            if not users: continue
            
            # Send message to each user of this bot
            for uid in users:
                try:
                    url = f"https://api.telegram.org/bot{tk}/"
                    if f_path:
                        is_vid = "video" in str(f_type).lower()
                        method = "sendVideo" if is_vid else "sendPhoto"
                        key = "video" if is_vid else "photo"
                        with open(f_path, 'rb') as f:
                            requests.post(url+method, data={'chat_id':uid, 'caption':msg}, files={key:f}, timeout=25)
                    else:
                        requests.post(url+"sendMessage", data={'chat_id':uid, 'text':msg}, timeout=15)
                    sc += 1
                    if delay > 0: time.sleep(delay)
                except: fl += 1
        except: continue
    
    # Log the result
    log_msg = f"📢 Global Broadcast: {sc} Sent" if username == "ADMIN" else f"📢 Broadcast: {sc} Sent"
    add_log(username, log_msg, "#4CAF50" if sc > 0 else "#ff4d4d")

# --- UI DESIGN ---
UI_CSS = '''
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap" rel="stylesheet">
<style>
    :root { --p: #7868e6; --s: #b8b5ff; --bg: #0f0c29; --card: rgba(255,255,255,0.08); --glow: 0 0 15px rgba(120, 104, 230, 0.4); }
    * { box-sizing: border-box; font-family: 'Poppins', sans-serif; transition: 0.2s; }
    body { background: radial-gradient(circle at top, #1e1b4b, #0f0c29); color: white; text-align: center; margin: 0; padding: 10px; min-height: 100vh; display: flex; align-items: center; justify-content: center; }
    .card { background: var(--card); backdrop-filter: blur(20px); padding: 20px; border-radius: 20px; max-width: 380px; width: 100%; border: 1px solid rgba(255,255,255,0.1); box-shadow: var(--glow); position: relative; }
    .title-brand { font-size: 28px; font-weight: 600; background: linear-gradient(to right, #7868e6, #b8b5ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 5px; letter-spacing: 1px; }
    .subtitle { color: #aaa; font-size: 12px; margin-bottom: 20px; line-height: 1.4; }
    .btn { background: linear-gradient(135deg, var(--p), var(--s)); color: white; border: none; padding: 12px; border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; margin: 6px 0; display: inline-block; text-decoration: none; font-size: 13px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
    .btn-tg { background: #0088cc; }
    .btn-del { background: linear-gradient(135deg, #ff4d4d, #ff9999); }
    .btn-ghost { background: transparent; border: 1px solid rgba(255,255,255,0.2); color: #ccc; margin-top: 15px; }
    .btn:active { transform: scale(0.96); }
    input, textarea { width: 100%; padding: 12px; margin: 8px 0; border-radius: 10px; background: rgba(0,0,0,0.4); color: white; border: 1px solid rgba(255,255,255,0.1); outline: none; font-size: 13px; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0; }
    .scroll-list { max-height: 220px; overflow-y: auto; background: rgba(0,0,0,0.2); border-radius: 12px; padding: 8px; margin-top: 12px; }
    .bot-item { display: flex; justify-content: space-between; background: rgba(255,255,255,0.05); padding: 12px; margin: 8px 0; border-radius: 12px; font-size: 13px; align-items: center; border-left: 4px solid var(--p); }
    .key-item { display:flex; flex-direction:column; background:rgba(255,255,255,0.05); padding:10px; margin:5px 0; border-radius:8px; font-size:12px; text-align:left; border-left:3px solid orange; }
    .temp-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; padding: 5px; }
    .temp-grid .temp-card:first-child:nth-last-child(odd) { grid-column: 1 / span 2; }
    .temp-card { background: rgba(255,255,255,0.06); border-radius: 15px; padding: 15px; border: 1px solid rgba(255,255,255,0.1); cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 5px; }
    .temp-card b { color: var(--s); font-size: 14px; }
    #deploy-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #0f0c29; z-index: 9999; flex-direction: column; align-items: center; justify-content: center; }
    .loader { width: 50px; height: 50px; border: 4px solid rgba(255,255,255,0.1); border-top-color: var(--p); border-radius: 50%; animation: spin 1s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .empty-state { padding: 40px 20px; text-align: center; }
    .empty-icon { font-size: 50px; margin-bottom: 10px; opacity: 0.3; }
</style>
<script>
    function startAnim(t) { 
        document.getElementById('deploy-overlay').style.display = 'flex'; 
        document.getElementById('stx').innerText = t; 
    }
</script>
'''

TEMPLATE = UI_CSS + '<div id="deploy-overlay"><div class="loader"></div><h3 id="stx" style="margin-top:15px; font-size:14px;">READY</h3></div><div class="card">{% with msgs = get_flashed_messages(with_categories=true) %}{% if msgs %}{% for cat, m in msgs %}<div style="background:{% if cat=="error" %}#ff4d4d{% else %}#4CAF50{% endif %}; padding:10px; border-radius:10px; margin-bottom:10px; font-size:12px;">{{ m }}</div>{% endfor %}{% endif %}{% endwith %}{{ content | safe }}</div>'

# --- ROUTES ---
@app.route('/')
def home():
    if 'user' in session: return redirect('/dashboard')
    return render_template_string(TEMPLATE, content='''
        <div class="title-brand">A·D·H BOT BUILDER </div>
        <p class="subtitle">Premium Bot Builder Web.<br>Simple. Fast. Secure.</p>
        <a href="https://t.me/ADH_BOT_BUILDER" class="btn btn-tg">Join Telegram</a>
        <a href="/login_ui" style="color: #aaa; text-decoration: none; font-size: 12px; display: block; margin-top: 10px;">Login Account</a>
        <button class="btn btn-ghost" onclick="location.href='/reg_ui'">Get Started</button>
    ''')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect('/')
    with get_db() as conn: 
        logs = conn.execute('SELECT * FROM logs WHERE username=? ORDER BY rowid DESC LIMIT 5', (session['user'],)).fetchall()
    log_html = "".join([f'<div class="bot-item" style="border-left-color:{l["color"]}">{l["msg"]}</div>' for l in logs])
    
    return render_template_string(TEMPLATE, content=f'''
        <h3 style="margin:0; font-size:18px;">Welcome, {session['user']}</h3>
        <div class="grid">
            <button class="btn" onclick="location.href='/my_bots'">📜 BOTS</button>
            <button class="btn" onclick="location.href='/templates'">🚀 DEPLOY</button>
            <button class="btn" onclick="location.href='/multi_bc_ui'">📢 BROADCAST</button>
            <button class="btn" onclick="location.href='/leaderboard'">🏆 LEADERBOARD</button>
        </div>
        <button class="btn" style="background:#5e54ad; color:white; font-size:12px;" onclick="location.href='/template_studio'"> 🧩 TEMPLATE STUDIO</button>
        <button class="btn" style="background:orange; color:black; font-size:12px;" onclick="location.href='/master'"> ⚡ DEVELOPER PANEL</button>
        <div class="scroll-list">
            {log_html if log_html else '<p style="font-size:11px; opacity:0.5;">No Logs</p>'}
        </div>
        <a href="/logout" style="color:#ff4d4d; font-size:11px; display:block; margin-top:15px; text-decoration:none;">LOGOUT SESSION</a>
    ''')

# --- DEVELOPER PANEL (MASTER) ---
@app.route('/master')
def master():
    if 'master' not in session:
        return render_template_string(TEMPLATE, content='<h4>ADMIN ACCESS</h4><form action="/api/m_login" method="POST"><input name="p" type="password" placeholder="Passkey" required><button class="btn">UNLOCK</button></form><button class="btn btn-ghost" onclick="location.href=\'/dashboard\'">BACK</button>')
    
    with get_db() as conn: 
        temps = conn.execute('SELECT * FROM templates').fetchall()
        bot_count = conn.execute('SELECT COUNT(*) FROM user_bots').fetchone()[0]
        user_count = conn.execute('SELECT COUNT(DISTINCT user_id) FROM bot_users').fetchone()[0]
        keys = conn.execute('SELECT * FROM access_keys ORDER BY rowid DESC').fetchall()
    
    t_list = "".join([f'<div class="bot-item"><span>{t["title"]}</span><a href="/api/del_temp/{t["id"]}" style="color:red; text-decoration:none;">[X]</a></div>' for t in temps])
    
    k_list = ""
    for k in keys:
        status = f"✅ USED by {k['bound_user']}" if k['bound_user'] else "⏳ UNUSED"
        color = "#4CAF50" if k['bound_user'] else "orange"
        k_list += f'<div class="key-item" style="border-left-color:{color}"><span>🔑 {k["key_code"]}</span><span style="opacity:0.7">{status}</span><a href="/api/del_key/{k["key_code"]}" style="color:red; text-decoration:none; text-align:right;">DELETE</a></div>'

    # Master Panel with Global Broadcast
    return render_template_string(TEMPLATE, content=f'''
        <h4>👑 MASTER PANEL</h4>
        <div class="grid" style="background:rgba(255,255,255,0.05); padding:10px; border-radius:10px;">
            <div style="font-size:11px;">🤖 Live Bots: {bot_count}</div>
            <div style="font-size:11px;">👤 Live Users: {user_count}</div>
        </div>

        <h5 style="margin:15px 0 5px 0; text-align:left;">📢 Global Broadcast (All Bots)</h5>
        <form action="/api/bc/global" method="POST" enctype="multipart/form-data" onsubmit="startAnim('SENDING GLOBAL...')">
            <textarea name="msg" placeholder="Message to ALL bot users..." required></textarea>
            <div class="grid" style="margin:0;">
                <input type="file" name="media" accept="image/*,video/*">
                <input type="number" name="delay" placeholder="Delay (s)" value="0">
            </div>
            <button class="btn" style="background:#e91e63;">SEND TO EVERYONE</button>
        </form>
        
        <h5 style="margin:10px 0 5px 0; text-align:left;">🔑 Access Keys</h5>
        <div class="scroll-list" style="max-height:150px;">{k_list if k_list else '<p style="font-size:10px; opacity:0.5">No keys generated</p>'}</div>
        <form action="/api/gen_key" method="POST"><button class="btn" style="background:#0088cc;">GENERATE NEW KEY</button></form>

        <h5 style="margin:15px 0 5px 0; text-align:left;">📜 Templates</h5>
        <div class="scroll-list">{t_list}</div>
        <button class="btn" onclick="location.href='/add_temp_ui'">➕ ADD TEMP</button>
        <button class="btn btn-ghost" onclick="location.href='/dashboard'">BACK</button>
    ''')

# --- TEMPLATE STUDIO (CONTRIBUTOR PANEL) ---
@app.route('/template_studio')
def template_studio():
    if 'user' not in session: return redirect('/')
    
    # Check if user has verified a key
    if 'tpl_access' not in session:
        return render_template_string(TEMPLATE, content='''
            <h4>🧩 TEMPLATE STUDIO</h4>
            <p style="font-size:12px; color:#aaa;">Enter your One-Time Access Key to unlock Template creation features.</p>
            <form action="/api/verify_key" method="POST">
                <input name="key" placeholder="XXXX-XXXX-XXXX" required>
                <button class="btn">UNLOCK PANEL</button>
            </form>
            <button class="btn btn-ghost" onclick="location.href='/dashboard'">BACK</button>
        ''')
    
    # Authorized View
    with get_db() as conn:
        temps = conn.execute('SELECT * FROM templates').fetchall()
    
    t_list = "".join([f'<div class="bot-item"><span>{t["title"]}</span><span style="font-size:10px; opacity:0.5;">ID: {t["id"]}</span></div>' for t in temps])
    
    return render_template_string(TEMPLATE, content=f'''
        <h4>🧩 STUDIO ACCESS</h4>
        <div style="background:#4CAF50; color:white; padding:5px; border-radius:5px; font-size:11px; margin-bottom:10px;">✅ Authorized: {session['user']}</div>
        
        <form action="/api/studio_add_temp" method="POST">
            <input name="title" placeholder="Template Name" required>
            <textarea name="code" placeholder="Python Code..." rows="8" required></textarea>
            <button class="btn">SAVE TEMPLATE</button>
        </form>
        
        <h5 style="margin:15px 0 5px 0; text-align:left;">📚 Existing Templates</h5>
        <div class="scroll-list">{t_list}</div>
        
        <button class="btn btn-ghost" onclick="location.href='/dashboard'">BACK</button>
    ''')

# --- API: KEY SYSTEM ---
@app.route('/api/gen_key', methods=['POST'])
def api_gen_key():
    if 'master' not in session: return redirect('/')
    # Generate random key
    new_key = "ADH-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    with get_db() as conn:
        conn.execute('INSERT INTO access_keys (key_code, created_at) VALUES (?, datetime("now"))', (new_key,))
        conn.commit()
    flash(f"🔑 Key Generated: {new_key}", "success")
    return redirect('/master')

@app.route('/api/del_key/<key>')
def api_del_key(key):
    if 'master' not in session: return redirect('/')
    with get_db() as conn:
        conn.execute('DELETE FROM access_keys WHERE key_code=?', (key,))
        conn.commit()
    flash("🗑️ Key Deleted", "success")
    return redirect('/master')

@app.route('/api/verify_key', methods=['POST'])
def api_verify_key():
    if 'user' not in session: return redirect('/')
    key_input = request.form['key'].strip()
    user = session['user']
    
    with get_db() as conn:
        row = conn.execute('SELECT * FROM access_keys WHERE key_code=?', (key_input,)).fetchone()
        
        if not row:
            flash("❌ Invalid Key!", "error")
            return redirect('/template_studio')
            
        if row['bound_user'] is None:
            # First use -> Bind to user
            conn.execute('UPDATE access_keys SET bound_user=? WHERE key_code=?', (user, key_input))
            conn.commit()
            session['tpl_access'] = True
            flash("✅ Key Linked Successfully!", "success")
            return redirect('/template_studio')
            
        elif row['bound_user'] == user:
            # Re-login with bound key
            session['tpl_access'] = True
            flash("✅ Welcome Back!", "success")
            return redirect('/template_studio')
            
        else:
            # Key used by someone else
            flash("❌ This Key is already used by another account!", "error")
            return redirect('/template_studio')

@app.route('/api/studio_add_temp', methods=['POST'])
def api_studio_add_temp():
    if 'user' not in session or 'tpl_access' not in session:
        return redirect('/')
    with get_db() as conn: 
        conn.execute('INSERT INTO templates (title, code) VALUES (?,?)', (request.form['title'], request.form['code']))
        conn.commit()
    flash("✅ Template Added!", "success")
    return redirect('/template_studio')


# --- NORMAL ROUTES (Bot, BC, etc) ---
@app.route('/my_bots')
def my_bots():
    if 'user' not in session: return redirect('/')
    with get_db() as conn: bots = conn.execute('SELECT * FROM user_bots WHERE owner_user=?', (session['user'],)).fetchall()
    if not bots:
        h = '<div class="empty-state"><div class="empty-icon">📂</div><h4 style="margin:0;">No Active Bots</h4><p style="font-size:12px; color:#aaa;">You haven\'t deployed any bots yet.</p><button class="btn" onclick="location.href=\'/templates\'">Deploy First Bot</button></div>'
    else:
        h = '<h4>📜 MY BOTS</h4><div class="scroll-list">' + "".join([f'<div class="bot-item"><span>@{b["bot_username"]}</span><a href="/api/del_bot/{b["token"]}" style="color:red; text-decoration:none;">🗑️ DELETE </a></div>' for b in bots]) + '</div>'
    return render_template_string(TEMPLATE, content=h+'<button class="btn btn-ghost" onclick="location.href=\'/dashboard\'">BACK</button>')

# --- BROADCAST API (Logic Updated) ---
@app.route('/api/bc/<scope>', methods=['POST'])
def api_bc(scope):
    # Logic: Global requires 'master', User requires 'user'
    
    with get_db() as conn:
        if scope == "global":
            if 'master' not in session: return redirect('/')
            # GLOBAL: Select ALL tokens from ALL users
            tokens = [b['token'] for b in conn.execute('SELECT token FROM user_bots').fetchall()]
            user_log = "ADMIN"
        else:
            if 'user' not in session: return redirect('/')
            # USER: Select ONLY user's tokens
            tokens = [b['token'] for b in conn.execute('SELECT token FROM user_bots WHERE owner_user=?', (session['user'],)).fetchall()]
            user_log = session['user']
    
    if not tokens:
        flash("❌ Error: No live bots found to broadcast!", "error")
        return redirect('/dashboard' if scope != 'global' else '/master')

    msg, media, delay = request.form.get('msg', '').strip(), request.files.get('media'), int(request.form.get('delay', 0))
    f_path, f_type = None, None
    if media and media.filename != '':
        f_path = os.path.join(UPLOAD_FOLDER, f"bc_{int(time.time())}_{media.filename}"); media.save(f_path); f_type = media.content_type
    
    # Start thread
    threading.Thread(target=broadcast_worker, args=(tokens, msg, f_path, f_type, user_log, delay)).start()
    
    flash("📢 Broadcast Started!", "success")
    return redirect('/dashboard' if scope != 'global' else '/master')

@app.route('/templates')
def show_templates():
    if 'user' not in session: return redirect('/')
    with get_db() as conn: temps = conn.execute('SELECT * FROM templates').fetchall()
    h = '<h4>🚀 SELECT TEMP</h4><div class="scroll-list"><div class="temp-grid">' + "".join([f'<div class="temp-card" onclick="location.href=\'/deploy_form/{t["id"]}\'"><b>{t["title"]}</b><span style="font-size:10px; opacity:0.6;">CLICK TO GO</span></div>' for t in temps])
    return render_template_string(TEMPLATE, content=h+'</div></div><button class="btn btn-ghost" onclick="location.href=\'/dashboard\'">BACK</button>')

@app.route('/deploy_form/<tid>')
def deploy_form(tid):
    if 'user' not in session: return redirect('/')
    return render_template_string(TEMPLATE, content=f'<h4>⚙️ CHOOSE YOUR BOT </h4><form action="/api/deploy" method="POST" onsubmit="startAnim(\'DEPLOYING...\')"><input type="hidden" name="tid" value="{tid}"><input name="tk" placeholder="Bot Token" required><input name="adm" placeholder="Admin ID" required><button class="btn">LAUNCH</button></form><button class="btn btn-ghost" onclick="location.href=\'/templates\'">BACK</button>')

@app.route('/api/deploy', methods=['POST'])
def api_deploy():
    if 'user' not in session: return redirect('/')
    tk, adm, tid = request.form['tk'].strip(), request.form['adm'].strip(), request.form['tid']
    with get_db() as conn:
        if conn.execute('SELECT 1 FROM user_bots WHERE token=?', (tk,)).fetchone():
            flash("❌ Already Active!", "error"); return redirect('/dashboard')
    try:
        r = requests.get(f"https://api.telegram.org/bot{tk}/getMe", timeout=12).json()
        if not r.get('ok'): flash("❌ Invalid Token!", "error"); return redirect('/dashboard')
        with get_db() as conn:
            raw = conn.execute('SELECT code FROM templates WHERE id=?', (tid,)).fetchone()['code']
            install_libs_from_code(raw)
            tracker = f'\ndef track_user(uid):\n try:\n  with sqlite3.connect("{DB_PATH}") as c: c.execute("INSERT OR IGNORE INTO bot_users VALUES (?,?)", ("{tk}", str(uid)))\n except: pass\n'
            final_code = "import sqlite3, os\n" + tracker + raw.replace("YOUR_BOT_TOKEN_HERE", tk).replace("YOUR_ADMIN_ID_HERE", adm)
            f_path = os.path.join(BOTS_FOLDER, f"bot_{tk[:8]}.py")
            with open(f_path, "w", encoding="utf-8") as f: f.write(final_code)
            proc = subprocess.Popen([sys.executable, f_path])
            conn.execute('INSERT INTO user_bots (token, owner_user, bot_username, admin_id, template_id, pid) VALUES (?,?,?,?,?,?)', (tk, session['user'], r['result']['username'], adm, tid, proc.pid))
            conn.commit()
        add_log(session['user'], f"🚀 Deployed: @{r['result']['username']}", "#4CAF50")
        return redirect('/my_bots')
    except Exception as e: flash(f"Err: {str(e)}", "error"); return redirect('/dashboard')

@app.route('/multi_bc_ui')
def multi_bc_ui():
    if 'user' not in session: return redirect('/')
    return render_template_string(TEMPLATE, content='<h4>📢 BROADCAST</h4><form action="/api/bc/user" method="POST" enctype="multipart/form-data" onsubmit="startAnim(\'SENDING...\')"><textarea name="msg" placeholder="Message..." required></textarea><input type="file" name="media" accept="image/*,video/*"><input type="number" name="delay" placeholder="Delay (Sec)" value="0"><button class="btn">START</button></form><button class="btn btn-ghost" onclick="location.href=\'/dashboard\'">BACK</button>')

@app.route('/leaderboard')
def leaderboard():
    if 'user' not in session: return redirect('/')
    with get_db() as conn: data = conn.execute('SELECT owner_user, COUNT(*) as cnt FROM user_bots GROUP BY owner_user ORDER BY cnt DESC LIMIT 10').fetchall()
    h = '<h4>🏆 RANKING</h4><div class="scroll-list">' + "".join([f'<div class="bot-item"><span>#{i+1} {r["owner_user"]}</span><b>{r["cnt"]}</b></div>' for i, r in enumerate(data)])
    return render_template_string(TEMPLATE, content=h+'</div><button class="btn btn-ghost" onclick="location.href=\'/dashboard\'">BACK</button>')

@app.route('/api/del_bot/<tk>')
def api_del_bot(tk):
    with get_db() as conn:
        bot = conn.execute('SELECT pid FROM user_bots WHERE token=?', (tk,)).fetchone()
        if bot and bot['pid']:
            try: os.kill(bot['pid'], signal.SIGTERM)
            except: pass
        conn.execute('DELETE FROM user_bots WHERE token=?', (tk,)); conn.commit()
    return redirect('/my_bots')

@app.route('/add_temp_ui')
def add_temp_ui():
    if 'master' not in session: return redirect('/master')
    return render_template_string(TEMPLATE, content='<h4>ADD TEMP</h4><form action="/api/add_temp" method="POST"><input name="title" placeholder="Name" required><textarea name="code" placeholder="Python Code..." rows="6" required></textarea><button class="btn">SAVE</button></form><button class="btn btn-ghost" onclick="location.href=\'/master\'">BACK</button>')

@app.route('/api/add_temp', methods=['POST'])
def api_add_temp():
    if 'master' not in session: return redirect('/')
    with get_db() as conn: conn.execute('INSERT INTO templates (title, code) VALUES (?,?)', (request.form['title'], request.form['code'])); conn.commit()
    return redirect('/master')

@app.route('/api/del_temp/<int:tid>')
def api_del_temp(tid):
    if 'master' not in session: return redirect('/') # Only master can delete
    with get_db() as conn: conn.execute('DELETE FROM templates WHERE id=?', (tid,)); conn.commit()
    return redirect('/master')

@app.route('/login_ui')
def login_ui(): return render_template_string(TEMPLATE, content='<h3>LOGIN</h3><form action="/api/login" method="POST"><input name="u" placeholder="User" required><input name="p" type="password" placeholder="Pass" required><button class="btn">ENTER</button></form><a href="/" style="font-size:11px; color:#aaa; text-decoration:none;">Back Home</a>')

@app.route('/reg_ui')
def reg_ui(): return render_template_string(TEMPLATE, content='<h3>REGISTER</h3><form action="/api/reg" method="POST"><input name="u" placeholder="User" required><input name="p" type="password" placeholder="Pass" required><button class="btn">CREATE</button></form><a href="/" style="font-size:11px; color:#aaa; text-decoration:none;">Back Home</a>')

@app.route('/api/login', methods=['POST'])
def api_login():
    with get_db() as conn:
        res = conn.execute('SELECT * FROM accounts WHERE username=? AND password=?', (request.form['u'], request.form['p'])).fetchone()
        if res: session['user'] = request.form['u']; return redirect('/dashboard')
    flash("❌ Invalid!", "error"); return redirect('/login_ui')

@app.route('/api/m_login', methods=['POST'])
def m_login_api():
    if request.form['p'] == MASTER_PASS: session['master'] = True; return redirect('/master')
    flash("❌ Wrong!", "error"); return redirect('/master')

@app.route('/api/reg', methods=['POST'])
def api_reg():
    with get_db() as conn:
        try: conn.execute('INSERT INTO accounts VALUES (?,?)', (request.form['u'], request.form['p'])); conn.commit(); session['user'] = request.form['u']; return redirect('/dashboard')
        except: flash("❌ Exists!", "error"); return redirect('/reg_ui')

@app.route('/logout')
def logout(): session.clear(); return redirect('/')

if __name__ == '__main__':
    app.run(port=8080, host='0.0.0.0', threaded=True)