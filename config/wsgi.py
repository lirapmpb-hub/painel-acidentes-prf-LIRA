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

# Em produção (gunicorn), já carrega os dados e monta as páginas principais
# assim que o servidor liga, em vez de esperar a primeira visita.
from dashboard.cache_paginas import aquecer_em_segundo_plano  # noqa: E402

aquecer_em_segundo_plano()
