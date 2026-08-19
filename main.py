import os
import time
import cloudscraper
from datetime import datetime
import zoneinfo

# ==============================================================================
# FARO DE BEAGLE
# BOT DE ANÁLISE DE GOLS - SOFASCORE + TELEGRAM
#
# Mercados:
#   1) Over 0.5 HT
#   2) Over 1.5 HT
#   3) Gol Limite FT
#
# Estrutura:
#   SofaScore -> análise ao vivo -> pontuação -> Telegram -> validação GREEN/RED
# ==============================================================================


# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================

TELEGRAM_TOKEN = os.getenv("8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4")
CHAT_ID = os.getenv("1865504705")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN não configurado no Railway.")

if not CHAT_ID:
    raise RuntimeError("CHAT_ID não configurado no Railway.")


# ==============================================================================
# CONFIGURAÇÕES DO BOT
# ==============================================================================

INTERVALO_CONSULTA = 240  # 4 minutos

HORA_INICIO = 8
HORA_FIM = 24


# ==============================================================================
# FILTROS DE PARTIDAS
# ==============================================================================

TERMOS_IGNORADOS = [

    # Categorias de base
    'u15', 'u16', 'u17', 'u18', 'u19', 'u20',
    'u21', 'u22', 'u23',

    'sub-15', 'sub-16', 'sub-17', 'sub-18',
    'sub-19', 'sub-20', 'sub-21', 'sub-22', 'sub-23',

    'sub15', 'sub16', 'sub17', 'sub18',
    'sub19', 'sub20', 'sub21', 'sub22', 'sub23',

    ' youth',
    'youth ',
    'juniors',
    'junior',
    'reserve',
    'reserves',
    'academy',

    'proliga',
    'liga pro',
    'cup u',
    'league u',
    'trophy u',
    'championship u',

    # Feminino
    'women',
    'feminino',
    'femeni',
    "women's",
    'female',
    ' w ',

    # Ligas menores / amadoras
    'amateur',
    'amador',
    'regionaliga',
    'oberliga',
    'landesliga',
    'district',
    'county',
    'regional league',
    'non-league',
    'primera c',
    'primera d',
    'tercera'
]


# ==============================================================================
# SCRAPER
# ==============================================================================

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)


# ==============================================================================
# CONTROLE DE ALERTAS
# ==============================================================================

notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()


# Alertas enviados que ainda precisam ser validados
alertas_pendentes = {}


# ==============================================================================
# HORÁRIO
# ==============================================================================

def obter_horario_brasil():
    fuso_br = zoneinfo.ZoneInfo('America/Sao_Paulo')
    return datetime.now(fuso_br)


# ==============================================================================
# TELEGRAM
# ==============================================================================

def enviar_alerta(mensagem):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown"
    }

    try:

        res = scraper.post(
            url,
            json=payload,
            timeout=10
        )

        if res.status_code == 200:

            dados = res.json()

            return dados.get(
                'result',
                {}
            ).get(
                'message_id'
            )

        print(
            f"Telegram retornou status {res.status_code}: "
            f"{res.text[:200]}"
        )

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

        res = scraper.post(
            url,
            json=payload,
            timeout=10
        )

        if res.status_code != 200:

            print(
                f"Erro ao editar Telegram: "
                f"{res.status_code} - {res.text[:200]}"
            )

    except Exception as e:

        print(f"Erro ao editar mensagem Telegram: {e}")


# ==============================================================================
# SOFASCORE - ESTATÍSTICAS
# ==============================================================================

def obter_estatisticas_sofascore(event_id):

    url = (
        f"https://www.sofascore.com/api/v1/"
        f"event/{event_id}/statistics"
    )

    try:

        res = scraper.get(
            url,
            timeout=10
        )

        if res.status_code == 200:

            return res.json().get(
                'statistics',
                []
            )

    except Exception as e:

        print(
            f"Erro nas estatísticas {event_id}: {e}"
        )

    return []


# ==============================================================================
# SOFASCORE - GRÁFICO DE PRESSÃO
# ==============================================================================

def obter_pressao_grafico_sofascore(event_id):

    url = (
        f"https://www.sofascore.com/api/v1/"
        f"event/{event_id}/graph"
    )

    try:

        res = scraper.get(
            url,
            timeout=10
        )

        if res.status_code != 200:
            return 0, 0, ""

        points = res.json().get(
            'graphPoints',
            []
        )

        if not points:
            return 0, 0, ""

        ultimos_pontos = (
            points[-10:]
            if len(points) >= 10
            else points
        )

        valores = []

        for ponto in ultimos_pontos:

            try:

                valor = float(
                    ponto.get(
                        'value',
                        0
                    )
                )

                valores.append(
                    abs(valor)
                )

            except Exception:
                pass

        if not valores:
            return 0, 0, ""

        pico = max(valores)

        media = sum(valores) / len(valores)

        texto = (
            f"🔥 *Pressão:* "
            f"Pico `{pico:.0f}` | "
            f"Média `{media:.1f}`\n"
        )

        return pico, media, texto

    except Exception:
        pass

    return 0, 0, ""


# ==============================================================================
# EXTRAÇÃO DE ESTATÍSTICAS
# ==============================================================================

