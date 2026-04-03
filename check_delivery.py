import os
import datetime
import http.server
import socketserver
import webbrowser
import argparse
import urllib.parse
import subprocess
import sys
import re
import tkinter as tk
from tkinter import filedialog

# --- ÇEKİRDEK MANTIK ---

def get_report_html(project_root, ref_file):
    project_root = project_root.strip().strip('"').strip("'")
    ref_file = ref_file.strip().strip('"').strip("'")
    
    if not os.path.isdir(project_root):
        return f"<div class='alert alert-danger'>HATA: Geçersiz dizin yolu!</div>"
    if not os.path.exists(ref_file):
        return f"<div class='alert alert-danger'>HATA: Referans dosyası bulunamadı!</div>"

    groups = {} 
    try:
        with open(ref_file, "r", encoding="utf-8-sig", errors="ignore") as f:
            header = f.readline()
            for line in f:
                parts = line.strip().split("\t")
                if len(parts) >= 2:
                    loc = parts[0].replace("/", "-")
                    sheet_no = parts[1].replace("/", "-")
                    if loc not in groups: groups[loc] = []
                    groups[loc].append({"sheet_no": sheet_no, "found_files": [], "other_loc_files": []})
    except Exception as e:
        return f"<div class='alert alert-danger'>HATA: Referans dosyası hatası: {str(e)}</div>"

    all_pdfs = []
    for root, dirs, files in os.walk(project_root):
        if "EX" in root.upper(): continue
        for file in files:
            if file.lower().endswith(".pdf"):
                file_path = os.path.join(root, file)
                try:
                    all_pdfs.append({
                        "path": file_path, "root": root, "name": file,
                        "size": os.path.getsize(file_path),
                        "date": datetime.datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%d.%m.%Y %H:%M')
                    })
                except: continue

    for loc, sheets in groups.items():
        for sheet in sheets:
            sheet_no = sheet["sheet_no"]
            sheet_esc = re.escape(sheet_no)
            
            for f in all_pdfs:
                filename = f["name"]
                found_in_file = False
                
                # 1. Tam Eşleşme (Boundary-aware: A-101, A-1011'i veya A-10'u yakalamaz)
                for m in re.finditer(sheet_esc, filename, re.I):
                    start, end = m.span()
                    pre_ok = (start == 0 or not filename[start-1].isalnum())
                    post_ok = (end == len(filename) or not filename[end].isalnum())
                    if pre_ok and post_ok:
                        found_in_file = True; break
                
                # 2. Liste/Aralık Fallback (Örn: A-SD-WA-003'ü ...A-SD-WA-002...01-02-03 içinde bulur)
                if not found_in_file:
                    m_parts = re.match(r"^(.*?)(\d+)$", sheet_no)
                    if m_parts:
                        prefix, num_str = m_parts.groups()
                        # Prefiks yeterince uzunsa ve dosyada varsa, sadece rakamı ara
                        if len(prefix) > 2 and prefix.lower() in filename.lower():
                            num_int = int(num_str)
                            # Standalone rakam kontrolü (03, 3 veya 003)
                            pattern = rf"(?<!\d)({num_str}|{num_int}|{num_int:02d})(?!\d)"
                            if re.search(pattern, filename):
                                found_in_file = True
                
                if found_in_file:
                    if loc.upper() in f["root"].upper().replace("_", "-"):
                        sheet["found_files"].append(f)
                    else:
                        sheet["other_loc_files"].append(f)
    
    rows_html = ""
    for loc, sheets in groups.items():
        total_sheets = len(sheets)
        ok_count = 0
        for s in sheets:
            df = s["found_files"] if s["found_files"] else s["other_loc_files"]
            if not df: continue
            unique_names = set(f["name"] for f in df)
            is_dup = len(unique_names) < len(df)
            has_zero = any(f["size"] == 0 for f in df)
            if not is_dup and not has_zero:
                ok_count += 1

        has_error = ok_count < total_sheets
        folder_status_class = "table-danger" if has_error else "table-success"
        folder_id = loc.replace(" ", "_").replace(".", "_").replace("/", "_").replace("-", "_")
        
        rows_html += f"""
            <tr class="folder-row {folder_status_class}" onclick="toggleFolder('{folder_id}')">
                <td><i class="bi bi-chevron-right" id="icon-{folder_id}"></i></td>
                <td>{loc} <span class="count-info">({ok_count}/{total_sheets})</span></td>
                <td><span class="badge {'bg-success' if not has_error else 'bg-danger'} badge-fixed">{'TAMAM' if not has_error else 'HATA'}</span></td>
                <td>-</td><td>-</td><td>-</td>
            </tr>"""
        for s in sheets:
            correct_files = s["found_files"]; other_files = s["other_loc_files"]
            display_files = correct_files if correct_files else other_files
            unique_names = set(f["name"] for f in display_files)
            is_duplicate = len(unique_names) < len(display_files)
            
            status_text = "OK"; row_class = ""; status_badge_bg = "bg-success"
            
            if not display_files:
                status_text = "EKSİK"
                status_badge_bg = "bg-danger"
                row_class = "table-light"
            elif any(f["size"] == 0 for f in display_files):
                status_text = "0 KB"
                if other_files and not correct_files: status_text += " (KONUM FARKLI)"
                status_badge_bg = "bg-danger"
                row_class = "table-warning"
            elif is_duplicate:
                status_text = f"MÜKERRER ({len(display_files)})"
                status_badge_bg = "bg-danger"
                row_class = "table-danger"
            elif other_files and not correct_files:
                status_text = "FARKLI KONUM"
                status_badge_bg = "bg-success"
                row_class = ""
            
            # Birden fazla dosya varsa aralarına <br> koyarak listele
            names = "<br>".join([f"<small>{f['name']}{('<span class=\"loc-hint\"> ['+os.path.basename(f['root'])+']</span>' if 'FARKLI' in status_text else '')}</small>" for f in display_files])
            sizes = "<br>".join([f"<small class=\"{'text-danger fw-bold' if f['size'] == 0 else ''}\">{round(f['size']/1024, 1)} KB{(' (BOŞ!)' if f['size'] == 0 else '')}</small>" for f in display_files])
            dates = "<br>".join([f"<small>{f['date']}</small>" for f in display_files])
            rows_html += f"""<tr class="sheet-row row-{folder_id} {row_class}"><td></td><td class="ps-5">{s['sheet_no']}</td><td><span class="badge {status_badge_bg} badge-fixed">{status_text}</span></td><td>{names if display_files else '-'}</td><td>{sizes if display_files else '-'}</td><td>{dates if display_files else '-'}</td></tr>"""
    return rows_html

