"""
Gera as cópias tratadas dos CSVs em data/cache, para o painel abrir mais rápido.

Uso: python manage.py preparar_dados
Roda no deploy (ver render.yaml). Localmente é opcional: sem o cache, o painel lê os CSVs.
"""
import time

from django.core.management.base import BaseCommand

from dashboard.dados import anos_disponiveis, arquivo_cache, gerar_cache


class Command(BaseCommand):
    help = "Gera data/cache/datatranAAAA.pkl a partir dos CSVs da PRF"

    def handle(self, *args, **options):
        for ano in anos_disponiveis():
            inicio = time.perf_counter()
            gerar_cache(ano)
            tamanho = arquivo_cache(ano).stat().st_size / 1e6
            self.stdout.write(f"{ano}: {tamanho:.0f} MB em {time.perf_counter() - inicio:.1f}s")