def extrair_stat_sofascore(
    stats_data,
    item_names
):

    if not stats_data:
        return 0, 0, 0

    if isinstance(item_names, str):
        item_names = [item_names]

    for period in stats_data:

        if period.get('period') != 'ALL':
            continue

        for group in period.get(
            'groups',
            []
        ):

            for item in group.get(
                'statisticsItems',
                []
            ):

                nome = item.get(
                    'name',
                    ''
                )

                if nome not in item_names:
                    continue

                home_raw = str(
                    item.get(
                        'home',
                        '0'
                    )
                ).replace(
                    '%',
                    ''
                )

                away_raw = str(
                    item.get(
                        'away',
                        '0'
                    )
                ).replace(
                    '%',
                    ''
                )

                try:

                    home = float(
                        home_raw
                    )

                    away = float(
                        away_raw
                    )

                    return (
                        home + away,
                        home,
                        away
                    )

                except ValueError:

                    return 0, 0, 0

    return 0, 0, 0


# ==============================================================================
# xG
# ==============================================================================

def extrair_xg_sofascore(stats_data):

    return extrair_stat_sofascore(
        stats_data,
        [
            'Expected goals',
            'Expected goals (xG)'
        ]
    )


# ==============================================================================
# EXTRAÇÃO COMPLETA
# ==============================================================================

def extrair_dados_estatisticos(stats):

    # Chutes no gol
    sot_tot, sot_h, sot_a = extrair_stat_sofascore(
        stats,
        [
            'Shots on target',
            'Shots on goal'
        ]
    )

    # Chutes fora
    sof_tot, sof_h, sof_a = extrair_stat_sofascore(
        stats,
        [
            'Shots off target'
        ]
    )

    # Finalizações bloqueadas
    blocked_tot, blocked_h, blocked_a = extrair_stat_sofascore(
        stats,
        [
            'Blocked shots'
        ]
    )

    # Finalizações totais
    total_shots, shots_h, shots_a = extrair_stat_sofascore(
        stats,
        [
            'Total shots'
        ]
    )

    # Escanteios
    corners_tot, corners_h, corners_a = extrair_stat_sofascore(
        stats,
        [
            'Corner kicks'
        ]
    )

    # Grandes chances
    big_tot, big_h, big_a = extrair_stat_sofascore(
        stats,
        [
            'Big chances'
        ]
    )

    # Ataques perigosos
    dangerous_tot, dangerous_h, dangerous_a = extrair_stat_sofascore(
        stats,
        [
            'Dangerous attacks'
        ]
    )

    # Ataques
    attacks_tot, attacks_h, attacks_a = extrair_stat_sofascore(
        stats,
        [
            'Attacks'
        ]
    )

    # Posse
    possession_tot, possession_h, possession_a = extrair_stat_sofascore(
        stats,
        [
            'Ball possession'
        ]
    )

    # xG
    xg_tot, xg_h, xg_a = extrair_xg_sofascore(
        stats
    )

    # Se o SofaScore não entregar Total shots,
    # reconstruímos através das categorias disponíveis.
    if total_shots <= 0:

        total_shots = (
            sot_tot
            + sof_tot
            + blocked_tot
        )

        shots_h = (
            sot_h
            + sof_h
            + blocked_h
        )

        shots_a = (
            sot_a
            + sof_a
            + blocked_a
        )

    return {

        'xg': xg_tot,
        'xg_h': xg_h,
        'xg_a': xg_a,

        'sot': sot_tot,
        'sot_h': sot_h,
        'sot_a': sot_a,

        'shots': total_shots,
        'shots_h': shots_h,
        'shots_a': shots_a,

        'corners': corners_tot,
        'corners_h': corners_h,
        'corners_a': corners_a,

        'big': big_tot,
        'big_h': big_h,
        'big_a': big_a,

        'dangerous': dangerous_tot,
        'dangerous_h': dangerous_h,
        'dangerous_a': dangerous_a,

        'attacks': attacks_tot,
        'attacks_h': attacks_h,
        'attacks_a': attacks_a,

        'possession': possession_tot,
        'possession_h': possession_h,
        'possession_a': possession_a
    }


# ==============================================================================
# FILTRO DE PARTIDAS
# ==============================================================================

def eh_partida_valida(
    nome_liga,
    time_casa,
    time_fora
):

    texto = (
        f" {nome_liga} "
        f"{time_casa} "
        f"{time_fora} "
    ).lower()

    for termo in TERMOS_IGNORADOS:

        if termo in texto:
            return False

    return True


# ==============================================================================
# MINUTAGEM
# ==============================================================================

def extrair_minutagem_e_numero(
    item,
    eh_1h,
    eh_2h
):

    status_desc = str(
        item.get(
            'status',
            {}
        ).get(
            'description',
            ''
        )
    ).lower().strip()

    status_type = str(
        item.get(
            'status',
            {}
        ).get(
            'type',
            ''
        )
    ).lower().strip()


    # Bloqueio de prorrogação e pênaltis

    termos_prorrogacao = [
        'extra',
        'extratime',
        'overtime',
        'penalties',
        'pen',
        'prorrogação'
    ]

    for termo in termos_prorrogacao:

        if (
            termo in status_desc
            or termo in status_type
        ):
            return None, None


    minuto = None


    # Tentativa 1:
    # leitura direta da descrição

    if "'" in status_desc:

        min_limpo = (
            status_desc
            .replace("'", "")
            .split('+')[0]
            .strip()
        )

        if min_limpo.isdigit():

            minuto = int(
                min_limpo
            )


    # Tentativa 2:
    # cálculo pelo timestamp

    if minuto is None:

        time_data = item.get(
            'time',
            {}
        )

        if (
            isinstance(
                time_data,
                dict
            )
            and
            time_data.get(
                'currentPeriodStartTimestamp'
            )
        ):

            try:

                now_ts = int(
                    time.time()
                )

                start_ts = int(
                    time_data.get(
                        'currentPeriodStartTimestamp'
                    )
                )

                m_calc = (
                    now_ts - start_ts
                ) // 60

                if eh_2h:
                    m_calc += 45

                if 1 <= m_calc <= 90:
                    minuto = m_calc

            except Exception:
                pass


    if minuto is None:
        return None, None


    # 1º tempo

    if eh_1h and 1 <= minuto <= 45:

        return (
            f"{minuto}' do 1º tempo",
            minuto
        )


    # 2º tempo

    if eh_2h and 45 <= minuto <= 90:

        return (
            f"{minuto}' do 2º tempo",
            minuto
        )


    return None, None


