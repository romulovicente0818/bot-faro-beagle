import time
import cloudscraper
from datetime import datetime, timedelta
import zoneinfo

# curl_cffi é usado como segunda camada quando o SofaScore devolve 403.
# O código continua funcionando com cloudscraper caso a biblioteca não esteja instalada.
try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE-aO4rOeondyaG_0eC0-3OJl4yAzXpBjc'
CHAT_ID = '-1004321907969'

TERMOS_IGNORADOS = [
    # Categorias de Base
    'u15', 'u16', 'u17', 'u18', 'u19', 'u20', 'u21', 'u22', 'u23',
    'sub-15', 'sub-16', 'sub-17', 'sub-18', 'sub-19', 'sub-20',
    'sub-21', 'sub-22', 'sub-23',
    'sub15', 'sub16', 'sub17', 'sub18', 'sub19', 'sub20',
    'sub21', 'sub22', 'sub23',
    ' youth', 'youth ', 'juniors', 'junior', 'reserve', 'reserves', 'academy',
    'proliga', 'liga pro', 'cup u', 'league u', 'trophy u', 'championship u',

    # Feminino
    'women', 'feminino', 'femeni', 'women\'s', 'female', ' w ',

    # Ligas Menores / Muito Under / Amadoras
    'amateur', 'amador', 'regionaliga', 'oberliga', 'landesliga',
    'district', 'county', 'regional league', 'non-league',
    'primera c', 'primera d', 'tercera'
]
# ==============================================================================

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

# Segunda sessão opcional, com fingerprint TLS de Chrome.
# É particularmente útil quando o CDN do SofaScore responde 403 ao cloudscraper.
cffi_scraper = None
if cffi_requests is not None:
    try:
        cffi_scraper = cffi_requests.Session(impersonate='chrome')
    except Exception as e:
        print(f'Não foi possível iniciar curl_cffi: {e}')

# Camada de acesso ao SofaScore com headers de navegador e múltiplas rotas.
SOFASCORE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.sofascore.com/',
    'Origin': 'https://www.sofascore.com',
    'X-Requested-With': 'XMLHttpRequest',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
}

# Ordem normal: API principal -> proxy do próprio site.
# O espelho é usado somente como contingência após 403, evitando uma
# requisição extra em cada ciclo normal do bot.
SOFASCORE_BASES = [
    'https://api.sofascore.com/api/v1',
    'https://www.sofascore.com/api/v1',
]
SOFASCORE_403_FALLBACKS = [
    'https://api.sofascore.app/api/v1',
]

def sofascore_get(path, timeout=10):
    path = path.lstrip('/')
    ultimo_status = None
    urls_403 = []

    # 1) Tentativa normal com cloudscraper.
    for base in SOFASCORE_BASES:
        url = f'{base}/{path}'
        try:
            res = scraper.get(
                url,
                headers=SOFASCORE_HEADERS,
                timeout=timeout
            )
            ultimo_status = res.status_code

            if res.status_code == 200:
                return res

            if res.status_code == 403:
                urls_403.append(url)
                continue

            # 404 em endpoints individuais é esperado em alguns eventos/dados.
            if res.status_code != 404:
                print(f'SofaScore {url}: status {res.status_code}')

        except Exception as e:
            print(f'Erro SofaScore {url}: {e}')

    # 2) Se houve 403, tenta primeiro o espelho.
    if urls_403:
        for base in SOFASCORE_403_FALLBACKS:
            url = f'{base}/{path}'
            try:
                res = scraper.get(
                    url,
                    headers=SOFASCORE_HEADERS,
                    timeout=timeout
                )
                ultimo_status = res.status_code
                if res.status_code == 200:
                    print(f'SofaScore: rota recuperada pelo espelho: {url}')
                    return res
            except Exception as e:
                print(f'Erro SofaScore espelho {url}: {e}')

    # 3) Se o 403 persistir, tenta fingerprint TLS de Chrome.
    if urls_403 and cffi_scraper is not None:
        for url in urls_403:
            try:
                res = cffi_scraper.get(
                    url,
                    headers=SOFASCORE_HEADERS,
                    timeout=timeout
                )
                ultimo_status = res.status_code
                if res.status_code == 200:
                    print(f'SofaScore: rota recuperada via curl_cffi: {url}')
                    return res
            except Exception as e:
                print(f'Erro SofaScore curl_cffi {url}: {e}')

    # Só deixa o 403 explícito no log quando todas as alternativas falharam.
    if ultimo_status is not None and ultimo_status not in (404, 403):
        print(
            f'SofaScore: nenhuma rota respondeu 200 para {path} '
            f'(último status: {ultimo_status})'
        )
    elif ultimo_status == 403:
        print(
            f'SofaScore: 403 em todas as rotas para {path}. '
            f'Verifique bloqueio do IP/rede do Railway.'
        )

    return None

# Registros para evitar repetição do mesmo alerta
notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()

# Dicionário de acompanhamento dos alertas enviados para validação do resultado
alertas_pendentes = {}

# Histórico dos resultados confirmados no dia, usado no relatório diário.
historico_diario = []
ultimo_relatorio_data = None
ultima_data_historico = None
relatorios_por_message_id = {}


def obter_horario_brasil():
    fuso_br = zoneinfo.ZoneInfo('America/Sao_Paulo')
    return datetime.now(fuso_br)


def enviar_alerta(mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown"
    }

    try:
        res = scraper.post(url, json=payload, timeout=10)

        if res.status_code == 200:
            dados = res.json()
            return dados.get('result', {}).get('message_id')

    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")

    return None


def editar_alerta(message_id, nova_mensagem):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"

    payload = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": nova_mensagem,
        "parse_mode": "Markdown"
    }

    try:
        scraper.post(url, json=payload, timeout=10)

    except Exception as e:
        print(f"Erro ao editar mensagem Telegram: {e}")


def obter_estatisticas_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"

    try:
        res = sofascore_get(url.replace('https://api.sofascore.com/api/v1/', ''), timeout=10)

        if res.status_code == 200:
            return res.json().get('statistics', [])

    except Exception:
        pass

    return []


def obter_prelive_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/prematch-form"

    try:
        res = sofascore_get(url.replace('https://api.sofascore.com/api/v1/', ''), timeout=10)

        if res.status_code == 200:
            return res.json()

    except Exception:
        pass

    return None


def analisar_prelive_por_mercado(event_id, home_team_id, away_team_id, mercado, total_gols_atual):
    """Analisa o pré-live de acordo com o mercado do alerta.

    Usa a forma pré-jogo e os últimos jogos das duas equipes como confirmação
    secundária. O resultado serve apenas para ajustar a Confiança; não bloqueia
    nem libera o alerta.
    """
    try:
        form = obter_prelive_sofascore(event_id)

        ids = [home_team_id, away_team_id]
        jogos = []

        for team_id in ids:
            if not team_id:
                continue

            url = f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0"
            res = sofascore_get(url.replace('https://api.sofascore.com/api/v1/', ''), timeout=10)

            if res.status_code != 200:
                continue

            eventos = res.json().get('events', [])
            jogos.extend(eventos[:5])

        if not jogos:
            return {
                'ajuste': 0.0,
                'status': 'SEM DADOS',
                'detalhe': ''
            }

        # Remove duplicados.
        unicos = {}
        for jogo in jogos:
            if jogo.get('id'):
                unicos[jogo['id']] = jogo
        jogos = list(unicos.values())

        primeiros_gols = []
        totais = []

        for jogo in jogos:
            hs = jogo.get('homeScore', {})
            aws = jogo.get('awayScore', {})

            total = hs.get('current')
            if total is None or aws.get('current') is None:
                continue

            total = int(total) + int(aws.get('current', 0))
            totais.append(total)

            h1 = hs.get('period1')
            a1 = aws.get('period1')

            if h1 is not None and a1 is not None:
                primeiros_gols.append(int(h1) + int(a1))

        # Forma pré-live também funciona como desempate secundário.
        form_values = []
        for lado in ('homeTeam', 'awayTeam'):
            dados = (form or {}).get(lado, {})
            forma = dados.get('form', [])
            if isinstance(forma, list):
                form_values.extend(forma)

        positivos_forma = sum(1 for x in form_values if x in ('W', 'D'))
        taxa_forma = (
            positivos_forma / len(form_values)
            if form_values else 0
        )

        ajuste = 0.0
        status = 'NEUTRO'
        detalhe = ''

        if mercado == '05_HT':
            if primeiros_gols:
                taxa = sum(g >= 1 for g in primeiros_gols) / len(primeiros_gols)
                if taxa >= 0.70:
                    ajuste = 0.35
                    status = 'FAVORÁVEL'
                elif taxa < 0.40:
                    ajuste = -0.25
                    status = 'DESFAVORÁVEL'
                else:
                    ajuste = 0.05
                    status = 'NEUTRO'
                detalhe = f'{taxa*100:.0f}% com gol no 1º tempo'

        elif mercado == '15_HT':
            if primeiros_gols:
                taxa = sum(g >= 2 for g in primeiros_gols) / len(primeiros_gols)
                if taxa >= 0.50:
                    ajuste = 0.40
                    status = 'FAVORÁVEL'
                elif taxa < 0.25:
                    ajuste = -0.30
                    status = 'DESFAVORÁVEL'
                else:
                    ajuste = 0.05
                    status = 'NEUTRO'
                detalhe = f'{taxa*100:.0f}% com 2+ gols no 1º tempo'

        elif mercado == 'LIMITE_FT':
            linha = total_gols_atual + 0.5
            if totais:
                taxa = sum(g > total_gols_atual for g in totais) / len(totais)

                if taxa >= 0.60:
                    ajuste = 0.45
                    status = 'FAVORÁVEL'
                elif taxa < 0.30:
                    ajuste = -0.35
                    status = 'DESFAVORÁVEL'
                else:
                    ajuste = 0.05
                    status = 'NEUTRO'

                detalhe = (
                    f'{taxa*100:.0f}% dos últimos jogos superaram '
                    f'{linha:.1f} gols'
                )

        # Forma geral entra apenas como desempate muito pequeno.
        if status == 'NEUTRO' and taxa_forma >= 0.70:
            ajuste += 0.10

        return {
            'ajuste': ajuste,
            'status': status,
            'detalhe': detalhe
        }

    except Exception:
        return {
            'ajuste': 0.0,
            'status': 'SEM DADOS',
            'detalhe': ''
        }


