import os
import tarfile

from flask import Flask, render_template_string, request

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
EXTRACT_DIR = os.path.join(UPLOAD_DIR, "extracted")
os.makedirs(EXTRACT_DIR, exist_ok=True)


INDEX_HTML = """
<!doctype html>
<html lang="sr">
<head>
  <meta charset="utf-8">
  <title>Firmware Upgrader</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 640px; margin: 60px auto; }
    .box { border: 1px solid #ccc; border-radius: 8px; padding: 24px; }
    h1 { font-size: 20px; }
    ul { background: #f5f5f5; padding: 16px 32px; border-radius: 6px; }
    code { background: #eee; padding: 1px 4px; border-radius: 3px; }
  </style>
</head>
<body>
  <div class="box">
    <h1>Firmware Upgrader v1.0</h1>
    <p>Posaljite novu verziju firmvera kao <code>.tar.gz</code> arhivu.
       Sadrzaj arhive ce biti automatski raspakovan na serveru.</p>
    <form action="/upload" method="post" enctype="multipart/form-data">
      <input type="file" name="file" accept=".tar.gz,.tgz">
      <button type="submit">Upload</button>
    </form>
    {% if names %}
      <h3>Raspakovani fajlovi:</h3>
      <ul>
        {% for n in names %}<li><code>{{ n }}</code></li>{% endfor %}
      </ul>
    {% endif %}
  </div>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(INDEX_HTML, names=None)


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files or request.files["file"].filename == "":
        return "Nije poslat fajl.", 400

    uploaded = request.files["file"]
    archive_path = os.path.join(UPLOAD_DIR, uploaded.filename)
    uploaded.save(archive_path)

    if not tarfile.is_tarfile(archive_path):
        return "Poslati fajl nije validna tar arhiva.", 400

    # ------------------------------------------------------------------
    # RANJIVOST (CVE-2007-4559): extractall() ne proverava da li imena
    # clanova arhive izlaze iz EXTRACT_DIR pomocu "../". Maliciozna arhiva
    # moze da zapise fajl bilo gde na disku gde web proces ima pravo pisanja.
    # ------------------------------------------------------------------
    with tarfile.open(archive_path) as tar:
        tar.extractall(EXTRACT_DIR)  # <-- ranjiva linija
        names = tar.getnames()

    return render_template_string(INDEX_HTML, names=names)


if __name__ == "__main__":
    # debug=True ukljucuje auto-reloader (prati izmene .py fajlova).
    app.run(host="0.0.0.0", port=5000, debug=True)