# ==============================================================================
# EQUILÍBRIO DO JOGO
# ==============================================================================

def calcular_equilibrio(
    dados,
    gols_c,
    gols_f
):

    xg_h = dados['xg_h']
    xg_a = dados['xg_a']

    sot_h = dados['sot_h']
    sot_a = dados['sot_a']

    shots_h = dados['shots_h']
    shots_a = dados['shots_a']

    corners_h = dados['corners_h']
    corners_a = dados['corners_a']


    total_xg = xg_h + xg_a
    total_sot = sot_h + sot_a
    total_shots = shots_h + shots_a


    # Sem dados suficientes
    if (
        total_xg <= 0
        and total_sot <= 0
        and total_shots <= 0
    ):
        return 0


    # Quanto maior a concentração,
    # menor o equilíbrio.

    desequilibrios = []


    if total_xg > 0:
        desequilibrios.append(
            abs(xg_h - xg_a)
            / total_xg
        )

    if total_sot > 0:
        desequilibrios.append(
            abs(sot_h - sot_a)
            / total_sot
        )

    if total_shots > 0:
        desequilibrios.append(
            abs(shots_h - shots_a)
            / total_shots
        )

    total_corners = (
        corners_h
        + corners_a
    )

    if total_corners > 0:
        desequilibrios.append(
            abs(corners_h - corners_a)
            / total_corners
        )


    if not desequilibrios:
        return 0


    media = sum(
        desequilibrios
    ) / len(
        desequilibrios
    )


    # 0 = equilibrado
    # 1 = extremamente desequilibrado

    return min(
        1,
        media
    )


# ==============================================================================
# PONTUAÇÃO - OVER 0.5 HT
# ==============================================================================

def pontuar_over_05_ht(
    minuto,
    dados,
    pressao_pico,
    pressao_media
):

    pontos = 0
    motivos = []


    xg = dados['xg']
    sot = dados['sot']
    shots = dados['shots']
    corners = dados['corners']
    big = dados['big']
    dangerous = dados['dangerous']


    # --------------------------------------------------
    # xG
    # --------------------------------------------------

    if xg >= 0.75:

        pontos += 3
        motivos.append(
            "xG muito forte"
        )

    elif xg >= 0.55:

        pontos += 2
        motivos.append(
            "xG forte"
        )

    elif xg >= 0.40:

        pontos += 1
        motivos.append(
            "xG aceitável"
        )


    # --------------------------------------------------
    # Chutes no alvo
    # --------------------------------------------------

    if sot >= 4:

        pontos += 3
        motivos.append(
            "4+ chutes no alvo"
        )

    elif sot >= 3:

        pontos += 2
        motivos.append(
            "3 chutes no alvo"
        )

    elif sot >= 2:

        pontos += 1
        motivos.append(
            "2 chutes no alvo"
        )


    # --------------------------------------------------
    # Finalizações
    # --------------------------------------------------

    if shots >= 10:

        pontos += 2
        motivos.append(
            "10+ finalizações"
        )

    elif shots >= 7:

        pontos += 1
        motivos.append(
            "7+ finalizações"
        )


    # --------------------------------------------------
    # Escanteios
    # --------------------------------------------------

    if corners >= 4:

        pontos += 2
        motivos.append(
            "4+ escanteios"
        )

    elif corners >= 2:

        pontos += 1
        motivos.append(
            "2+ escanteios"
        )


    # --------------------------------------------------
    # Grandes chances
    # --------------------------------------------------

    if big >= 2:

        pontos += 3
        motivos.append(
            "2+ grandes chances"
        )

    elif big >= 1:

        pontos += 2
        motivos.append(
            "grande chance criada"
        )


    # --------------------------------------------------
    # Ataques perigosos
    # --------------------------------------------------

    if dangerous >= 25:

        pontos += 2
        motivos.append(
            "muita pressão ofensiva"
        )

    elif dangerous >= 15:

        pontos += 1
        motivos.append(
            "pressão ofensiva"
        )


    # --------------------------------------------------
    # Gráfico de pressão
    # --------------------------------------------------

    if pressao_pico >= 55:

        pontos += 3
        motivos.append(
            "pico de pressão muito alto"
        )

    elif pressao_pico >= 40:

        pontos += 2
        motivos.append(
            "pico de pressão alto"
        )

    elif pressao_pico >= 30:

        pontos += 1
        motivos.append(
            "pressão consistente"
        )


    # --------------------------------------------------
    # Tempo
    # --------------------------------------------------

    # Depois dos 20', damos maior peso ao volume.
    if minuto >= 20:

        if sot >= 3:
            pontos += 1

        if xg >= 0.55:
            pontos += 1


    return pontos, motivos