def obter_pressao_grafico_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/graph"

    try:
        res = sofascore_get(url.replace('https://api.sofascore.com/api/v1/', ''), timeout=10)

        if res.status_code == 200:

            points = res.json().get('graphPoints', [])

            if not points:
                return {
                    'pico': 0,
                    'media': 0,
                    'recente': 0,
                    'aceleracao': 0,
                    'direcao': 0,
                    'texto': ''
                }

            # Mantemos a leitura do gráfico do SofaScore.
            # Usamos uma janela curta para detectar pressão atual.
            ultimos_pontos = (
                points[-10:]
                if len(points) >= 10
                else points
            )

            valores = []

            for p in ultimos_pontos:
                try:
                    valores.append(
                        float(p.get('value', 0))
                    )
                except Exception:
                    valores.append(0)

            if not valores:
                return {
                    'pico': 0,
                    'media': 0,
                    'recente': 0,
                    'aceleracao': 0,
                    'direcao': 0,
                    'texto': ''
                }

            metade = max(
                1,
                len(valores) // 2
            )

            primeira_metade = valores[:metade]
            segunda_metade = valores[metade:]

            media_abs = (
                sum(abs(x) for x in valores)
                / len(valores)
            )

            recente_abs = (
                sum(abs(x) for x in segunda_metade)
                / len(segunda_metade)
                if segunda_metade
                else media_abs
            )

            media_anterior = (
                sum(abs(x) for x in primeira_metade)
                / len(primeira_metade)
                if primeira_metade
                else 0
            )

            pico_pressao = max(
                abs(x) for x in valores
            )

            aceleracao = (
                recente_abs - media_anterior
            )

            # Valor positivo = pressão Casa
            # Valor negativo = pressão Fora
            direcao = (
                sum(segunda_metade)
                / len(segunda_metade)
                if segunda_metade
                else 0
            )

            texto_fluxo = (
                f"🔥 *Pressão no Gráfico:* "
                f"Pico `{pico_pressao:.0f}` | "
                f"Média `{media_abs:.1f}` | "
                f"Recente `{recente_abs:.1f}`\n"
            )

            return {
                'pico': pico_pressao,
                'media': media_abs,
                'recente': recente_abs,
                'aceleracao': aceleracao,
                'direcao': direcao,
                'texto': texto_fluxo
            }

    except Exception:
        pass

    return {
        'pico': 0,
        'media': 0,
        'recente': 0,
        'aceleracao': 0,
        'direcao': 0,
        'texto': ''
    }


def extrair_stat_sofascore(stats_data, item_name):
    if not stats_data:
        return 0, 0, 0

    for period in stats_data:

        if period.get('period') == 'ALL':

            for group in period.get('groups', []):

                for item in group.get('statisticsItems', []):

                    if item.get('name') == item_name:

                        home_raw = str(
                            item.get('home', '0')
                        ).replace('%', '')

                        away_raw = str(
                            item.get('away', '0')
                        ).replace('%', '')

                        try:
                            val_home = float(home_raw)
                            val_away = float(away_raw)

                            return (
                                val_home + val_away,
                                val_home,
                                val_away
                            )

                        except ValueError:
                            return 0, 0, 0

    return 0, 0, 0


def extrair_xg_sofascore(stats_data):

    xg_total, xg_home, xg_away = (
        extrair_stat_sofascore(
            stats_data,
            'Expected goals'
        )
    )

    if xg_total > 0:
        return xg_total, xg_home, xg_away

    xg_total_alt, xg_h_alt, xg_a_alt = (
        extrair_stat_sofascore(
            stats_data,
            'Expected goals (xG)'
        )
    )

    return xg_total_alt, xg_h_alt, xg_a_alt


def eh_partida_valida(nome_liga, time_casa, time_fora):

    texto_completo = (
        f" {nome_liga} {time_casa} {time_fora} "
    ).lower()

    for termo in TERMOS_IGNORADOS:

        if termo in texto_completo:
            return False

    return True


def extrair_minutagem_e_numero(item, eh_1h, eh_2h):

    status_desc = str(
        item.get('status', {}).get('description', '')
    ).lower().strip()

    status_type = str(
        item.get('status', {}).get('type', '')
    ).lower().strip()

    # BLOQUEIO RIGIDO DE PRORROGAÇÃO E PÊNALTIS
    termos_prorrogacao = [
        'extra',
        'et',
        'extratime',
        'overtime',
        'penalties',
        'pen',
        'prorrogação'
    ]

    for termo in termos_prorrogacao:

        if termo in status_desc or termo in status_type:
            return None, None

    minuto = None

    if "'" in status_desc:

        min_limpo = (
            status_desc
            .replace("'", "")
            .split('+')[0]
            .strip()
        )

        if min_limpo.isdigit():
            minuto = int(min_limpo)

    if not minuto:

        time_data = item.get('time', {})

        if (
            isinstance(time_data, dict)
            and time_data.get(
                'currentPeriodStartTimestamp'
            )
        ):

            now_ts = int(time.time())

            start_ts = time_data.get(
                'currentPeriodStartTimestamp'
            )

            m_calc = (
                now_ts - start_ts
            ) // 60

            if eh_2h:
                m_calc += 45

            if 1 <= m_calc <= 90:
                minuto = m_calc

    if minuto:

        if eh_1h and minuto <= 45:
            return (
                f"{minuto}' do 1º tempo",
                minuto
            )

        elif eh_2h and 45 <= minuto <= 90:
            return (
                f"{minuto}' do 2º tempo",
                minuto
            )

    return None, None


# ==============================================================================
# FILTROS AVANÇADOS
# ==============================================================================

def calcular_intensidade(
    xg,
    finalizacoes,
    chutes_gol,
    escanteios,
    grandes_chances
):
    """
    Mede o volume ofensivo geral.
    Não decide sozinho a entrada.
    """

    pontos = 0

    if xg >= 0.90:
        pontos += 3
    elif xg >= 0.70:
        pontos += 2
    elif xg >= 0.45:
        pontos += 1

    if finalizacoes >= 10:
        pontos += 2
    elif finalizacoes >= 7:
        pontos += 1

    if chutes_gol >= 4:
        pontos += 3
    elif chutes_gol >= 3:
        pontos += 2
    elif chutes_gol >= 2:
        pontos += 1

    if escanteios >= 6:
        pontos += 2
    elif escanteios >= 4:
        pontos += 1

    if grandes_chances >= 2:
        pontos += 2
    elif grandes_chances >= 1:
        pontos += 1

    return pontos


def calcular_equilibrio(
    fin_h,
    fin_a
):
    """
    Mede se existe produção ofensiva dos dois lados.
    """

    total = fin_h + fin_a

    if total <= 0:
        return 0

    maior = max(fin_h, fin_a)
    menor = min(fin_h, fin_a)

    if maior <= 0:
        return 0

    proporcao = menor / maior

    if proporcao >= 0.50:
        return 2

    if proporcao >= 0.30:
        return 1

    return 0


\
def obter_incidentes_sofascore(event_id):
    """Busca incidentes para detectar expulsões/cartões vermelhos."""
    try:
        res = sofascore_get(f'event/{event_id}/incidents', timeout=10)
        if res is not None and res.status_code == 200:
            return res.json().get('incidents', [])
    except Exception:
        pass
    return []

def extrair_cartoes_vermelhos(incidentes, home_id, away_id):
    """Conta expulsões efetivas por equipe."""
    vermelhos_casa = 0
    vermelhos_fora = 0
    for incidente in incidentes or []:
        if incidente.get('incidentType') != 'card':
            continue
        classif = str(incidente.get('incidentClass', '')).lower()
        is_red = classif in ('red', 'secondyellow', 'second_yellow')
        if incidente.get('isRed') is True:
            is_red = True
        if 'red' in classif and 'yellow' not in classif:
            is_red = True
        if not is_red:
            continue
        is_home = incidente.get('isHome')
        team = incidente.get('team') or {}
        team_id = team.get('id') if isinstance(team, dict) else None
        if is_home is True or (team_id and str(team_id) == str(home_id)):
            vermelhos_casa += 1
        elif is_home is False or (team_id and str(team_id) == str(away_id)):
            vermelhos_fora += 1
    return vermelhos_casa, vermelhos_fora

