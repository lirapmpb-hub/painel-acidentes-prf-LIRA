# Painel de Acidentes nas Rodovias Federais

Painel web com os acidentes registrados pela Polícia Rodoviária Federal (PRF) nas rodovias federais, de 2023 a 2026, com o visual baseado no Manual de Identidade Visual da Polícia Militar da Paraíba.

O painel é voltado para a tomada de decisão: responde **onde, quando e o que fazer**. Os filtros (estado, município, rodovia, gravidade, período e avançados) ficam numa barra fixa no topo, e o painel tem cinco abas, cada uma respondendo a uma pergunta:

A **página inicial** (`/`) apresenta o painel e o que existe em cada aba, com a Paraíba como entrada principal, sem carregar os dados de acidentes. Endereços antigos com filtro (`/?uf=PB`) levam ao Panorama.

| Aba | Pergunta | O que mostra |
| --- | --- | --- |
| Panorama (`/panorama/`) | Qual é a situação? | Resumo para decisão, totais com variação sobre o ano anterior, evolução mensal, mapa, dia e hora, tipos e rodovias |
| Onde agir | Onde e quando agir? | Trechos priorizados pela gravidade (UPS) com tendência, mapa de calor da gravidade, sugestão de escala, causas por quem pode agir, perfil da BR e ranking completo dos trechos |
| Por quê | O que faz os acidentes matarem? | Condições da via e do ambiente, causas, tipos de acidente, vítimas e veículos |
| Acompanhar | Estamos melhorando? | Meta de redução, antes e depois de uma ação e comparação entre os anos |
| Estrutura PRF | Quem cobre cada área? | Regionais, delegacias e unidades operacionais |

Além das abas, a **Ficha do trecho** (`/ficha/?uf=PB&br=230&trecho=20`) reúne tudo de um trecho de 10 km, com recomendações, e pode ser impressa ou salva em PDF. Os endereços das abas antigas (`/condicoes/`, `/trechos/`, `/vitimas/`, `/anos/`, `/metas/`) redirecionam para as novas.

Indicadores usados para priorizar:

- **UPS** (Unidade Padrão de Severidade, DENATRAN): cada acidente vale 1 sem vítimas, 4 com feridos, 6 com pedestre ferido e 13 com morte.
- **Tendência**: sempre contra os mesmos meses e filtros do ano anterior.
- **Janela de risco**: dia da semana + faixa de 3 horas.
- **Causas por responsável**: infrações (PM/PRF), veículo, via (DNIT/DER), pedestres, atenção do condutor e ambiente (ver `dashboard/decisao.py`).

O botão **Baixar CSV** exporta os acidentes do filtro atual com as 30 colunas originais da PRF, e **Copiar link desta visão** copia o endereço com os filtros.

## Fonte dos dados

Arquivos `datatran` (agrupados por ocorrência) dos [dados abertos da PRF](https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf), na pasta `data/`. Para atualizar um ano, substitua o `datatranAAAA.csv` correspondente e reinicie o servidor.

## Rodar no computador

Requer Python 3.12 ou mais recente.

```bash
python -m venv venv
source venv/bin/activate        # no Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py runserver
```

Depois abra http://127.0.0.1:8000.

## Publicação

O site roda no [Render](https://render.com), configurado em `render.yaml`. Em produção, o Django lê três variáveis de ambiente:

| Variável | Uso |
| --- | --- |
| `DJANGO_SECRET_KEY` | Chave secreta (o Render gera uma automaticamente) |
| `DJANGO_DEBUG` | `False` em produção |
| `DJANGO_ALLOWED_HOSTS` | Domínios extras, separados por vírgula (opcional) |

## Estrutura

```
config/          configurações do Django
dashboard/
  dados.py       leitura e limpeza dos CSVs
  filtros.py     filtros da URL
  calculos.py    índices e agregações
  decisao.py     UPS, prioridades, janelas de risco, causas por responsável, metas e textos
  mapa.py        mapa por camadas (áreas, rodovias por trecho, prioritários, mortes, calor)
  geo.py         malhas do IBGE e ligação município PRF -> código IBGE
  graficos.py    gráficos (Plotly) e paleta de cores
  views/         um arquivo por aba (panorama, onde_agir, por_que, acompanhar, estrutura, ficha)
  tests.py       testes automáticos (python manage.py test)
  templates/     páginas HTML (Tailwind CSS)
  static/        brasão da PMPB
data/            datatran2023.csv a datatran2026.csv
data/geo/        malhas do IBGE (municípios, regiões imediatas e intermediárias); refazer com
                 python manage.py baixar_malhas
```

## Identidade visual

Cores, faixas e brasão seguem o Manual de Identidade Visual da PMPB (Centro de Comunicação Social, 2026). Os títulos usam a fonte Montserrat no lugar da Gilroy Black, que é paga.