# ==============================================================================
# PONTUAÇÃO - OVER 1.5 HT
# ==============================================================================

def pontuar_over_15_ht(
    minuto,
    dados,
    pressao_pico,
    pressao_media
):

    pontos = 0
    motivos = []


    xg = dados['xg']
    sot = dados['sot']
    shots = dados['shots']
    corners = dados['corners']
    big = dados['big']
    dangerous = dados['dangerous']


    # Para buscar o segundo gol no HT,
    # somos mais exigentes.


    # --------------------------------------------------
    # xG
    # --------------------------------------------------

    if xg >= 1.25:

        pontos += 4
        motivos.append(
            "xG muito alto"
        )

    elif xg >= 1.00:

        pontos += 3
        motivos.append(
            "xG alto"
        )

    elif xg >= 0.80:

        pontos += 2
        motivos.append(
            "xG forte"
        )

    elif xg >= 0.65:

        pontos += 1
        motivos.append(
            "xG razoável"
        )


    # --------------------------------------------------
    # Chutes no alvo
    # --------------------------------------------------

    if sot >= 6:

        pontos += 4
        motivos.append(
            "6+ chutes no alvo"
        )

    elif sot >= 4:

        pontos += 3
        motivos.append(
            "4+ chutes no alvo"
        )

    elif sot >= 3:

        pontos += 1
        motivos.append(
            "3 chutes no alvo"
        )


    # --------------------------------------------------
    # Finalizações
    # --------------------------------------------------

    if shots >= 12:

        pontos += 3
        motivos.append(
            "12+ finalizações"
        )

    elif shots >= 9:

        pontos += 2
        motivos.append(
            "9+ finalizações"
        )

    elif shots >= 7:

        pontos += 1


    # --------------------------------------------------
    # Escanteios
    # --------------------------------------------------

    if corners >= 5:

        pontos += 2
        motivos.append(
            "5+ escanteios"
        )

    elif corners >= 3:

        pontos += 1
        motivos.append(
            "3+ escanteios"
        )


    # --------------------------------------------------
    # Grandes chances
    # --------------------------------------------------

    if big >= 2:

        pontos += 4
        motivos.append(
            "2+ grandes chances"
        )

    elif big >= 1:

        pontos += 2
        motivos.append(
            "grande chance criada"
        )


    # --------------------------------------------------
    # Pressão
    # --------------------------------------------------

    if pressao_pico >= 55:

        pontos += 3
        motivos.append(
            "pressão muito alta"
        )

    elif pressao_pico >= 40:

        pontos += 2
        motivos.append(
            "pressão alta"
        )

    elif pressao_pico >= 30:

        pontos += 1


    # --------------------------------------------------
    # Final do HT
    # --------------------------------------------------

    if minuto >= 24:

        if sot >= 4:
            pontos += 1

        if xg >= 1.00:
            pontos += 1


    return pontos, motivos


# ==============================================================================
# PONTUAÇÃO - GOL LIMITE FT
# ==============================================================================

def pontuar_limite_ft(
    minuto,
    dados,
    pressao_pico,
    pressao_media
):

    pontos = 0
    motivos = []


    xg = dados['xg']
    sot = dados['sot']
    shots = dados['shots']
    corners = dados['corners']
    big = dados['big']
    dangerous = dados['dangerous']


    # --------------------------------------------------
    # xG acumulado
    # --------------------------------------------------

    if xg >= 2.40:

        pontos += 4
        motivos.append(
            "xG muito alto"
        )

    elif xg >= 1.90:

        pontos += 3
        motivos.append(
            "xG alto"
        )

    elif xg >= 1.50:

        pontos += 2
        motivos.append(
            "xG forte"
        )

    elif xg >= 1.20:

        pontos += 1
        motivos.append(
            "xG aceitável"
        )


    # --------------------------------------------------
    # Chutes no alvo
    # --------------------------------------------------

    if sot >= 9:

        pontos += 4
        motivos.append(
            "9+ chutes no alvo"
        )

    elif sot >= 7:

        pontos += 3
        motivos.append(
            "7+ chutes no alvo"
        )

    elif sot >= 5:

        pontos += 2
        motivos.append(
            "5+ chutes no alvo"
        )

    elif sot >= 4:

        pontos += 1
        motivos.append(
            "4+ chutes no alvo"
        )


    # --------------------------------------------------
    # Finalizações
    # --------------------------------------------------

    if shots >= 22:

        pontos += 3
        motivos.append(
            "22+ finalizações"
        )

    elif shots >= 17:

        pontos += 2
        motivos.append(
            "17+ finalizações"
        )

    elif shots >= 12:

        pontos += 1
        motivos.append(
            "12+ finalizações"
        )


    # --------------------------------------------------
    # Escanteios
    # --------------------------------------------------

    if corners >= 8:

        pontos += 3
        motivos.append(
            "8+ escanteios"
        )

    elif corners >= 6:

        pontos += 2
        motivos.append(
            "6+ escanteios"
        )

    elif corners >= 4:

        pontos += 1
        motivos.append(
            "4+ escanteios"
        )


    # --------------------------------------------------
    # Grandes chances
    # --------------------------------------------------

    if big >= 4:

        pontos += 4
        motivos.append(
            "4+ grandes chances"
        )

    elif big >= 3:

        pontos += 3
        motivos.append(
            "3+ grandes chances"
        )

    elif big >= 2:

        pontos += 2
        motivos.append(
            "2+ grandes chances"
        )

    elif big >= 1:

        pontos += 1


    # --------------------------------------------------
    # Ataques perigosos
    # --------------------------------------------------

    if dangerous >= 70:

        pontos += 3
        motivos.append(
            "70+ ataques perigosos"
        )

    elif dangerous >= 50:

        pontos += 2
        motivos.append(
            "50+ ataques perigosos"
        )

    elif dangerous >= 35:

        pontos += 1


    # --------------------------------------------------
    # Pressão
    # --------------------------------------------------

    if pressao_pico >= 60:

        pontos += 4
        motivos.append(
            "pico de pressão muito alto"
        )

    elif pressao_pico >= 45:

        pontos += 3
        motivos.append(
            "pico de pressão alto"
        )

    elif pressao_pico >= 30:

        pontos += 1


    # --------------------------------------------------
    # Últimos minutos
    # --------------------------------------------------

    if minuto >= 70:

        if sot >= 6:
            pontos += 1

        if corners >= 5:
            pontos += 1


    return pontos, motivos