def obter_odds_favorito_sofascore(event_id):
    """Obtém o favorito pré-live pelo mercado principal 1X2."""
    try:
        res = sofascore_get(f'event/{event_id}/odds/1/all', timeout=10)
        if res is None or res.status_code != 200:
            res = sofascore_get(f'event/{event_id}/odds/1/featured', timeout=10)
        if res is None or res.status_code != 200:
            return None
        data = res.json()
        markets = data.get('markets', []) if isinstance(data, dict) else []
        if not markets:
            return None
        mercado = None
        for m in markets:
            nome = str(m.get('name', '')).lower()
            if m.get('isMain') or nome in ('1x2', 'match winner', 'full time result'):
                mercado = m
                break
        mercado = mercado or markets[0]
        odds = {}
        for escolha in mercado.get('choices', []) or []:
            nome = str(escolha.get('name', '')).strip().lower()
            try:
                valor = float(escolha.get('decimalValue'))
            except (TypeError, ValueError):
                continue
            if valor > 1.0:
                odds[nome] = valor
        if '1' not in odds or '2' not in odds:
            return None
        if odds['1'] < odds['2']:
            favorito, odd_fav, odd_outro = 'home', odds['1'], odds['2']
        elif odds['2'] < odds['1']:
            favorito, odd_fav, odd_outro = 'away', odds['2'], odds['1']
        else:
            favorito, odd_fav, odd_outro = None, None, None
        vantagem = ((odd_outro - odd_fav) / odd_outro) if odd_fav and odd_outro else 0.0
        return {
            'favorito': favorito if vantagem >= 0.04 else None,
            'odd_favorito': odd_fav,
            'odd_outro': odd_outro,
            'vantagem': vantagem,
            'status': 'FORTE' if vantagem >= 0.12 else ('LEVE' if vantagem >= 0.04 else 'EQUILIBRADO')
        }
    except Exception:
        return None

def obter_classificacao_sofascore(item):
    """Consulta classificação/objetivo competitivo, com proteção no início da temporada."""
    try:
        tournament = item.get('tournament', {}) or {}
        unique = tournament.get('uniqueTournament', {}) or {}
        tournament_id = unique.get('id') or tournament.get('id')
        season_id = (item.get('season', {}) or {}).get('id')
        if not tournament_id or not season_id:
            return None
        chave = f'{tournament_id}:{season_id}'
        agora_ts = time.time()
        cached = contexto_competitivo_cache.get(f'standings:{chave}')
        if cached and agora_ts - cached.get('ts', 0) < 900:
            return cached.get('data')
        res = sofascore_get(
            f'unique-tournament/{tournament_id}/season/{season_id}/standings/total',
            timeout=10
        )
        if res is None or res.status_code != 200:
            return None
        standings = res.json().get('standings', [])
        rows = []
        for tabela in standings:
            rows.extend(tabela.get('rows', []) or [])
        home_id = item.get('homeTeam', {}).get('id')
        away_id = item.get('awayTeam', {}).get('id')
        home_row = next((r for r in rows if r.get('team', {}).get('id') == home_id), None)
        away_row = next((r for r in rows if r.get('team', {}).get('id') == away_id), None)
        if not home_row or not away_row:
            data = {'available': False}
        else:
            partidas = min(int(home_row.get('matches', 0) or 0), int(away_row.get('matches', 0) or 0))
            n = len(rows)
            promo_positions = []
            releg_positions = []
            for row in rows:
                promo = row.get('promotion', {})
                promo_text = str(promo.get('text', '') if isinstance(promo, dict) else '').lower()
                descs = ' '.join(str(d.get('text', '') if isinstance(d, dict) else d) for d in (row.get('descriptions', []) or [])).lower()
                if any(k in promo_text for k in ('champions', 'libertadores', 'promotion', 'promov')):
                    if row.get('position') is not None:
                        promo_positions.append(row.get('position'))
                if any(k in (promo_text + ' ' + descs) for k in ('releg', 'rebaix', 'playoff')):
                    if row.get('position') is not None:
                        releg_positions.append(row.get('position'))
            limite_top = max(promo_positions) if promo_positions else min(4, n) if n else 4
            limite_releg = min(releg_positions) if releg_positions else max(1, n - 2)

            def resumir(row):
                return {
                    'position': row.get('position'),
                    'matches': row.get('matches', 0),
                    'points': row.get('points', 0),
                    'promotion': row.get('promotion', {}).get('text', '') if isinstance(row.get('promotion'), dict) else ''
                }

            home = resumir(home_row)
            away = resumir(away_row)

            def pressao_equipe(dados):
                if partidas < 4:
                    return 0.0, 'classificação ainda muito inicial'
                pos = dados.get('position') or n
                press = 0.0
                motivo = ''
                if pos <= limite_top:
                    press += 0.4
                    motivo = 'na zona de objetivo alto'
                elif pos <= limite_top + 2:
                    press += 0.8
                    motivo = 'próxima da zona de objetivo alto'
                if pos >= limite_releg:
                    press += 0.9
                    motivo = 'na zona de risco na tabela'
                elif pos == limite_releg - 1:
                    press += 0.7
                    motivo = 'próxima da zona de risco'
                return press, motivo

            hp, hm = pressao_equipe(home)
            ap, am = pressao_equipe(away)
            data = {
                'available': True,
                'matches_considered': partidas,
                'home': home,
                'away': away,
                'home_pressure': hp,
                'away_pressure': ap,
                'home_reason': hm,
                'away_reason': am,
                'table_size': n
            }
        contexto_competitivo_cache[f'standings:{chave}'] = {'ts': agora_ts, 'data': data}
        return data
    except Exception:
        return None

def obter_contexto_competitivo(event_id, item):
    """Combina favorito pré-live, classificação/objetivo e expulsões atuais."""
    try:
        chave_evento = str(event_id)
        agora_ts = time.time()
        cached = contexto_competitivo_cache.get(f'event:{chave_evento}')
        if cached and agora_ts - cached.get('ts', 0) < 900:
            contexto = dict(cached.get('data', {}))
        else:
            contexto = {
                'favorito': obter_odds_favorito_sofascore(event_id),
                'classificacao': obter_classificacao_sofascore(item),
            }
            contexto_competitivo_cache[f'event:{chave_evento}'] = {'ts': agora_ts, 'data': contexto}
        incidentes = obter_incidentes_sofascore(event_id)
        contexto['vermelhos_casa'], contexto['vermelhos_fora'] = extrair_cartoes_vermelhos(
            incidentes,
            item.get('homeTeam', {}).get('id'),
            item.get('awayTeam', {}).get('id')
        )
        return contexto
    except Exception:
        return {'favorito': None, 'classificacao': None, 'vermelhos_casa': 0, 'vermelhos_fora': 0}

