# Painel de Acidentes nas Rodovias Federais

Painel analítico feito em Django para o Curso de Formação de Oficiais da Academia de
Polícia Militar do Cabo Branco (PMPB).

## Objetivo

Responder a uma pergunta: **onde, quando e por que acontecem os acidentes mais graves
nas rodovias federais?**

O painel tem uma página principal ("Visão geral") e 5 abas:

| Aba | O que mostra |
|---|---|
| Evolução mensal | Total de cada mês do período |
| Causas | As 10 causas com os maiores números |
| Dia e horário | Mapa de calor por dia da semana e hora, com resumo por faixa do dia |
| Tipos mais graves | Vítimas a cada 100 acidentes de cada tipo |
| Trechos críticos | Os 10 trechos de 5 km das BRs com os maiores números |

Os filtros valem para todas as abas:
- **UF:** um estado ou o Brasil inteiro.
- **De / até:** mês inicial e mês final do período.
- **Ver por:** acidentes, mortos ou feridos.

Cada gráfico traz a frase "O que o gráfico sinaliza". Ela é calculada a partir dos dados.

## Fonte dos dados

Polícia Rodoviária Federal (PRF), dados abertos de acidentes, arquivo **datatran 2026**
(`DATA/datatran2026.csv`). A base cobre apenas acidentes em rodovias federais.

O período coberto é calculado a partir da própria base e aparece na seção
"Metodologia e limitações" da Visão geral.

**Índice de gravidade** = mortos ÷ acidentes × 100

## Estrutura dos arquivos

```
PROJETO 3/
├── manage.py                  # comando principal do Django
├── config/                    # configurações do projeto
│   ├── settings.py            # configurações (ALLOWED_HOSTS, apps, etc.)
│   └── urls.py                # liga o endereço do site ao app "painel"
├── painel/                    # o app do painel
│   ├── views.py               # lê o CSV com Pandas, calcula os números,
│   │                          # gera os gráficos (Plotly) e as frases
│   ├── urls.py                # endereços: página principal e as 5 abas
│   ├── templates/painel/
│   │   └── index.html         # a página (HTML + Tailwind)
│   └── static/painel/         # brasões usados no cabeçalho
├── DATA/
│   └── datatran2026.csv       # base de dados da PRF
├── db.sqlite3                 # banco padrão do Django (o painel não usa)
└── venv/                      # ambiente virtual do Python
```

## Como rodar

No Terminal, entre na pasta do projeto. As aspas são necessárias porque o caminho tem espaço:

```bash
cd "/Users/eduardoaraujo/PROJETOS /PROJETO 3"
```

1. Ative o ambiente virtual:

   ```bash
   source venv/bin/activate
   ```

2. Instale as bibliotecas (só na primeira vez):

   ```bash
   pip install django pandas plotly
   ```

3. Ligue o servidor:

   ```bash
   python manage.py runserver
   ```

4. Abra no navegador: http://127.0.0.1:8000/

Para desligar o servidor, aperte `Ctrl + C` no Terminal.

### Acessar de outros computadores da mesma rede (opcional)

Ligue o servidor assim:

```bash
python manage.py runserver 0.0.0.0:8000
```

Depois abra `http://IP-DO-COMPUTADOR:8000/` no outro aparelho.

O IP precisa estar na lista `ALLOWED_HOSTS` em `config/settings.py`. Para descobrir o IP
do Mac, use `ipconfig getifaddr en0`.
