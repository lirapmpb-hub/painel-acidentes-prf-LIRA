"""
Testes automáticos do painel. Rodar com:

    python manage.py test

Usam os arquivos reais da pasta data/ (não há banco de dados envolvido).
"""
import re

import pandas as pd
from django.core.cache import cache
from django.test import SimpleTestCase

from . import decisao
from .calculos import candidatos


class PaginasTest(SimpleTestCase):
    """Todas as abas abrem, com e sem filtros, sem erro em nenhum gráfico."""

    URLS = [
        "/panorama/", "/panorama/?uf=PB", "/panorama/?uf=PB&municipio=JOAO%20PESSOA",
        "/onde-agir/", "/onde-agir/?uf=PB&br=230", "/onde-agir/?uf=PB&br=230&ordem=indice",
        "/onde-agir/?uf=PB&br=230&trecho=20",
        "/por-que/", "/por-que/?uf=PB&classificacao=Com%20V%C3%ADtimas%20Fatais",
        "/acompanhar/", "/acompanhar/?uf=PB&indicador=ups&meta=20&intervencao=2025-03&janela=6",
        "/estrutura/", "/estrutura/?ordem=mortos",
        "/ficha/", "/ficha/?uf=PB&br=230&trecho=20",
        "/panorama/?uf=AC&clima=Neve",  # filtro sem nenhum acidente
    ]

    def setUp(self):
        cache.clear()

    def test_paginas_abrem_sem_erro(self):
        for url in self.URLS:
            with self.subTest(url=url):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 200)
                html = resposta.content.decode()
                self.assertNotIn("Erro ao montar este gráfico", html)
                self.assertIn("Polícia Militar da Paraíba", html)

    def test_pagina_inicial(self):
        resposta = self.client.get("/")
        self.assertEqual(resposta.status_code, 200)
        html = resposta.content.decode()
        self.assertIn("Ver a Paraíba", html)
        self.assertIn('href="/panorama/?uf=PB"', html)
        self.assertNotIn("cdn.plot.ly", html)  # a página inicial não carrega gráficos

    def test_endereco_antigo_com_filtro_vai_para_o_panorama(self):
        resposta = self.client.get("/?uf=PB&br=230")
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(resposta["Location"], "/panorama/?uf=PB&br=230")

    def test_cada_subaba_tem_sua_parte(self):
        for url in ["/panorama/?uf=PB", "/onde-agir/?uf=PB&br=230", "/por-que/?uf=PB", "/acompanhar/?uf=PB"]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                links = re.findall(r'data-subaba-link="([^"]+)"', html)
                partes = re.findall(r'id="([^"]+)" data-subaba', html)
                self.assertGreaterEqual(len(links), 3)
                self.assertEqual(links, partes)

    def test_abas_antigas_redirecionam_mantendo_filtros(self):
        for antiga, nova in [("/trechos/", "/onde-agir/"), ("/condicoes/", "/por-que/"),
                             ("/vitimas/", "/por-que/"), ("/anos/", "/acompanhar/"), ("/metas/", "/acompanhar/")]:
            with self.subTest(antiga=antiga):
                resposta = self.client.get(antiga + "?uf=PB&br=230")
                self.assertEqual(resposta.status_code, 301)
                self.assertEqual(resposta["Location"], nova + "?uf=PB&br=230")

    def test_cache_atende_get_e_head_comprimidos(self):
        self.client.get("/panorama/?uf=PB")
        for metodo in (self.client.get, self.client.head):
            resposta = metodo("/panorama/?uf=PB", HTTP_ACCEPT_ENCODING="gzip")
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta["Content-Encoding"], "gzip")

    def test_exportar_csv(self):
        resposta = self.client.get("/exportar/?uf=PB&br=230")
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("text/csv", resposta["Content-Type"])
        primeira_linha = resposta.content.decode("utf-8-sig").splitlines()[0]
        self.assertTrue(primeira_linha.startswith("id;data_inversa;dia_semana"))


class FiltrosTest(SimpleTestCase):
    """Município e rodovia: cada lista mostra só o que combina com a outra escolha."""

    @staticmethod
    def opcoes(html, campo):
        bloco = re.search(rf'<select id="{campo}".*?</select>', html, re.S).group(0)
        return [v for v in re.findall(r'<option value="([^"]*)"', bloco) if v]

    def test_rodovias_do_municipio(self):
        html = self.client.get("/panorama/?uf=PB&municipio=ITAPORANGA").content.decode()
        self.assertEqual(self.opcoes(html, "br"), ["361"])

    def test_combinacao_impossivel_volta_para_todas(self):
        html = self.client.get("/panorama/?uf=PB&municipio=ITAPORANGA&br=104").content.decode()
        self.assertNotIn('value="104" selected', html)

    def test_municipios_da_rodovia(self):
        html = self.client.get("/panorama/?uf=PB&br=361").content.decode()
        municipios = self.opcoes(html, "municipio")
        self.assertIn("ITAPORANGA", municipios)
        self.assertNotIn("JOAO PESSOA", municipios)


class DecisaoTest(SimpleTestCase):
    """Cálculos de apoio à decisão."""

    def test_pesos_da_ups(self):
        df = pd.DataFrame({
            "classificacao_acidente": ["Sem Vítimas", "Com Vítimas Feridas", "Com Vítimas Feridas",
                                       "Com Vítimas Fatais", "Não informado"],
            "tipo_acidente": ["Colisão traseira", "Colisão traseira", decisao.PEDESTRE,
                              decisao.PEDESTRE, "Colisão traseira"],
        })
        self.assertEqual(list(decisao.ups(df)), [1, 4, 6, 13, 1])

    def test_tendencia(self):
        self.assertEqual(decisao.tendencia(130, 100)["nivel"], 2)
        self.assertEqual(decisao.tendencia(110, 100)["nivel"], 1)
        self.assertEqual(decisao.tendencia(100, 100)["nivel"], 0)
        self.assertEqual(decisao.tendencia(70, 100)["nivel"], -2)
        self.assertEqual(decisao.tendencia(5, 3)["texto"], "poucos casos")
        self.assertIsNone(decisao.tendencia(5, None))

    def test_toda_causa_tem_grupo(self):
        causas = pd.Series(["Ingestão de álcool pelo condutor", "Pista esburacada", "Causa nova qualquer"])
        self.assertEqual(list(decisao.grupo_da_causa(causas)),
                         [decisao.INFRACAO, decisao.VIA, decisao.AMBIENTE])

    def test_antes_depois_mesmo_numero_de_meses(self):
        indice = pd.period_range("2024-01", "2025-12", freq="M")
        serie = pd.DataFrame({coluna: range(len(indice)) for coluna in decisao.INDICADORES}, index=indice)
        resultado = decisao.antes_depois(serie, pd.Period("2025-11", freq="M"), 6)
        self.assertEqual(resultado["meses"], 1)  # só dezembro existe depois de novembro
        self.assertTrue(resultado["tem_controle"])

    def test_candidatos_juntam_os_primeiros_de_cada_medida(self):
        tabela = pd.DataFrame({"rotulo": list("abcd"), "acidentes": [100, 90, 40, 35],
                               "mortos": [1, 2, 20, 0], "indice": [1, 2.2, 50, 0]})
        self.assertEqual(set(candidatos(tabela, 1)["rotulo"]), {"a", "c"})