def avaliar_propensao_gol(
    mercado, gols_c, gols_f, xg_tot, fin_h, fin_a, chutes_h, chutes_a,
    gc_h, gc_a, pressao, intensidade, contexto_competitivo=None
):
    """Pergunta se o jogo continua realmente propenso a outro gol."""
    contexto_competitivo = contexto_competitivo or {}
    favorito_info = contexto_competitivo.get('favorito') or {}
    classificacao = contexto_competitivo.get('classificacao') or {}
    vermelhos_casa = int(contexto_competitivo.get('vermelhos_casa', 0) or 0)
    vermelhos_fora = int(contexto_competitivo.get('vermelhos_fora', 0) or 0)
    pontos = 0.0
    motivos = []
    total_fin = fin_h + fin_a
    total_chutes = chutes_h + chutes_a
    total_gc = gc_h + gc_a
    diferenca = abs(gols_c - gols_f)
    recente = pressao.get('recente', 0)
    aceleracao = pressao.get('aceleracao', 0)

    if aceleracao <= -6:
        pontos -= 1
        motivos.append('intensidade recente em queda')

    # Expulsões: superioridade numérica só ajuda quando o time com vantagem
    # está em condição de pressionar; se o time que já perdia ficou com um a menos,
    # o contexto é penalizado.
    if vermelhos_casa or vermelhos_fora:
        if gols_c < gols_f:
            equipe_atras = 'home'
        elif gols_f < gols_c:
            equipe_atras = 'away'
        else:
            equipe_atras = None
        if vermelhos_casa and vermelhos_fora:
            pontos += 0.5
            motivos.append('há expulsão dos dois lados')
        elif vermelhos_casa:
            if equipe_atras == 'home':
                pontos -= 1.5
                motivos.append('equipe atrás ficou com um a menos')
            else:
                pontos += 1.5
                motivos.append('equipe atrás enfrenta um adversário com um a menos')
        elif vermelhos_fora:
            if equipe_atras == 'away':
                pontos -= 1.5
                motivos.append('equipe atrás ficou com um a menos')
            else:
                pontos += 1.5
                motivos.append('equipe atrás enfrenta um adversário com um a menos')

    if mercado in ('05_HT', '15_HT'):
        if recente >= 30:
            pontos += 1
            motivos.append('pressão recente suficiente')
        elif recente < 20 and aceleracao < 0:
            pontos -= 1
        if xg_tot >= 0.70 or total_gc >= 2 or total_chutes >= 3:
            pontos += 1
        if total_fin >= 8 or total_chutes >= 4:
            pontos += 1
        return {
            'aprovado': pontos >= 1,
            'pontos': pontos,
            'nivel': 'ALTA' if pontos >= 2 else ('MÉDIA' if pontos >= 1 else 'BAIXA'),
            'motivos': motivos,
            'contexto': contexto_competitivo
        }

    if diferenca == 0:
        if recente >= 30 or aceleracao >= 6:
            pontos += 2
            motivos.append('jogo empatado com pressão atual')
        elif recente >= 20:
            pontos += 1
        if xg_tot >= 1.50:
            pontos += 1
        if total_chutes >= 5 or total_gc >= 2:
            pontos += 1
    elif diferenca == 1:
        if gols_c < gols_f:
            fin_trailing, shots_trailing, gc_trailing, lado_trailing = fin_h, chutes_h, gc_h, 'home'
        else:
            fin_trailing, shots_trailing, gc_trailing, lado_trailing = fin_a, chutes_a, gc_a, 'away'
        share_fin = fin_trailing / total_fin if total_fin else 0
        share_shots = shots_trailing / total_chutes if total_chutes else 0
        share_gc = gc_trailing / total_gc if total_gc else 0
        produzindo = share_fin >= 0.40 or share_shots >= 0.40 or share_gc >= 0.50
        if produzindo:
            pontos += 2
            motivos.append('equipe atrás do placar está produzindo')
        elif share_fin < 0.30 and share_shots < 0.30 and gc_trailing == 0:
            pontos -= 2
            motivos.append('equipe atrás do placar produz pouco')
        if aceleracao <= -6 and share_shots < 0.40:
            pontos -= 1
            motivos.append('pressão não sustenta reação')
        if recente >= 30:
            pontos += 1
        elif recente < 20 and aceleracao < 0:
            pontos -= 1

        favorito = favorito_info.get('favorito') if isinstance(favorito_info, dict) else None
        if favorito == lado_trailing:
            if produzindo:
                pontos += 2
                motivos.append('favorito atrás está crescendo no jogo')
            else:
                pontos += 0.5
                motivos.append('favorito está atrás do placar')

        if classificacao.get('available'):
            if lado_trailing == 'home':
                press_comp = float(classificacao.get('home_pressure', 0) or 0)
                motivo_comp = classificacao.get('home_reason', '')
            else:
                press_comp = float(classificacao.get('away_pressure', 0) or 0)
                motivo_comp = classificacao.get('away_reason', '')
            if press_comp >= 0.7:
                pontos += 1.5
                motivos.append(f'equipe atrás tem objetivo competitivo: {motivo_comp}' if motivo_comp else 'equipe atrás tem maior necessidade competitiva')
            elif press_comp >= 0.4:
                pontos += 0.5
                motivos.append('há pressão competitiva pela tabela')
    else:
        pontos -= 2
        motivos.append('vantagem de dois ou mais gols')

    # Empate: favorito/necessitado criando e crescendo recebe reforço.
    if diferenca == 0 and classificacao.get('available'):
        hp = float(classificacao.get('home_pressure', 0) or 0)
        ap = float(classificacao.get('away_pressure', 0) or 0)
        if max(hp, ap) >= 0.7 and (recente >= 25 or aceleracao >= 4):
            pontos += 1
            motivos.append('há pressão competitiva e jogo ainda vivo')

    if diferenca == 0 and isinstance(favorito_info, dict):
        favorito = favorito_info.get('favorito')
        if favorito and recente >= 25 and aceleracao >= 0:
            if favorito == 'home' and (fin_h > fin_a or chutes_h > chutes_a or gc_h > gc_a):
                pontos += 1
                motivos.append('favorito empatado está crescendo')
            elif favorito == 'away' and (fin_a > fin_h or chutes_a > chutes_h or gc_a > gc_h):
                pontos += 1
                motivos.append('favorito empatado está crescendo')

    if mercado == 'LIMITE_FT':
        if recente >= 35:
            pontos += 1
        if aceleracao >= 6:
            pontos += 1

    if mercado == 'LIMITE_FT' and (gols_c + gols_f) == 1:
        aprovado = pontos >= 2
    elif mercado == 'LIMITE_FT':
        aprovado = pontos >= 1
    else:
        aprovado = pontos >= 1

    return {
        'aprovado': aprovado,
        'pontos': pontos,
        'nivel': 'ALTA' if pontos >= 3 else ('MÉDIA' if pontos >= 1 else 'BAIXA'),
        'motivos': motivos,
        'contexto': contexto_competitivo
    }


def calcular_score_05_ht(
    xg_tot,
    fin_tot,
    chutes_gol,
    escanteios,
    grandes_chances,
    fin_h,
    fin_a,
    pressao
):
    """
    Goal Score específico para Over 0.5 HT.

    Máximo aproximado: 20 pontos.
    """

    score = 0
    motivos = []

    # ------------------------------------------------------------------
    # xG
    # ------------------------------------------------------------------

    if xg_tot >= 0.65:
        score += 3
        motivos.append("xG forte")

    elif xg_tot >= 0.50:
        score += 2
        motivos.append("xG bom")

    elif xg_tot >= 0.45:
        score += 1

    # ------------------------------------------------------------------
    # Finalizações
    # ------------------------------------------------------------------

    if fin_tot >= 10:
        score += 3
        motivos.append("volume alto")

    elif fin_tot >= 7:
        score += 2
        motivos.append("bom volume")

    elif fin_tot >= 5:
        score += 1

    # ------------------------------------------------------------------
    # Chutes no alvo
    # ------------------------------------------------------------------

    if chutes_gol >= 4:
        score += 3
        motivos.append("4+ no alvo")

    elif chutes_gol >= 3:
        score += 2
        motivos.append("3 no alvo")

    elif chutes_gol >= 2:
        score += 1

    # ------------------------------------------------------------------
    # Escanteios
    # ------------------------------------------------------------------

    if escanteios >= 5:
        score += 2
        motivos.append("muitos escanteios")

    elif escanteios >= 3:
        score += 1

    # ------------------------------------------------------------------
    # Grandes chances
    # ------------------------------------------------------------------

    if grandes_chances >= 2:
        score += 3
        motivos.append("grandes chances")

    elif grandes_chances >= 1:
        score += 2
        motivos.append("chance clara")

    # ------------------------------------------------------------------
    # Pressão
    # ------------------------------------------------------------------

    if pressao['recente'] >= 45:
        score += 3
        motivos.append("pressão forte")

    elif pressao['recente'] >= 30:
        score += 2
        motivos.append("pressão boa")

    elif pressao['recente'] >= 20:
        score += 1

    # ------------------------------------------------------------------
    # Aceleração
    # ------------------------------------------------------------------

    if pressao['aceleracao'] >= 12:
        score += 2
        motivos.append("pressão acelerando")

    elif pressao['aceleracao'] >= 6:
        score += 1

    # ------------------------------------------------------------------
    # Equilíbrio
    # ------------------------------------------------------------------

    equilibrio = calcular_equilibrio(
        fin_h,
        fin_a
    )

    score += equilibrio

    if equilibrio >= 2:
        motivos.append("jogo equilibrado")

    # ------------------------------------------------------------------
    # Regras mínimas
    # ------------------------------------------------------------------

    base_ofensiva = (
        xg_tot >= 0.45
        or chutes_gol >= 2
        or fin_tot >= 7
        or grandes_chances >= 1
    )

    pressao_valida = (
        pressao['pico'] >= 30
        or pressao['recente'] >= 25
        or chutes_gol >= 3
        or grandes_chances >= 1
    )

    aprovado = (
        score >= 10
        and base_ofensiva
        and pressao_valida
    )

    return aprovado, score, motivos


def calcular_score_15_ht(
    xg_tot,
    fin_tot,
    chutes_gol,
    escanteios,
    grandes_chances,
    fin_h,
    fin_a,
    pressao
):
    """
    Goal Score específico para Over 1.5 HT.

    Como já existe um gol, o filtro exige maior intensidade.
    """

    score = 0
    motivos = []

    # ------------------------------------------------------------------
    # xG
    # ------------------------------------------------------------------

    if xg_tot >= 1.00:
        score += 4
        motivos.append("xG muito forte")

    elif xg_tot >= 0.85:
        score += 3
        motivos.append("xG forte")

    elif xg_tot >= 0.70:
        score += 2
        motivos.append("xG bom")

    # ------------------------------------------------------------------
    # Finalizações
    # ------------------------------------------------------------------

    if fin_tot >= 11:
        score += 3
        motivos.append("volume muito alto")

    elif fin_tot >= 8:
        score += 2
        motivos.append("bom volume")

    elif fin_tot >= 6:
        score += 1

    # ------------------------------------------------------------------
    # Chutes no alvo
    # ------------------------------------------------------------------

    if chutes_gol >= 4:
        score += 3
        motivos.append("4+ no alvo")

    elif chutes_gol >= 3:
        score += 2
        motivos.append("3 no alvo")

    elif chutes_gol >= 2:
        score += 1

    # ------------------------------------------------------------------
    # Escanteios
    # ------------------------------------------------------------------

    if escanteios >= 5:
        score += 2
        motivos.append("muitos escanteios")

    elif escanteios >= 3:
        score += 1

    # ------------------------------------------------------------------
    # Grandes chances
    # ------------------------------------------------------------------

    if grandes_chances >= 2:
        score += 3
        motivos.append("grandes chances")

    elif grandes_chances >= 1:
        score += 2
        motivos.append("chance clara")

    # ------------------------------------------------------------------
    # Pressão
    # ------------------------------------------------------------------

    if pressao['recente'] >= 45:
        score += 3
        motivos.append("pressão forte")

    elif pressao['recente'] >= 30:
        score += 2
        motivos.append("pressão boa")

    # ------------------------------------------------------------------
    # Aceleração
    # ------------------------------------------------------------------

    if pressao['aceleracao'] >= 10:
        score += 2
        motivos.append("pressão acelerando")

    elif pressao['aceleracao'] >= 5:
        score += 1

    # ------------------------------------------------------------------
    # Equilíbrio
    # ------------------------------------------------------------------

    equilibrio = calcular_equilibrio(
        fin_h,
        fin_a
    )

    score += equilibrio

    if equilibrio >= 2:
        motivos.append("jogo equilibrado")

    # ------------------------------------------------------------------
    # Regras mínimas
    # ------------------------------------------------------------------

    base_ofensiva = (
        xg_tot >= 0.70
        or chutes_gol >= 3
        or grandes_chances >= 1
        or (
            fin_tot >= 8
            and escanteios >= 3
        )
    )

    pressao_valida = (
        pressao['pico'] >= 30
        or pressao['recente'] >= 25
        or chutes_gol >= 3
        or grandes_chances >= 1
    )

    aprovado = (
        score >= 12
        and base_ofensiva
        and pressao_valida
    )

    return aprovado, score, motivos