# ==============================================================================
# CLASSIFICAÇÃO
# ==============================================================================

def classificar_pontuacao(
    pontos,
    mercado
):

    if mercado == '05_HT':

        if pontos >= 12:
            return "🔥 MUITO FORTE"

        if pontos >= 9:
            return "🟢 FORTE"

        if pontos >= 7:
            return "🟡 MODERADO"

        return "⚪ FRACO"


    if mercado == '15_HT':

        if pontos >= 15:
            return "🔥 MUITO FORTE"

        if pontos >= 12:
            return "🟢 FORTE"

        if pontos >= 9:
            return "🟡 MODERADO"

        return "⚪ FRACO"


    if mercado == 'LIMITE_FT':

        if pontos >= 17:
            return "🔥 MUITO FORTE"

        if pontos >= 14:
            return "🟢 FORTE"

        if pontos >= 11:
            return "🟡 MODERADO"

        return "⚪ FRACO"


    return "⚪"


# ==============================================================================
# TEXTO DE ESTATÍSTICAS
# ==============================================================================

def montar_bloco_estatisticas(
    dados,
    time_casa,
    time_fora,
    pressao_texto
):

    linha_xg = ""

    if dados['xg'] > 0:

        linha_xg = (
            f"📈 *xG:* `{dados['xg']:.2f}` "
            f"_({time_casa} "
            f"{dados['xg_h']:.2f} | "
            f"{dados['xg_a']:.2f} "
            f"{time_fora})_\n"
        )


    return (

        linha_xg

        +

        f"🎯 *Chutes no Gol:* "
        f"`{int(dados['sot'])}` "
        f"_({int(dados['sot_h'])}x"
        f"{int(dados['sot_a'])})_\n"

        +

        f"⚽ *Finalizações:* "
        f"`{int(dados['shots'])}` "
        f"_({int(dados['shots_h'])}x"
        f"{int(dados['shots_a'])})_\n"

        +

        f"🚩 *Escanteios:* "
        f"`{int(dados['corners'])}` "
        f"_({int(dados['corners_h'])}x"
        f"{int(dados['corners_a'])})\n"

        +

        f"💥 *Grandes Chances:* "
        f"`{int(dados['big'])}` "
        f"_({int(dados['big_h'])}x"
        f"{int(dados['big_a'])})\n"

        +

        f"🔥 *Ataques Perigosos:* "
        f"`{int(dados['dangerous'])}` "
        f"_({int(dados['dangerous_h'])}x"
        f"{int(dados['dangerous_a'])})\n"

        +

        pressao_texto
    )


# ==============================================================================
# VALIDAÇÃO DOS ALERTAS
# ==============================================================================

