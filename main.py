import time
import cloudscraper
from datetime import datetime, timedelta
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAEm4h212tRP1DI_8h2XJbXKzRzhNZUa62g'
CHAT_ID = '1865504705'

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

# Camada de acesso ao SofaScore com headers XHR e fallback de domínio.
# Mantém o restante do funcionamento do bot inalterado.
SOFASCORE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://www.sofascore.com/',
    'Origin': 'https://www.sofascore.com',
    'X-Requested-With': 'XMLHttpRequest',
}

# Ordem de acesso: API principal -> proxy do próprio site -> espelho.
# O api.sofascore.app está retornando 404 para os endpoints usados pelo bot,
# portanto ele foi removido da rota de fallback.
SOFASCORE_BASES = [
    'https://api.sofascore.com/api/v1',
    'https://www.sofascore.com/api/v1',
]

def sofascore_get(path, timeout=10):
    path = path.lstrip('/')
    ultimo_status = None

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

            # 404 em endpoints individuais do SofaScore é esperado em
            # alguns eventos/dados indisponíveis. Não imprimir cada 404
            # evita saturar os logs do Railway.
            if res.status_code != 404:
                print(
                    f'SofaScore {url}: status {res.status_code}'
                )

        except Exception as e:
            print(f'Erro SofaScore {url}: {e}')

    # Não gerar uma linha de log para cada endpoint que simplesmente
    # respondeu 404. Erros diferentes de 404 continuam visíveis.
    if ultimo_status is not None and ultimo_status != 404:
        print(
            f'SofaScore: nenhuma rota respondeu 200 para {path} '
            f'(último status: {ultimo_status})'
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
def avaliar_propensao_gol(
    mercado,
    gols_c,
    gols_f,
    xg_tot,
    fin_h,
    fin_a,
    chutes_h,
    chutes_a,
    gc_h,
    gc_a,
    pressao,
    intensidade
):
    """
    Camada final de PROPENSÃO AO GOL.
    O Goal Score continua intacto; esta função avalia o contexto atual:
    placar, equipe atrás, produção de cada lado e pressão recente.
    Não presume necessidade de resultado pela tabela, pois o bot não
    consulta classificação/objetivo competitivo nesta versão.
    """
    pontos = 0
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

    # HT: confirmação de que o jogo continua vivo.
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

        aprovado = pontos >= 1
        return {
            'aprovado': aprovado,
            'pontos': pontos,
            'nivel': 'ALTA' if pontos >= 2 else ('MÉDIA' if pontos >= 1 else 'BAIXA'),
            'motivos': motivos
        }

    # FT: pergunta primeiro se existe contexto para um próximo gol.
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
            fin_trailing, shots_trailing = fin_h, chutes_h
            gc_trailing = gc_h
        else:
            fin_trailing, shots_trailing = fin_a, chutes_a
            gc_trailing = gc_a

        share_fin = fin_trailing / total_fin if total_fin else 0
        share_shots = shots_trailing / total_chutes if total_chutes else 0
        share_gc = gc_trailing / total_gc if total_gc else 0

        if share_fin >= 0.40 or share_shots >= 0.40 or share_gc >= 0.50:
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

    else:
        pontos -= 2
        motivos.append('vantagem de dois ou mais gols')

    if mercado == 'LIMITE_FT':
        if recente >= 35:
            pontos += 1
        if aceleracao >= 6:
            pontos += 1

    # Para o limite FT, a entrada só passa quando há evidência contextual
    # suficiente de que um novo gol continua plausível.
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
        'motivos': motivos
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
        f'{linhas_motivos}\n'
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
        f'📅 Período: {data_inicio} 08h às {data_fim} 02h',
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

            print(
                f"[{horario}] "
                f"Status retornado: "
                f"{response.status_code}"
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
                        )
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
                            )
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
                        )
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
                            )
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
                        )
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
                            )
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
        f"restrito a HT/FT "
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