def calcular_score_limite_ft(
    xg_tot,
    fin_tot,
    chutes_gol,
    escanteios,
    grandes_chances,
    fin_h,
    fin_a,
    pressao
):
    """
    Goal Score específico para o mercado de gol limite FT.
    """

    score = 0
    motivos = []

    # ------------------------------------------------------------------
    # xG
    # ------------------------------------------------------------------

    if xg_tot >= 1.70:
        score += 4
        motivos.append("xG muito forte")

    elif xg_tot >= 1.40:
        score += 3
        motivos.append("xG forte")

    elif xg_tot >= 1.20:
        score += 2
        motivos.append("xG bom")

    # ------------------------------------------------------------------
    # Finalizações
    # ------------------------------------------------------------------

    if fin_tot >= 18:
        score += 3
        motivos.append("volume muito alto")

    elif fin_tot >= 14:
        score += 2
        motivos.append("volume alto")

    elif fin_tot >= 10:
        score += 1

    # ------------------------------------------------------------------
    # Chutes no alvo
    # ------------------------------------------------------------------

    if chutes_gol >= 7:
        score += 3
        motivos.append("7+ no alvo")

    elif chutes_gol >= 5:
        score += 2
        motivos.append("5+ no alvo")

    elif chutes_gol >= 3:
        score += 1

    # ------------------------------------------------------------------
    # Escanteios
    # ------------------------------------------------------------------

    if escanteios >= 8:
        score += 2
        motivos.append("muitos escanteios")

    elif escanteios >= 5:
        score += 1

    # ------------------------------------------------------------------
    # Grandes chances
    # ------------------------------------------------------------------

    if grandes_chances >= 3:
        score += 3
        motivos.append("muitas grandes chances")

    elif grandes_chances >= 2:
        score += 2
        motivos.append("grandes chances")

    elif grandes_chances >= 1:
        score += 1

    # ------------------------------------------------------------------
    # Pressão
    # ------------------------------------------------------------------

    if pressao['recente'] >= 50:
        score += 3
        motivos.append("pressão muito forte")

    elif pressao['recente'] >= 35:
        score += 2
        motivos.append("pressão forte")

    elif pressao['recente'] >= 25:
        score += 1

    # ------------------------------------------------------------------
    # Aceleração
    # ------------------------------------------------------------------

    if pressao['aceleracao'] >= 12:
        score += 2
        motivos.append("pressão acelerando")

    elif pressao['aceleracao'] >= 6:
        score += 1

    # ------------------------------------------------------------------
    # Equilíbrio
    # ------------------------------------------------------------------

    equilibrio = calcular_equilibrio(
        fin_h,
        fin_a
    )

    score += equilibrio

    if equilibrio >= 2:
        motivos.append("produção dos dois lados")

    # ------------------------------------------------------------------
    # Regras mínimas
    # ------------------------------------------------------------------

    base_ofensiva = (
        xg_tot >= 1.20
        or chutes_gol >= 4
        or grandes_chances >= 2
        or (
            fin_tot >= 12
            and escanteios >= 5
        )
    )

    pressao_valida = (
        pressao['pico'] >= 30
        or pressao['recente'] >= 30
        or chutes_gol >= 4
        or grandes_chances >= 2
    )

    aprovado = (
        score >= 12
        and base_ofensiva
        and pressao_valida
    )

    return aprovado, score, motivos



def normalizar_score_100(score, mercado):
    """Converte o score interno do filtro para uma escala de 0 a 100."""
    maximos = {
        '05_HT': 21,
        '15_HT': 22,
        'LIMITE_FT': 22,
    }
    maximo = maximos.get(mercado, 22)
    return max(0, min(100, round((score / maximo) * 100)))


def classificar_intensidade(pressao, fin_tot, chutes_gol, grandes_chances):
    """Classifica a intensidade atual do jogo."""
    aceleracao = pressao.get('aceleracao', 0)
    recente = pressao.get('recente', 0)

    if aceleracao >= 6:
        return 'CRESCENTE'
    if aceleracao <= -6:
        return 'CAINDO'
    if recente >= 35 or fin_tot >= 10 or chutes_gol >= 4 or grandes_chances >= 2:
        return 'ALTA'
    return 'ESTÁVEL'


def classificar_pressao(pressao):
    """Classifica a pressão recente do gráfico do SofaScore."""
    recente = pressao.get('recente', 0)
    pico = pressao.get('pico', 0)

    if recente >= 45 or pico >= 60:
        return 'ALTA'
    if recente >= 25 or pico >= 40:
        return 'MÉDIA'
    return 'BAIXA'


def classificar_qualidade(xg_tot, chutes_gol, grandes_chances):
    """Classifica a qualidade das oportunidades criadas."""
    if xg_tot >= 1.00 or grandes_chances >= 2 or chutes_gol >= 5:
        return 'ALTA'
    if xg_tot >= 0.60 or grandes_chances >= 1 or chutes_gol >= 3:
        return 'MÉDIA'
    return 'BAIXA'


def calcular_confianca_independente(
    mercado,
    xg_tot,
    fin_tot,
    chutes_gol,
    grandes_chances,
    pressao,
    intensidade,
    qualidade,
    prelive_info=None,
):
    """Calcula a Confiança de forma independente do GOAL SCORE.

    A confiança usa somente os sinais qualitativos/estatísticos do jogo,
    com pesos próprios, e não reutiliza o score interno do filtro.
    """
    pontos = 4.0

    # xG
    if xg_tot >= 1.20:
        pontos += 1.5
    elif xg_tot >= 0.90:
        pontos += 1.2
    elif xg_tot >= 0.60:
        pontos += 0.8
    elif xg_tot >= 0.40:
        pontos += 0.4

    # Chutes no alvo
    if chutes_gol >= 6:
        pontos += 1.2
    elif chutes_gol >= 4:
        pontos += 0.9
    elif chutes_gol >= 3:
        pontos += 0.6
    elif chutes_gol >= 2:
        pontos += 0.3

    # Grandes chances
    if grandes_chances >= 3:
        pontos += 1.0
    elif grandes_chances >= 2:
        pontos += 0.8
    elif grandes_chances >= 1:
        pontos += 0.4

    # Volume geral
    if fin_tot >= 14:
        pontos += 0.7
    elif fin_tot >= 10:
        pontos += 0.5
    elif fin_tot >= 7:
        pontos += 0.3

    # Pressão
    recente = pressao.get('recente', 0)
    pico = pressao.get('pico', 0)
    aceleracao = pressao.get('aceleracao', 0)

    if recente >= 45 or pico >= 60:
        pontos += 0.8
    elif recente >= 30 or pico >= 45:
        pontos += 0.5
    elif recente >= 20 or pico >= 30:
        pontos += 0.3

    if aceleracao >= 8:
        pontos += 0.4
    elif aceleracao >= 4:
        pontos += 0.2

    # Qualidade e intensidade entram como fatores independentes.
    if qualidade == 'ALTA':
        pontos += 0.4
    elif qualidade == 'MÉDIA':
        pontos += 0.2

    if intensidade == 'CRESCENTE':
        pontos += 0.4
    elif intensidade == 'ALTA':
        pontos += 0.2

    # Ajustes pequenos por mercado, sem usar o GOAL SCORE.
    if mercado == '05_HT':
        pontos += 0.1
    elif mercado == '15_HT':
        pontos += 0.0
    elif mercado == 'LIMITE_FT':
        pontos -= 0.1

    if prelive_info:
        pontos += float(prelive_info.get('ajuste', 0.0))

    return max(0.0, min(10.0, round(pontos, 1)))


def montar_motivos_exibicao(
    xg_tot,
    fin_tot,
    chutes_gol,
    escanteios,
    grandes_chances,
    fin_h,
    fin_a,
    intensidade,
    pressao_nivel,
    qualidade,
):
    """Monta motivos curtos e objetivos para a mensagem do Telegram."""
    motivos = []

    if xg_tot >= 0.80:
        motivos.append('xG elevado para o minuto')
    elif xg_tot >= 0.50:
        motivos.append('xG interessante para o minuto')

    if chutes_gol >= 5:
        motivos.append(f'{chutes_gol} chutes no alvo')
    elif chutes_gol >= 3:
        motivos.append(f'{chutes_gol} chutes no alvo')

    if grandes_chances >= 2:
        motivos.append(f'{grandes_chances} grandes chances')
    elif grandes_chances == 1:
        motivos.append('1 grande chance')

    if intensidade == 'CRESCENTE':
        motivos.append('pressão crescente')
    elif intensidade == 'ALTA':
        motivos.append('intensidade ofensiva alta')

    if pressao_nivel == 'ALTA':
        motivos.append('pressão alta')

    if qualidade == 'ALTA':
        motivos.append('qualidade das chances alta')

    if fin_tot >= 10:
        motivos.append('volume ofensivo elevado')
    elif fin_tot >= 7:
        motivos.append('bom volume ofensivo')

    if escanteios >= 5:
        motivos.append(f'{escanteios} escanteios')

    maior = max(fin_h, fin_a)
    menor = min(fin_h, fin_a)
    if maior > 0 and menor / maior >= 0.50:
        motivos.append('volume ofensivo dos dois lados')

    # Limita a mensagem para não ficar excessivamente longa.
    return motivos[:5] if motivos else ['sinais ofensivos suficientes para o filtro']


