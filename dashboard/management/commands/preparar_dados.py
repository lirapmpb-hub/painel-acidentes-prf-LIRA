"""
Gera as cópias tratadas dos CSVs em data/cache, para o painel abrir mais rápido.

Uso: python manage.py preparar_dados
Roda no deploy (ver render.yaml). Localmente é opcional: sem o cache, o painel lê os CSVs.
"""
import time

from django.core.management.base import BaseCommand

from dashboard.dados import (ARQUIVO_RESUMO, anos_disponiveis, arquivo_cache, gerar_cache,
                             gerar_resumo_da_base)


class Command(BaseCommand):
    help = "Gera data/cache/datatranAAAA.pkl a partir dos CSVs da PRF, e o resumo da base"

    def handle(self, *args, **options):
        for ano in anos_disponiveis():
            inicio = time.perf_counter()
            gerar_cache(ano)
            tamanho = arquivo_cache(ano).stat().st_size / 1e6
            self.stdout.write(f"{ano}: {tamanho:.0f} MB em {time.perf_counter() - inicio:.1f}s")
        # resumo.json: anos e último mês, para a página inicial não precisar ler os acidentes
        gerar_resumo_da_base()
        self.stdout.write(f"Resumo da base: {ARQUIVO_RESUMO.read_text(encoding='utf-8')}")
