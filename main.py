import time
import cloudscraper
from datetime import datetime
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4'
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
        res = scraper.get(url, timeout=10)

        if res.status_code == 200:
            return res.json().get('statistics', [])

    except Exception:
        pass

    return []


def obter_prelive_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/prematch-form"

    try:
        res = scraper.get(url, timeout=10)

        if res.status_code == 200:
            return res.json()

    except Exception:
        pass

    return None


def obter_pressao_grafico_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/graph"

    try:
        res = scraper.get(url, timeout=10)

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
    confianca = score_100 / 10

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

    data_relatorio = agora.strftime('%d/%m/%Y')
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
        '📊 *RELATÓRIO DO DIA*',
        '━━━━━━━━━━━━━━━━━━',
        '',
        f'📅 {data_relatorio}',
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

    linhas.extend([
        '',
        '━━━━━━━━━━━━━━━━━━',
        '🐶 *FARO DE BEAGLE*',
        '📊 Operação encerrada às 02:00.',
    ])

    if enviar_alerta('\n'.join(linhas)):
        ultimo_relatorio_data = agora.date()


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

                chaves_para_remover.append(
                    chave_alerta
                )

    for ch in chaves_para_remover:
        alertas_pendentes.pop(
            ch,
            None
        )


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

        response = scraper.get(
            url,
            timeout=15
        )

        if response.status_code != 200:

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

                    if aprovado:
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
                            pressao
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

                    if aprovado:
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
                            pressao
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

                    if aprovado:
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
                            pressao
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