def montar_layout_alerta(
    mercado,
    liga,
    time_casa,
    time_fora,
    gols_c,
    gols_f,
    minutagem,
    score,
    xg_tot,
    xg_h,
    xg_a,
    fin_tot,
    fin_h,
    fin_a,
    chutes_gol,
    cg_h,
    cg_a,
    grandes_chances,
    gc_h,
    gc_a,
    escanteios,
    esc_h,
    esc_a,
    pressao,
    prelive_info=None,
    contexto_competitivo=None
):
    """Gera o layout padrão Faro de Beagle."""
    score_100 = normalizar_score_100(score, mercado)
    intensidade = classificar_intensidade(
        pressao, fin_tot, chutes_gol, grandes_chances
    )
    pressao_nivel = classificar_pressao(pressao)
    qualidade = classificar_qualidade(
        xg_tot, chutes_gol, grandes_chances
    )
    confianca = calcular_confianca_independente(
        mercado,
        xg_tot,
        fin_tot,
        chutes_gol,
        grandes_chances,
        pressao,
        intensidade,
        qualidade,
        prelive_info,
    )

    motivos = montar_motivos_exibicao(
        xg_tot,
        fin_tot,
        chutes_gol,
        escanteios,
        grandes_chances,
        fin_h,
        fin_a,
        intensidade,
        pressao_nivel,
        qualidade,
    )

    nomes_mercado = {
        '05_HT': ('🔥 SINAL +0,5 HT', 'OVER 0,5 HT'),
        '15_HT': ('🔥 SINAL +1,5 HT', 'OVER 1,5 HT'),
        'LIMITE_FT': (f'🎯 SINAL LIMITE FT (+{gols_c + gols_f + 0.5})',
                      f'OVER LIMITE (+{gols_c + gols_f + 0.5})'),
    }
    titulo, faro = nomes_mercado.get(
        mercado, ('🔥 SINAL', 'OVER')
    )

    linhas_motivos = ''.join(
        f'• {motivo}\n' for motivo in motivos
    )

    contexto_competitivo = contexto_competitivo or {}
    contexto_linhas = []
    favorito_info = contexto_competitivo.get('favorito') or {}
    classificacao = contexto_competitivo.get('classificacao') or {}
    vermelhos_casa = int(contexto_competitivo.get('vermelhos_casa', 0) or 0)
    vermelhos_fora = int(contexto_competitivo.get('vermelhos_fora', 0) or 0)
    if isinstance(favorito_info, dict) and favorito_info.get('favorito'):
        lado = 'Casa' if favorito_info.get('favorito') == 'home' else 'Fora'
        contexto_linhas.append(f'⭐ Favorito pré-live: {lado} ({favorito_info.get("status", "")})')
    if classificacao.get('available'):
        hp = classificacao.get('home_pressure', 0) or 0
        ap = classificacao.get('away_pressure', 0) or 0
        if hp >= 0.7 or ap >= 0.7:
            lado = time_casa if hp >= ap else time_fora
            contexto_linhas.append(f'🎯 Pressão competitiva: {lado}')
    if vermelhos_casa or vermelhos_fora:
        if vermelhos_casa and vermelhos_fora:
            contexto_linhas.append('🟥 Expulsões: 1+ de cada lado')
        elif vermelhos_casa:
            contexto_linhas.append(f'🟥 Expulsão: {time_casa}')
        else:
            contexto_linhas.append(f'🟥 Expulsão: {time_fora}')
    bloco_contexto = ''
    if contexto_linhas:
        bloco_contexto = '\n🧩 *Contexto competitivo:*\n' + '\n'.join(f'• {x}' for x in contexto_linhas) + '\n'

    mensagem = (
        f'🐶 *FARO DE BEAGLE*\n'
        f'{titulo}\n\n'
        f'🏆 *Liga:* {liga}\n'
        f'{time_casa} x {time_fora}\n'
        f'⏱️ {minutagem} — {gols_c}x{gols_f}\n\n'
        f'📊 *GOAL SCORE: {score_100}/100*\n\n'
        f'xG: {xg_tot:.2f} ({xg_h:.2f} x {xg_a:.2f})\n'
        f'Finalizações: {fin_tot} ({fin_h}x{fin_a})\n'
        f'No alvo: {chutes_gol} ({cg_h}x{cg_a})\n'
        f'Grandes chances: {grandes_chances} ({gc_h}x{gc_a})\n'
        f'Escanteios: {escanteios} ({esc_h}x{esc_a})\n\n'
        f'📈 Intensidade: {intensidade}\n'
        f'🔥 Pressão: {pressao_nivel}\n'
        f'🎯 Qualidade das chances: {qualidade}\n\n'
        f'🧠 *Motivos:*\n'
        f'{linhas_motivos}'
        f'{bloco_contexto}\n'
        f'🐶 *FARO:*\n'
        f'{faro}\n\n'
        f'Confiança: {confianca:.1f}/10'
    )

    return mensagem


def registrar_resultado_diario(info, resultado):
    historico_diario.append({
        'mercado': info.get('mercado', ''),
        'event_id': info.get('event_id', ''),
        'mensagem_original': info.get('mensagem_original', ''),
        'resultado': resultado
    })


def enviar_relatorio_diario():
    global ultimo_relatorio_data

    agora = obter_horario_brasil()
    if ultimo_relatorio_data == agora.date():
        return

    # O relatório pertence ao ciclo operacional que começou às 08h.
    # Portanto, quando ele é enviado às 02h, o período começou no dia anterior.
    inicio_operacao = agora.date() - timedelta(days=1)
    data_inicio = inicio_operacao.strftime('%d/%m/%Y')
    data_fim = agora.strftime('%d/%m/%Y')
    total = len(historico_diario)
    greens = sum(1 for item in historico_diario if item['resultado'] == 'GREEN')
    reds = sum(1 for item in historico_diario if item['resultado'] == 'RED')
    aproveitamento = (greens / total * 100) if total else 0.0

    contagem = {
        '05_HT': {'total': 0, 'green': 0, 'red': 0},
        '15_HT': {'total': 0, 'green': 0, 'red': 0},
        'LIMITE_FT': {'total': 0, 'green': 0, 'red': 0},
    }

    for item in historico_diario:
        mercado = item['mercado']
        if mercado in contagem:
            contagem[mercado]['total'] += 1
            if item['resultado'] == 'GREEN':
                contagem[mercado]['green'] += 1
            else:
                contagem[mercado]['red'] += 1

    nomes = {
        '05_HT': '+0,5 HT',
        '15_HT': '+1,5 HT',
        'LIMITE_FT': 'Limite FT',
    }

    linhas = [
        '🐶 *FARO DE BEAGLE*',
        '📊 *RELATÓRIO DA OPERAÇÃO*',
        '━━━━━━━━━━━━━━━━━━',
        '',
        f'📅 Período operacional: {data_inicio} 08h às {data_fim} 02h',
        '',
        f'🚨 Alertas confirmados: {total}',
        f'🟢 Greens: {greens}',
        f'🔴 Reds: {reds}',
        f'📈 Aproveitamento: {aproveitamento:.1f}%',
        '',
        '━━━━━━━━━━━━━━━━━━',
    ]

    for mercado in ('05_HT', '15_HT', 'LIMITE_FT'):
        dados = contagem[mercado]
        taxa = (dados['green'] / dados['total'] * 100) if dados['total'] else 0.0
        linhas.extend([
            '',
            f"🔥 *{nomes[mercado]}*",
            f"Alertas: {dados['total']}",
            f"🟢 Green: {dados['green']}",
            f"🔴 Red: {dados['red']}",
            f"📊 Aproveitamento: {taxa:.1f}%",
        ])

    linhas.extend(['', '━━━━━━━━━━━━━━━━━━', '', '📋 *ALERTAS CONFIRMADOS*'])

    if historico_diario:
        for item in historico_diario:
            marcador = '🟢' if item['resultado'] == 'GREEN' else '🔴'
            partes = item['mensagem_original'].splitlines()
            resumo = []
            for linha in partes:
                if (
                    'FARO DE BEAGLE' in linha
                    or 'Liga:' in linha
                    or '🏆' in linha
                    or ' x ' in linha
                    or '⏱️' in linha
                ):
                    resumo.append(linha.replace('*', ''))
            linhas.append(f"{marcador} " + " | ".join(resumo[:4]))
    else:
        linhas.append('Nenhum alerta confirmado no período.')

    pendentes = list(alertas_pendentes.values())
    if pendentes:
        linhas.extend(['', '⏳ *ALERTAS AINDA EM ABERTO ÀS 02H*'])
        for info in pendentes:
            partes = info.get('mensagem_original', '').splitlines()
            resumo = []
            for linha in partes:
                if (
                    'FARO DE BEAGLE' in linha
                    or 'Liga:' in linha
                    or '🏆' in linha
                    or ' x ' in linha
                    or '⏱️' in linha
                ):
                    resumo.append(linha.replace('*', ''))
            linhas.append('⏳ ' + ' | '.join(resumo[:4]))

    linhas.extend([
        '',
        '━━━━━━━━━━━━━━━━━━',
        '🐶 *FARO DE BEAGLE*',
        '📊 Operação encerrada às 02:00.',
    ])

    mensagem_relatorio = '\n'.join(linhas)
    message_id = enviar_alerta(mensagem_relatorio)
    if message_id:
        ultimo_relatorio_data = agora.date()
        relatorios_por_message_id[message_id] = mensagem_relatorio
        for info in alertas_pendentes.values():
            info['relatorio_message_id'] = message_id
            info['relatorio_mensagem'] = mensagem_relatorio