def get_dashboard_html(default_root, default_ref):
    return f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <title>Proje Teslim Dashboard</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">
        <style>
            body {{ padding: 20px; background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; }}
            .folder-row {{ cursor: pointer; font-weight: bold; }}
            .sheet-row {{ display: none; background: #fff; }}
            .badge-fixed {{ width: 110px; }}
            .table-container {{ background: white; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); overflow: hidden; }}
            .config-panel {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
            .loc-hint {{ color: #0d6efd; font-size: 0.75rem; }}
            #treeEditor {{ font-family: 'Consolas', 'Monaco', 'Courier New', monospace; font-size: 13px; height: 500px; white-space: pre; overflow: auto; background: #fdfdfd; }}
        </style>
    </head>
    <body>
        <div class="container-fluid">
            <div class="config-panel">
                <div class="row g-3 align-items-end">
                    <div class="col-md-5">
                        <label class="form-label fw-bold">Tarama Dizini (Root)</label>
                        <div class="input-group">
                            <input type="text" id="rootPath" class="form-control" value="{default_root}">
                            <button class="btn btn-outline-secondary" onclick="browseFolder()"><i class="bi bi-folder2-open"></i></button>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label fw-bold d-flex align-items-center">
                            Referans Dosyası (TXT)
                            <button class="btn btn-link p-0 ms-2 text-primary" data-bs-toggle="modal" data-bs-target="#infoModal">
                                <i class="bi bi-info-circle-fill"></i>
                            </button>
                        </label>
                        <div class="input-group">
                            <input type="text" id="refFile" class="form-control" value="{default_ref}">
                            <button class="btn btn-outline-secondary" onclick="browseFile()"><i class="bi bi-file-earmark-text"></i></button>
                        </div>
                    </div>
                    <div class="col-md-3 d-flex gap-2">
                        <button onclick="runCheck()" class="btn btn-primary flex-grow-1"><i class="bi bi-play-fill"></i> Analiz Et</button>
                        <button class="btn btn-dark" data-bs-toggle="modal" data-bs-target="#treeModal" onclick="generateTree()"><i class="bi bi-tree"></i> Klasör Ağacı</button>
                    </div>
                </div>
            </div>

            <div class="table-container">
                <table class="table table-hover mb-0">
                    <thead class="table-dark"><tr><th style="width:40px"></th><th>Klasör / Pafta No</th><th>Durum</th><th>Dosyalar</th><th>Boyut</th><th>Tarih</th></tr></thead>
                    <tbody id="reportContent"><tr><td colspan="6" class="text-center p-5 text-muted">Analiz başlatılmadı.</td></tr></tbody>
                </table>
            </div>
        </div>

        <!-- Tree Modal -->
        <div class="modal fade" id="treeModal" tabindex="-1">
            <div class="modal-dialog modal-xl">
                <div class="modal-content">
                    <div class="modal-header bg-dark text-white">
                        <h5 class="modal-title">Klasör Yapısı (current_tree.txt)</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body p-0">
                        <textarea id="treeEditor" class="form-control border-0 rounded-0"></textarea>
                    </div>
                    <div class="modal-footer">
                        <span id="saveStatus" class="me-auto"></span>
                        <button type="button" class="btn btn-outline-dark" onclick="generateTree()"><i class="bi bi-arrow-clockwise"></i> Yeniden Oluştur</button>
                        <button type="button" class="btn btn-primary" onclick="saveTree()"><i class="bi bi-save"></i> Kaydet</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Info Modal -->
        <div class="modal fade" id="infoModal" tabindex="-1">
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Pafta Listesi Nasıl Hazırlanır?</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>Referans dosyası <strong>.txt</strong> formatında ve <strong>Tab (Sekme)</strong> ile ayrılmış iki sütundan oluşmalıdır:</p>
                        <ol>
                            <li><strong>1. Sütun (Konum):</strong> Dosyanın bulunması gereken klasör adı (Örn: <i>01_Planlar</i>).</li>
                            <li><strong>2. Sütun (Pafta No):</strong> Aranan pafta veya dosya numarası (Örn: <i>A-101</i>).</li>
                        </ol>
                        <div class="alert alert-info py-2">
                            <small><strong>Not:</strong> İlk satır başlık (Header) olarak kabul edilir ve analiz sırasında atlanır.</small>
                        </div>
                        <h6>Örnek Görünüm:</h6>
                        <pre class="bg-light p-2 border rounded" style="font-size: 12px;">Konum[TAB]Pafta No
01_Planlar[TAB]A-101
02_Görünüşler[TAB]G-201</pre>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Kapat</button>
                    </div>
                </div>
            </div>
        </div>

        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
        <script>
            async function browseFolder() {{
                const res = await fetch('/browse?type=dir');
                const path = await res.text();
                if(path) document.getElementById('rootPath').value = path;
            }}
            async function browseFile() {{
                const res = await fetch('/browse?type=file');
                const path = await res.text();
                if(path) document.getElementById('refFile').value = path;
            }}
            async function runCheck() {{
                const root = document.getElementById('rootPath').value;
                const ref = document.getElementById('refFile').value;
                document.getElementById('reportContent').innerHTML = '<tr><td colspan="6" class="text-center p-5"><div class="spinner-border text-primary"></div></td></tr>';
                const response = await fetch('/run_check?root=' + encodeURIComponent(root) + '&ref=' + encodeURIComponent(ref));
                document.getElementById('reportContent').innerHTML = await response.text();
            }}
            async function generateTree() {{
                const root = document.getElementById('rootPath').value;
                document.getElementById('treeEditor').value = "Oluşturuluyor, lütfen bekleyin...";
                const res = await fetch('/generate_tree?root=' + encodeURIComponent(root));
                document.getElementById('treeEditor').value = await res.text();
            }}
            async function saveTree() {{
                const content = document.getElementById('treeEditor').value;
                const res = await fetch('/save_tree', {{ method: 'POST', body: content }});
                const status = await res.text();
                const statusEl = document.getElementById('saveStatus');
                statusEl.innerText = status;
                statusEl.className = 'me-auto ' + (status.includes('HATA') ? 'text-danger' : 'text-success');
                setTimeout(() => statusEl.innerText = '', 3000);
            }}
            function toggleFolder(id) {{
                const rows = document.querySelectorAll('.row-' + id);
                const icon = document.getElementById('icon-' + id);
                if(!rows.length) return;
                const isHidden = rows[0].style.display === 'none' || rows[0].style.display === '';
                rows.forEach(r => r.style.display = isHidden ? 'table-row' : 'none');
                icon.className = isHidden ? 'bi bi-chevron-down' : 'bi bi-chevron-right';
            }}
        </script>
    </body>
    </html>
    """

# --- SUNUCU ---

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # İstek loglarını gizleyerek ana mesajın (Ctrl+C) görünür kalmasını sağlıyoruz.
        return

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        
        if url.path == '/run_check':
            self.send_response(200); self.send_header('Content-type','text/html;charset=utf-8'); self.end_headers()
            self.wfile.write(get_report_html(qs['root'][0], qs['ref'][0]).encode('utf-8'))
            
        elif url.path == '/browse':
            self.send_response(200); self.end_headers()
            b_type = qs.get('type', ['dir'])[0]
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            if b_type == 'dir':
                path = filedialog.askdirectory()
            else:
                path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
            root.destroy()
            self.wfile.write((path or "").encode('utf-8'))
            
        elif url.path == '/generate_tree':
            self.send_response(200); self.end_headers()
            root_path = qs['root'][0]
            try:
                # tree /f /a komutunu çalıştır
                result = subprocess.run(['tree', '/f', '/a', root_path], capture_output=True, shell=True)
                # Türkçe Windows CLI standart OEM kod sayfası CP857'dir
                content = result.stdout.decode('cp857', errors='replace')
            except Exception as e:
                content = f"HATA: Klasör ağacı oluşturulamadı: {str(e)}"
            self.wfile.write(content.encode('utf-8'))
            
        elif url.path == '/':
            self.send_response(200); self.send_header('Content-type','text/html;charset=utf-8'); self.end_headers()
            self.wfile.write(get_dashboard_html(self.server.d_root, self.server.d_ref).encode('utf-8'))
        else: super().do_GET()

    def do_POST(self):
        if self.path == '/save_tree':
            length = int(self.headers['Content-Length'])
            content = self.rfile.read(length).decode('utf-8')
            try:
                with open("current_tree.txt", "w", encoding="utf-8") as f: f.write(content)
                msg = "current_tree.txt başarıyla güncellendi!"
            except Exception as e:
                msg = f"HATA: {str(e)}"
            self.send_response(200); self.end_headers()
            self.wfile.write(msg.encode('utf-8'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--ref", default="referans_listesi.txt")
    parser.add_argument("--port", type=int, default=8888)
    args = parser.parse_args()

    print("\n" + "="*60)
    print(f" DASHBOARD: http://localhost:{args.port}")
    print(" DURDURMAK ICIN: Ctrl + C")
    print("="*60 + "\n")
    webbrowser.open(f"http://localhost:{args.port}")
    
    # HTTPServer Windows'ta KeyboardInterrupt'u daha iyi yakalar
    httpd = http.server.HTTPServer(("", args.port), DashboardHandler)
    httpd.allow_reuse_address = True
    httpd.d_root = args.root
    httpd.d_ref = args.ref
    httpd.timeout = 0.5 # Periyodik olarak sinyalleri kontrol et
    
    try:
        while True:
            httpd.handle_request()
    except KeyboardInterrupt:
        print("\nKapatılıyor...")
        httpd.server_close()

if __name__ == "__main__":
    main()