def validar_alertas_enviados(
    jogos_dict
):

    chaves_para_remover = []


    for chave_alerta, info in list(
        alertas_pendentes.items()
    ):

        event_id = info['event_id']

        message_id = info['message_id']

        gols_no_alerta = info['gols_alerta']

        mercado = info['mercado']

        msg_original = info['mensagem_original']


        item_jogo = jogos_dict.get(
            event_id
        )


        # Se o jogo desapareceu do endpoint
        # ao vivo, esperamos a próxima rodada.
        if not item_jogo:
            continue


        gols_c = item_jogo.get(
            'homeScore',
            {}
        ).get(
            'current',
            0
        )

        gols_f = item_jogo.get(
            'awayScore',
            {}
        ).get(
            'current',
            0
        )


        gols_atuais = (
            gols_c
            + gols_f
        )


        status_desc = str(
            item_jogo.get(
                'status',
                {}
            ).get(
                'description',
                ''
            )
        ).lower()


        time_status = str(
            item_jogo.get(
                'status',
                {}
            ).get(
                'type',
                ''
            )
        ).lower()


        eh_intervalo = (
            'halftime' in status_desc
            or 'half time' in status_desc
            or time_status == 'halftime'
        )


        eh_2h = (
            '2nd' in status_desc
            or 'second half' in status_desc
        )


        eh_finalizado = (
            time_status == 'finished'
            or 'ended' in status_desc
            or 'ft' in status_desc
        )


        # ==============================================================
        # GREEN
        # ==============================================================

        if gols_atuais > gols_no_alerta:

            nova_mensagem = (
                f"{msg_original}\n\n"
                f"✅️✅️✅️ *GREEN*"
            )

            editar_alerta(
                message_id,
                nova_mensagem
            )

            chaves_para_remover.append(
                chave_alerta
            )

            continue


        # ==============================================================
        # RED HT
        # ==============================================================

        if mercado in [
            '05_HT',
            '15_HT'
        ]:

            if (
                eh_intervalo
                or eh_2h
                or eh_finalizado
            ):

                nova_mensagem = (
                    f"{msg_original}\n\n"
                    f"❌️❌️❌️ *RED*"
                )

                editar_alerta(
                    message_id,
                    nova_mensagem
                )

                chaves_para_remover.append(
                    chave_alerta
                )


        # ==============================================================
        # RED FT
        # ==============================================================

        elif mercado == 'LIMITE_FT':

            if eh_finalizado:

                nova_mensagem = (
                    f"{msg_original}\n\n"
                    f"❌️❌️❌️ *RED*"
                )

                editar_alerta(
                    message_id,
                    nova_mensagem
                )

                chaves_para_remover.append(
                    chave_alerta
                )


    for chave in chaves_para_remover:

        alertas_pendentes.pop(
            chave,
            None
        )


# ==============================================================================
# CONSULTA PRINCIPAL
# ==============================================================================