def atualizar_relatorio_pos_02h(info, resultado):
    """Atualiza o relatório das 02h quando um alerta que estava aberto é confirmado depois."""
    report_id = info.get('relatorio_message_id')
    if not report_id:
        return

    base = relatorios_por_message_id.get(report_id, info.get('relatorio_mensagem', ''))
    if not base:
        return

    marcador = '🟢' if resultado == 'GREEN' else '🔴'
    partes = info.get('mensagem_original', '').splitlines()
    resumo = []
    for linha in partes:
        if (
            'FARO DE BEAGLE' in linha
            or 'Liga:' in linha
            or '🏆' in linha
            or ' x ' in linha
            or '⏱️' in linha
        ):
            resumo.append(linha.replace('*', ''))

    atualizacao = (
        '\n\n━━━━━━━━━━━━━━━━━━\n'
        '🔄 *ATUALIZAÇÃO PÓS-02H*\n'
        f'{marcador} ' + ' | '.join(resumo[:4]) + '\n'
        f'{marcador} Resultado confirmado: {resultado}'
    )

    nova = base + atualizacao
    if editar_alerta(report_id, nova) is None:
        # editar_alerta não retorna status; mantemos o texto local para futuras atualizações.
        pass
    relatorios_por_message_id[report_id] = nova



def validar_alertas_enviados(jogos_dict):
    """Verifica o placar e edita o alerta apenas anexando os emojis de GREEN ou RED ao final."""
    chaves_para_remover = []

    for chave_alerta, info in list(alertas_pendentes.items()):

        event_id = info['event_id']
        message_id = info['message_id']
        gols_no_alerta = info['gols_alerta']
        mercado = info['mercado']
        msg_original = info['mensagem_original']

        item_jogo = jogos_dict.get(event_id)

        if not item_jogo:
            continue

        gols_c = item_jogo.get(
            'homeScore', {}
        ).get(
            'current',
            0
        )

        gols_f = item_jogo.get(
            'awayScore', {}
        ).get(
            'current',
            0
        )

        gols_atuais = gols_c + gols_f

        status_desc = str(
            item_jogo.get('status', {})
            .get('description', '')
        ).lower()

        time_status = str(
            item_jogo.get('status', {})
            .get('type', '')
        ).lower()

        eh_intervalo = (
            'halftime' in status_desc
            or 'ht' in status_desc
            or time_status == 'halftime'
        )

        eh_2h = (
            '2nd' in status_desc
            or time_status == '2nd'
        )

        eh_finalizado = (
            time_status == 'finished'
            or 'ended' in status_desc
            or 'ft' in status_desc
            or 'extra' in status_desc
        )

        if gols_atuais > gols_no_alerta:

            nova_mensagem = (
                f"{msg_original}\n\n"
                f"✅️✅️✅️"
            )

            editar_alerta(
                message_id,
                nova_mensagem
            )

            registrar_resultado_diario(info, 'GREEN')
            if info.get('relatorio_message_id'):
                atualizar_relatorio_pos_02h(info, 'GREEN')

            chaves_para_remover.append(
                chave_alerta
            )

        else:

            if mercado in ['05_HT', '15_HT'] and (
                eh_intervalo
                or eh_2h
                or eh_finalizado
            ):

                nova_mensagem = (
                    f"{msg_original}\n\n"
                    f"❌️❌️❌️"
                )

                editar_alerta(
                    message_id,
                    nova_mensagem
                )

                registrar_resultado_diario(info, 'RED')
                if info.get('relatorio_message_id'):
                    atualizar_relatorio_pos_02h(info, 'RED')

                chaves_para_remover.append(
                    chave_alerta
                )

            elif mercado == 'LIMITE_FT' and eh_finalizado:

                nova_mensagem = (
                    f"{msg_original}\n\n"
                    f"❌️❌️❌️"
                )

                editar_alerta(
                    message_id,
                    nova_mensagem
                )

                registrar_resultado_diario(info, 'RED')
                if info.get('relatorio_message_id'):
                    atualizar_relatorio_pos_02h(info, 'RED')

                chaves_para_remover.append(
                    chave_alerta
                )

    for ch in chaves_para_remover:
        alertas_pendentes.pop(
            ch,
            None
        )


