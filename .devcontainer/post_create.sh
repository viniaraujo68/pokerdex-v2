set -euo pipefail

chmod -R u+rwX,go+rwX /workspace || true

if [ ! -f manage.py ]; then
  django-admin startproject pokerdex .
  python manage.py startapp core
fi

python - <<'PY'
from pathlib import Path
p = Path("pokerdex/settings.py")
s = p.read_text()

s = s.replace("TIME_ZONE = 'UTC'", "TIME_ZONE = \"America/Sao_Paulo\"")

s = s.replace(
    "'django.contrib.staticfiles',",
    "'django.contrib.staticfiles',\n    'core',"
)

if "ALLOWED_HOSTS = []" in s:
    s = s.replace(
        "ALLOWED_HOSTS = []",
        "import os\nALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS','*').split(',')"
    )

if "DEBUG = True" in s:
    s = s.replace(
        "DEBUG = True",
        "import os\nDEBUG = os.getenv('DJANGO_DEBUG','1')=='1'"
    )

if "SECRET_KEY =" in s and "DJANGO_SECRET_KEY" not in s:
    s = s.replace(
        "SECRET_KEY =",
        "import os\nSECRET_KEY = os.getenv('DJANGO_SECRET_KEY','dev-please-change')\
    )

p.write_text(s)

Path("pokerdex/__init__.py").write_text("\n")
PY

if ! grep -q "path('api/health'" pokerdex/urls.py; then
python - <<'PY'
from pathlib import Path
u = Path("pokerdex/urls.py").read_text()

if "from django.contrib import admin" not in u or "from django.urls import path" not in u:
    u = "from django.contrib import admin\nfrom django.urls import path\n" + u.splitlines(keepends=True)[-1]

u = u.replace(
    "urlpatterns = [",
    "urlpatterns = [\n    path('api/health', lambda r: __import__('django').http.response.JsonResponse({'status':'ok'})),"
)

Path("pokerdex/urls.py").write_text(u)
PY
fi

echo "postCreate.sh finalizado com sucesso."