def checar_jogos_ao_vivo():

    horario = obter_horario_brasil().strftime(
        '%H:%M:%S'
    )

    print(
        f"[{horario}] "
        f"Faro de Beagle buscando partidas no SofaScore..."
    )


    url = (
        "https://www.sofascore.com/api/v1/"
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
                f"SofaScore retornou "
                f"{response.status_code}"
            )

            return


        dados_response = response.json()

        jogos = dados_response.get(
            'events',
            []
        )


        print(
            f"[{horario}] "
            f"Partidas ao vivo: {len(jogos)}"
        )


        jogos_dict = {

            str(
                item.get('id')
            ).strip(): item

            for item in jogos

            if item.get('id')
        }


        # Primeiro valida os alertas antigos
        validar_alertas_enviados(
            jogos_dict
        )


        # ==============================================================
        # ANALISA CADA JOGO
        # ==============================================================

        for item in jogos:


            event_id = str(
                item.get('id', '')
            ).strip()


            if not event_id:
                continue


            nome_liga = item.get(
                'tournament',
                {}
            ).get(
                'name',
                'Liga'
            )


            time_casa = item.get(
                'homeTeam',
                {}
            ).get(
                'name',
                'Casa'
            )


            time_fora = item.get(
                'awayTeam',
                {}
            ).get(
                'name',
                'Fora'
            )


            # ----------------------------------------------------------
            # FILTRO
            # ----------------------------------------------------------

            if not eh_partida_valida(
                nome_liga,
                time_casa,
                time_fora
            ):

                continue


            # ----------------------------------------------------------
            # LIGA / PAÍS
            # ----------------------------------------------------------

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
                    f"{nome_pais} - "
                    f"{nome_liga}"
                )

            else:

                liga_formatada = nome_liga


            # ----------------------------------------------------------
            # STATUS
            # ----------------------------------------------------------

            status_desc = str(
                item.get(
                    'status',
                    {}
                ).get(
                    'description',
                    ''
                )
            ).lower()


            time_status = str(
                item.get(
                    'status',
                    {}
                ).get(
                    'type',
                    ''
                )
            ).lower()


            # ----------------------------------------------------------
            # BLOQUEIO PRORROGAÇÃO
            # ----------------------------------------------------------

            if any(
                termo in status_desc
                or termo in time_status

                for termo in [
                    'extra',
                    'extratime',
                    'overtime',
                    'penalties',
                    'pen'
                ]
            ):

                continue


            # ----------------------------------------------------------
            # PLACAR
            # ----------------------------------------------------------

            gols_c = item.get(
                'homeScore',
                {}
            ).get(
                'current',
                0
            )


            gols_f = item.get(
                'awayScore',
                {}
            ).get(
                'current',
                0
            )


            total_gols = (
                gols_c
                + gols_f
            )


            # ----------------------------------------------------------
            # TEMPO
            # ----------------------------------------------------------

            eh_1h = (
                time_status == 'inprogress'
                and (
                    '1st' in status_desc
                    or 'first half' in status_desc
                )
            )


            eh_2h = (
                time_status == 'inprogress'
                and (
                    '2nd' in status_desc
                    or 'second half' in status_desc
                )
            )


            if not (
                eh_1h
                or eh_2h
            ):

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


            # ==========================================================
            # ESTATÍSTICAS
            # ==========================================================

            stats = obter_estatisticas_sofascore(
                event_id
            )


            dados_estatisticos = (
                extrair_dados_estatisticos(
                    stats
                )
            )


            # ==========================================================
            # PRESSÃO
            # ==========================================================

            pressao_pico, pressao_media, pressao_texto = (
                obter_pressao_grafico_sofascore(
                    event_id
                )
            )


            # ==========================================================
            # EQUILÍBRIO
            # ==========================================================

            equilibrio = calcular_equilibrio(
                dados_estatisticos,
                gols_c,
                gols_f
            )


            # ==========================================================
            # BLOCO DE ESTATÍSTICAS
            # ==========================================================

            bloco_estatisticas = (
                montar_bloco_estatisticas(
                    dados_estatisticos,
                    time_casa,
                    time_fora,
                    pressao_texto
                )
            )


            # ==========================================================
            # 1. OVER 0.5 HT
            #
            # 0x0
            # Janela: 15' até 25'
            # ==========================================================

            if (
                total_gols == 0
                and eh_1h
                and 15 <= minuto_num <= 25
            ):


                if event_id not in notificados_05_ht:


                    pontos, motivos = (
                        pontuar_over_05_ht(
                            minuto_num,
                            dados_estatisticos,
                            pressao_pico,
                            pressao_media
                        )
                    )


                    # Penalização para jogo extremamente
                    # desequilibrado.

                    if equilibrio > 0.70:
                        pontos -= 2


                    # Proteção contra pontuação negativa

                    pontos = max(
                        0,
                        pontos
                    )


                    classificacao = (
                        classificar_pontuacao(
                            pontos,
                            '05_HT'
                        )
                    )


                    # --------------------------------------------------
                    # Gatilho mínimo
                    # --------------------------------------------------

                    sinal_valido = False


                    if (
                        pontos >= 9
                        and (
                            dados_estatisticos['xg'] >= 0.40
                            or dados_estatisticos['sot'] >= 3
                            or dados_estatisticos['big'] >= 1
                        )
                    ):

                        sinal_valido = True


                    if sinal_valido:


                        notificados_05_ht.add(
                            event_id
                        )


                        motivos_txt = (
                            " • ".join(
                                motivos[:6]
                            )
                        )


                        mensagem = (

                            f"🚨 *FARO DE BEAGLE* 🚨\n"
                            f"⚽ *OVER 0.5 HT*\n\n"

                            f"🏆 *Liga:* "
                            f"{liga_formatada}\n"

                            f"⚽ *{time_casa} "
                            f"{gols_c} x {gols_f} "
                            f"{time_fora}*\n"

                            f"⏱️ *Tempo:* "
                            f"{minutagem}\n\n"

                            f"📊 *ANÁLISE AO VIVO*\n"

                            f"{bloco_estatisticas}\n"

                            f"🧠 *Score:* "
                            f"`{pontos}/20` "
                            f"{classificacao}\n\n"

                            f"🔎 *Indicadores:* "
                            f"{motivos_txt}\n\n"

                            f"💡 *Mercado:* "
                            f"Over 0.5 HT"
                        )


                        msg_id = enviar_alerta(
                            mensagem
                        )


                        if msg_id:

                            alertas_pendentes[
                                f"{event_id}_05_HT"
                            ] = {

                                'event_id':
                                    event_id,

                                'message_id':
                                    msg_id,

                                'gols_alerta':
                                    total_gols,

                                'mercado':
                                    '05_HT',

                                'mensagem_original':
                                    mensagem
                            }


            # ==========================================================
            # 2. OVER 1.5 HT
            #
            # 1x0 ou 0x1
            # Janela: 18' até 28'
            # ==========================================================

            elif (
                total_gols == 1
                and eh_1h
                and 18 <= minuto_num <= 28
            ):


                if event_id not in notificados_15_ht:


                    pontos, motivos = (
                        pontuar_over_15_ht(
                            minuto_num,
                            dados_estatisticos,
                            pressao_pico,
                            pressao_media
                        )
                    )


                    # Se o jogo estiver extremamente
                    # desequilibrado, reduzimos a pontuação.

                    if equilibrio > 0.70:
                        pontos -= 2


                    pontos = max(
                        0,
                        pontos
                    )


                    classificacao = (
                        classificar_pontuacao(
                            pontos,
                            '15_HT'
                        )
                    )


                    sinal_valido = False


                    # Gatilho mais exigente.
                    # Afinal, precisamos do segundo gol
                    # antes do intervalo.

                    if (
                        pontos >= 12
                        and (
                            dados_estatisticos['xg'] >= 0.80
                            or dados_estatisticos['sot'] >= 4
                            or dados_estatisticos['big'] >= 1
                        )
                    ):

                        sinal_valido = True


                    if sinal_valido:


                        notificados_15_ht.add(
                            event_id
                        )


                        motivos_txt = (
                            " • ".join(
                                motivos[:6]
                            )
                        )


                        mensagem = (

                            f"⚡ *FARO DE BEAGLE* ⚡\n"
                            f"⚽ *OVER 1.5 HT — 2º GOL*\n\n"

                            f"🏆 *Liga:* "
                            f"{liga_formatada}\n"

                            f"⚽ *{time_casa} "
                            f"{gols_c} x {gols_f} "
                            f"{time_fora}*\n"

                            f"⏱️ *Tempo:* "
                            f"{minutagem}\n\n"

                            f"📊 *ANÁLISE AO VIVO*\n"

                            f"{bloco_estatisticas}\n"

                            f"🧠 *Score:* "
                            f"`{pontos}/24` "
                            f"{classificacao}\n\n"

                            f"🔎 *Indicadores:* "
                            f"{motivos_txt}\n\n"

                            f"💡 *Mercado:* "
                            f"Over 1.5 HT"
                        )


                        msg_id = enviar_alerta(
                            mensagem
                        )


                        if msg_id:

                            alertas_pendentes[
                                f"{event_id}_15_HT"
                            ] = {

                                'event_id':
                                    event_id,

                                'message_id':
                                    msg_id,

                                'gols_alerta':
                                    total_gols,

                                'mercado':
                                    '15_HT',

                                'mensagem_original':
                                    mensagem
                            }


            # ==========================================================
            # 3. GOL LIMITE FT
            #
            # Janela: 65' até 75'
            #
            # Regras:
            # - diferença máxima de 1 gol
            # - máximo 4 gols no jogo
            # ==========================================================

            elif (
                eh_2h
                and abs(
                    gols_c - gols_f
                ) <= 1
                and total_gols <= 4
                and 65 <= minuto_num <= 75
            ):


                if event_id not in notificados_limite_ft:


                    pontos, motivos = (
                        pontuar_limite_ft(
                            minuto_num,
                            dados_estatisticos,
                            pressao_pico,
                            pressao_media
                        )
                    )


                    # --------------------------------------------------
                    # Penalização por placar
                    # --------------------------------------------------

                    if total_gols == 0:

                        # 0x0 aos 70' exige muito mais
                        # evidência de pressão.

                        pontos -= 3

                    elif total_gols >= 4:

                        pontos -= 2


                    # --------------------------------------------------
                    # Jogo extremamente desequilibrado
                    # --------------------------------------------------

                    if equilibrio > 0.75:

                        pontos -= 2


                    pontos = max(
                        0,
                        pontos
                    )


                    classificacao = (
                        classificar_pontuacao(
                            pontos,
                            'LIMITE_FT'
                        )
                    )


                    # --------------------------------------------------
                    # Mercado do próximo gol
                    # --------------------------------------------------

                    proximo_gol = (
                        total_gols + 0.5
                    )


                    # --------------------------------------------------
                    # Gatilho
                    # --------------------------------------------------

                    sinal_valido = False


                    if (
                        pontos >= 14
                        and (
                            dados_estatisticos['xg'] >= 1.50
                            or dados_estatisticos['sot'] >= 6
                            or dados_estatisticos['big'] >= 2
                        )
                    ):

                        sinal_valido = True


                    if sinal_valido:


                        notificados_limite_ft.add(
                            event_id
                        )


                        motivos_txt = (
                            " • ".join(
                                motivos[:7]
                            )
                        )


                        mensagem = (

                            f"🎯 *FARO DE BEAGLE* 🎯\n"
                            f"⚽ *GOL LIMITE FT*\n\n"

                            f"🏆 *Liga:* "
                            f"{liga_formatada}\n"

                            f"⚽ *{time_casa} "
                            f"{gols_c} x {gols_f} "
                            f"{time_fora}*\n"

                            f"⏱️ *Tempo:* "
                            f"{minutagem}\n\n"

                            f"🎯 *Próxima linha:* "
                            f"Over {proximo_gol}\n\n"

                            f"📊 *ANÁLISE AO VIVO*\n"

                            f"{bloco_estatisticas}\n"

                            f"🧠 *Score:* "
                            f"`{pontos}/25` "
                            f"{classificacao}\n\n"

                            f"🔎 *Indicadores:* "
                            f"{motivos_txt}\n\n"

                            f"💡 *Mercado:* "
                            f"Próximo gol / "
                            f"Over limite FT"
                        )


                        msg_id = enviar_alerta(
                            mensagem
                        )


                        if msg_id:

                            alertas_pendentes[
                                f"{event_id}_LIMITE_FT"
                            ] = {

                                'event_id':
                                    event_id,

                                'message_id':
                                    msg_id,

                                'gols_alerta':
                                    total_gols,

                                'mercado':
                                    'LIMITE_FT',

                                'mensagem_original':
                                    mensagem
                            }


    except Exception as e:

        print(
            f"Erro na consulta principal: {e}"
        )


