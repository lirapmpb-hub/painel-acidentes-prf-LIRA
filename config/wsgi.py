"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()

# Importa já as URLs e as telas do painel (pandas, Plotly), em vez de deixar
# para a primeira visita. Com o gunicorn em --preload (ver render.yaml), isto
# acontece uma vez só, antes de o servidor abrir a porta para as visitas.
from django.urls import get_resolver  # noqa: E402

get_resolver().url_patterns
import dashboard.views  # noqa: E402, F401