def obter_evento_sofascore(event_id):
    """Busca um evento individual para validar alertas que atravessaram 02h."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}"
    try:
        res = sofascore_get(url.replace('https://api.sofascore.com/api/v1/', ''), timeout=10)
        if res is not None and res.status_code == 200:
            return res.json().get('event')
    except Exception:
        pass
    return None


def checar_alertas_pendentes_fora_do_live(jogos_dict):
    """Inclui no dicionário os alertas pendentes que já saíram da lista live."""
    for info in list(alertas_pendentes.values()):
        event_id = str(info.get('event_id', '')).strip()
        if not event_id or event_id in jogos_dict:
            continue
        evento = obter_evento_sofascore(event_id)
        if evento:
            jogos_dict[event_id] = evento



def checar_jogos_ao_vivo():

    horario = obter_horario_brasil().strftime('%H:%M:%S')

    print(
        f"[{horario}] "
        f"Faro de Beagle buscando partidas "
        f"no Sofascore..."
    )

    url = (
        "https://api.sofascore.com/api/v1/"
        "sport/football/events/live"
    )

    try:

        response = sofascore_get('sport/football/events/live', timeout=15)

        if response is None or response.status_code != 200:

            status = response.status_code if response is not None else 'sem resposta'
            print(
                f"[{horario}] "
                f"Status retornado: {status}"
            )

            return

        dados = response.json()

        jogos = dados.get(
            'events',
            []
        )

        print(
            f"[{horario}] "
            f"Total de partidas ao vivo "
            f"localizadas: {len(jogos)}"
        )

        jogos_dict = {
            str(item.get('id', '')).strip(): item
            for item in jogos
            if item.get('id')
        }

        checar_alertas_pendentes_fora_do_live(
            jogos_dict
        )

        validar_alertas_enviados(
            jogos_dict
        )

        for item in jogos:

            event_id = str(
                item.get('id', '')
            ).strip()

            if not event_id:
                continue

            nome_liga = item.get(
                'tournament', {}
            ).get(
                'name',
                'Liga'
            )

            time_casa = item.get(
                'homeTeam', {}
            ).get(
                'name',
                'Casa'
            )

            time_fora = item.get(
                'awayTeam', {}
            ).get(
                'name',
                'Fora'
            )

            if not eh_partida_valida(
                nome_liga,
                time_casa,
                time_fora
            ):
                continue

            category = item.get(
                'tournament',
                {}
            ).get(
                'category',
                {}
            )

            nome_pais = category.get(
                'name',
                ''
            )

            if (
                nome_pais
                and nome_pais.lower()
                not in nome_liga.lower()
            ):

                liga_formatada = (
                    f"{nome_pais} - {nome_liga}"
                )

            else:

                liga_formatada = nome_liga

            status_desc = str(
                item.get('status', {})
                .get('description', '')
            ).lower()

            time_status = str(
                item.get('status', {})
                .get('type', '')
            ).lower()

            # Descarta se estiver em prorrogação ou disputa de pênaltis
            if any(
                term in status_desc
                or term in time_status
                for term in [
                    'extra',
                    'et',
                    'extratime',
                    'overtime',
                    'penalties'
                ]
            ):
                continue

            gols_c = item.get(
                'homeScore', {}
            ).get(
                'current',
                0
            )

            gols_f = item.get(
                'awayScore', {}
            ).get(
                'current',
                0
            )

            total_gols = (
                gols_c + gols_f
            )

            eh_1h = (
                time_status == 'inprogress'
                and '1st' in status_desc
            )

            eh_2h = (
                time_status == 'inprogress'
                and '2nd' in status_desc
            )

            if not (eh_1h or eh_2h):
                continue

            minutagem, minuto_num = (
                extrair_minutagem_e_numero(
                    item,
                    eh_1h,
                    eh_2h
                )
            )

            if not minuto_num:
                continue

            stats = obter_estatisticas_sofascore(
                event_id
            )

            cg_tot, cg_h, cg_a = (
                extrair_stat_sofascore(
                    stats,
                    'Shots on target'
                )
            )

            cf_tot, cf_h, cf_a = (
                extrair_stat_sofascore(
                    stats,
                    'Shots off target'
                )
            )

            esc_tot, esc_h, esc_a = (
                extrair_stat_sofascore(
                    stats,
                    'Corner kicks'
                )

            )

            # Grandes chances.
            # Caso o SofaScore não forneça o dado,
            # permanece em zero sem quebrar o bot.
            gc_tot, gc_h, gc_a = (
                extrair_stat_sofascore(
                    stats,
                    'Big chances'
                )
            )

            if gc_tot == 0:

                gc_tot, gc_h, gc_a = (
                    extrair_stat_sofascore(
                        stats,
                        'Big chances created'
                    )
                )

            chutes_gol = int(
                cg_tot
            )

            cg_h_int = int(cg_h)
            cg_a_int = int(cg_a)

            fin_tot = int(
                cg_tot + cf_tot
            )

            fin_h_int = int(
                cg_h + cf_h
            )

            fin_a_int = int(
                cg_a + cf_a
            )

            escanteios = int(
                esc_tot
            )

            esc_h_int = int(
                esc_h
            )

            esc_a_int = int(
                esc_a
            )

            grandes_chances = int(
                gc_tot
            )

            xg_tot, xg_h, xg_a = (
                extrair_xg_sofascore(
                    stats
                )
            )

            linha_xg = (
                f"📈 *xG Acumulado:* "
                f"`{xg_tot:.2f}` "
                f"_({time_casa} "
                f"{xg_h:.2f} | "
                f"{xg_a:.2f} "
                f"{time_fora})_\n"
                if xg_tot > 0
                else ""
            )

            # ==================================================================
            # PRESSÃO AVANÇADA
            # ==================================================================

            pressao = (
                obter_pressao_grafico_sofascore(
                    event_id
                )
            )

            linha_fluxo = pressao['texto']

            # ==================================================================
            # PRÉ-LIVE
            # ==================================================================

            prelive_dados = (
                obter_prelive_sofascore(
                    event_id
                )
            )

            linha_prelive = (
                "📋 *Tendência Pré-Live:* "
                "Propenso a Gols ✅\n"
                if prelive_dados
                else ""
            )

            # ==================================================================
            # CONTEXTO COMPETITIVO
            # ==================================================================
            # Favorito pré-live + classificação/objetivo competitivo + expulsões.
            # Fica em cache para reduzir chamadas repetidas ao SofaScore.
            contexto_competitivo = obter_contexto_competitivo(event_id, item)

            # ==================================================================
            # DADOS PARA O LAYOUT DOS ALERTAS
            # ==================================================================
            # ==================================================================
            # 1. OVER 0.5 HT (0x0) -> 15' a 25' DO 1º TEMPO
            # ==================================================================

            if total_gols == 0 and eh_1h:
                if event_id not in notificados_05_ht and 15 <= minuto_num <= 25:

                    aprovado, score, motivos = calcular_score_05_ht(
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        escanteios,
                        grandes_chances,
                        fin_h_int,
                        fin_a_int,
                        pressao
                    )

                    contexto_gol = avaliar_propensao_gol(
                        '05_HT', gols_c, gols_f, xg_tot,
                        fin_h_int, fin_a_int, cg_h_int, cg_a_int,
                        int(gc_h), int(gc_a), pressao,
                        classificar_intensidade(
                            pressao, fin_tot, chutes_gol, grandes_chances
                        ),
                        contexto_competitivo
                    )

                    if aprovado and contexto_gol['aprovado']:
                        notificados_05_ht.add(event_id)

                        mensagem = montar_layout_alerta(
                            '05_HT',
                            liga_formatada,
                            time_casa,
                            time_fora,
                            gols_c,
                            gols_f,
                            minutagem,
                            score,
                            xg_tot,
                            xg_h,
                            xg_a,
                            fin_tot,
                            fin_h_int,
                            fin_a_int,
                            chutes_gol,
                            cg_h_int,
                            cg_a_int,
                            grandes_chances,
                            int(gc_h),
                            int(gc_a),
                            escanteios,
                            esc_h_int,
                            esc_a_int,
                            pressao,
                            analisar_prelive_por_mercado(
                                event_id,
                                item.get('homeTeam', {}).get('id'),
                                item.get('awayTeam', {}).get('id'),
                                '05_HT',
                                total_gols
                            ),
                            contexto_competitivo
                        )

                        msg_id = enviar_alerta(mensagem)
                        if msg_id:
                            alertas_pendentes[f"{event_id}_05_HT"] = {
                                'event_id': event_id,
                                'message_id': msg_id,
                                'gols_alerta': total_gols,
                                'mercado': '05_HT',
                                'mensagem_original': mensagem
                            }

            # ==================================================================
            # 2. OVER 1.5 HT (1x0 / 0x1) -> 18' a 28'
            # ==================================================================

            elif total_gols == 1 and eh_1h:
                if event_id not in notificados_15_ht and 18 <= minuto_num <= 28:

                    aprovado, score, motivos = calcular_score_15_ht(
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        escanteios,
                        grandes_chances,
                        fin_h_int,
                        fin_a_int,
                        pressao
                    )

                    contexto_gol = avaliar_propensao_gol(
                        '15_HT', gols_c, gols_f, xg_tot,
                        fin_h_int, fin_a_int, cg_h_int, cg_a_int,
                        int(gc_h), int(gc_a), pressao,
                        classificar_intensidade(
                            pressao, fin_tot, chutes_gol, grandes_chances
                        ),
                        contexto_competitivo
                    )

                    if aprovado and contexto_gol['aprovado']:
                        notificados_15_ht.add(event_id)

                        mensagem = montar_layout_alerta(
                            '15_HT',
                            liga_formatada,
                            time_casa,
                            time_fora,
                            gols_c,
                            gols_f,
                            minutagem,
                            score,
                            xg_tot,
                            xg_h,
                            xg_a,
                            fin_tot,
                            fin_h_int,
                            fin_a_int,
                            chutes_gol,
                            cg_h_int,
                            cg_a_int,
                            grandes_chances,
                            int(gc_h),
                            int(gc_a),
                            escanteios,
                            esc_h_int,
                            esc_a_int,
                            pressao,
                            analisar_prelive_por_mercado(
                                event_id,
                                item.get('homeTeam', {}).get('id'),
                                item.get('awayTeam', {}).get('id'),
                                '15_HT',
                                total_gols
                            ),
                            contexto_competitivo
                        )

                        msg_id = enviar_alerta(mensagem)
                        if msg_id:
                            alertas_pendentes[f"{event_id}_15_HT"] = {
                                'event_id': event_id,
                                'message_id': msg_id,
                                'gols_alerta': total_gols,
                                'mercado': '15_HT',
                                'mensagem_original': mensagem
                            }

            # ==================================================================
            # 3. OVER LIMITE FT -> 65' a 75'
            # ==================================================================

            elif (
                eh_2h
                and abs(gols_c - gols_f) <= 1
                and total_gols <= 4
            ):
                if event_id not in notificados_limite_ft and 65 <= minuto_num <= 75:

                    aprovado, score, motivos = calcular_score_limite_ft(
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        escanteios,
                        grandes_chances,
                        fin_h_int,
                        fin_a_int,
                        pressao
                    )

                    contexto_gol = avaliar_propensao_gol(
                        'LIMITE_FT', gols_c, gols_f, xg_tot,
                        fin_h_int, fin_a_int, cg_h_int, cg_a_int,
                        int(gc_h), int(gc_a), pressao,
                        classificar_intensidade(
                            pressao, fin_tot, chutes_gol, grandes_chances
                        ),
                        contexto_competitivo
                    )

                    if aprovado and contexto_gol['aprovado']:
                        notificados_limite_ft.add(event_id)

                        mensagem = montar_layout_alerta(
                            'LIMITE_FT',
                            liga_formatada,
                            time_casa,
                            time_fora,
                            gols_c,
                            gols_f,
                            minutagem,
                            score,
                            xg_tot,
                            xg_h,
                            xg_a,
                            fin_tot,
                            fin_h_int,
                            fin_a_int,
                            chutes_gol,
                            cg_h_int,
                            cg_a_int,
                            grandes_chances,
                            int(gc_h),
                            int(gc_a),
                            escanteios,
                            esc_h_int,
                            esc_a_int,
                            pressao,
                            analisar_prelive_por_mercado(
                                event_id,
                                item.get('homeTeam', {}).get('id'),
                                item.get('awayTeam', {}).get('id'),
                                'LIMITE_FT',
                                total_gols
                            ),
                            contexto_competitivo
                        )

                        msg_id = enviar_alerta(mensagem)
                        if msg_id:
                            alertas_pendentes[f"{event_id}_LIMITE_FT"] = {
                                'event_id': event_id,
                                'message_id': msg_id,
                                'gols_alerta': total_gols,
                                'mercado': 'LIMITE_FT',
                                'mensagem_original': mensagem
                            }

    except Exception as e:

        print(
            f"Erro na consulta: {e}"
        )


if __name__ == '__main__':

    horario_inicio = (
        obter_horario_brasil()
        .strftime('%H:%M:%S')
    )

    print(
        f"[{horario_inicio}] "
        f"Faro de Beagle rodando "
        f"08h-02h | ciclo de 120s | HT/FT "
        f"(sem prorrogação)..."
    )

    while True:

        try:

            agora_br = (
                obter_horario_brasil()
            )

            hora_atual = agora_br.hour

            # Cada período operacional começa às 08:00 e gera um novo histórico.
            if hora_atual >= 8:
                if ultima_data_historico != agora_br.date():
                    historico_diario.clear()
                    ultima_data_historico = agora_br.date()

            # Operação: 08:00 até antes de 02:00.
            # A partir de 02:00 o bot para de buscar novos alertas e envia
            # o relatório referente ao ciclo que começou às 08:00 do dia anterior.
            if hora_atual >= 8 or hora_atual < 2:

                checar_jogos_ao_vivo()

            else:

                horario_formatado = (
                    agora_br.strftime('%H:%M:%S')
                )

                print(
                    f"[{horario_formatado}] "
                    f"Bot em repouso fora "
                    f"do horário "
                    f"(08h às 02h)."
                )

                enviar_relatorio_diario()

        except Exception as e:

            print(
                f"Aviso no ciclo principal: {e}"
            )

        time.sleep(120)