# ==============================================================================
# INICIALIZAÇÃO
# ==============================================================================

if __name__ == '__main__':


    horario_inicio = (
        obter_horario_brasil()
        .strftime('%H:%M:%S')
    )


    print(
        f"[{horario_inicio}] "
        f"========================================"
    )

    print(
        f"[{horario_inicio}] "
        f"FARO DE BEAGLE INICIADO"
    )

    print(
        f"[{horario_inicio}] "
        f"Mercados: Over 0.5 HT | "
        f"Over 1.5 HT | Gol Limite FT"
    )

    print(
        f"[{horario_inicio}] "
        f"Intervalo: "
        f"{INTERVALO_CONSULTA}s"
    )

    print(
        f"[{horario_inicio}] "
        f"Horário: "
        f"{HORA_INICIO:02d}:00 até 00:00"
    )

    print(
        f"[{horario_inicio}] "
        f"========================================"
    )


    while True:

        try:

            agora_br = (
                obter_horario_brasil()
            )

            hora_atual = (
                agora_br.hour
            )


            if (
                HORA_INICIO
                <= hora_atual
                < HORA_FIM
            ):

                checar_jogos_ao_vivo()


            else:

                horario_formatado = (
                    agora_br
                    .strftime('%H:%M:%S')
                )

                print(
                    f"[{horario_formatado}] "
                    f"Bot em repouso fora "
                    f"do horário "
                    f"(08h às 00h)."
                )


        except Exception as e:

            print(
                f"Aviso no ciclo principal: {e}"
            )


        time.sleep(
            INTERVALO_CONSULTA
    )
