import time
import cloudscraper
from datetime import datetime
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================

TELEGRAM_TOKEN = 'COLOQUE_AQUI_SEU_NOVO_TOKEN'
CHAT_ID = '1865504705'

TERMOS_IGNORADOS = [
    # Categorias de Base
    'u15', 'u16', 'u17', 'u18', 'u19', 'u20', 'u21', 'u22', 'u23',
    'sub-15', 'sub-16', 'sub-17', 'sub-18', 'sub-19', 'sub-20',
    'sub-21', 'sub-22', 'sub-23',
    'sub15', 'sub16', 'sub17', 'sub18', 'sub19', 'sub20',
    'sub21', 'sub22', 'sub23',
    ' youth', 'youth ', 'juniors', 'junior', 'reserve', 'reserves',
    'academy',
    'proliga', 'liga pro', 'cup u', 'league u', 'trophy u',
    'championship u',

    # Feminino
    'women', 'feminino', 'femeni', 'women\'s', 'female', ' w ',

    # Ligas menores / amadoras
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

# ==============================================================================
# CONTROLE DE ALERTAS
# ==============================================================================

notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()

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

    except Exception as e:
        print(
            f"Erro ao enviar Telegram: {e}"
        )

    return None


def editar_alerta(message_id, nova_mensagem):
    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/editMessageText"
    )

    payload = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": nova_mensagem,
        "parse_mode": "Markdown"
    }

    try:
        scraper.post(
            url,
            json=payload,
            timeout=10
        )

    except Exception as e:
        print(
            f"Erro ao editar mensagem Telegram: {e}"
        )


# ==============================================================================
# SOFASCORE
# ==============================================================================

def obter_estatisticas_sofascore(event_id):
    url = (
        f"https://api.sofascore.com/api/v1/"
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

    except Exception:
        pass

    return []


def obter_prelive_sofascore(event_id):
    url = (
        f"https://api.sofascore.com/api/v1/"
        f"event/{event_id}/prematch-form"
    )

    try:
        res = scraper.get(
            url,
            timeout=10
        )

        if res.status_code == 200:
            return res.json()

    except Exception:
        pass

    return None


# ==============================================================================
# GRÁFICO DE PRESSÃO
# ==============================================================================

def obter_pressao_grafico_sofascore(event_id):

    url = (
        f"https://api.sofascore.com/api/v1/"
        f"event/{event_id}/graph"
    )

    try:
        res = scraper.get(
            url,
            timeout=10
        )

        if res.status_code != 200:
            return {
                'pico': 0,
                'media': 0,
                'recente': 0,
                'aceleracao': 0,
                'direcao': 0
            }

        points = res.json().get(
            'graphPoints',
            []
        )

        if not points:
            return {
                'pico': 0,
                'media': 0,
                'recente': 0,
                'aceleracao': 0,
                'direcao': 0
            }

        # Janela recente
        ultimos_pontos = (
            points[-10:]
            if len(points) >= 10
            else points
        )

        valores = []

        for p in ultimos_pontos:
            try:
                valores.append(
                    float(
                        p.get(
                            'value',
                            0
                        )
                    )
                )
            except Exception:
                valores.append(0)

        if not valores:
            return {
                'pico': 0,
                'media': 0,
                'recente': 0,
                'aceleracao': 0,
                'direcao': 0
            }

        metade = max(
            1,
            len(valores) // 2
        )

        primeira_metade = valores[:metade]
        segunda_metade = valores[metade:]

        media_abs = (
            sum(
                abs(x)
                for x in valores
            ) / len(valores)
        )

        media_anterior = (
            sum(
                abs(x)
                for x in primeira_metade
            ) / len(primeira_metade)
            if primeira_metade
            else 0
        )

        media_recente = (
            sum(
                abs(x)
                for x in segunda_metade
            ) / len(segunda_metade)
            if segunda_metade
            else media_abs
        )

        pico = max(
            abs(x)
            for x in valores
        )

        aceleracao = (
            media_recente
            - media_anterior
        )

        direcao = (
            sum(segunda_metade)
            / len(segunda_metade)
            if segunda_metade
            else 0
        )

        return {
            'pico': pico,
            'media': media_abs,
            'recente': media_recente,
            'aceleracao': aceleracao,
            'direcao': direcao
        }

    except Exception:
        pass

    return {
        'pico': 0,
        'media': 0,
        'recente': 0,
        'aceleracao': 0,
        'direcao': 0
    }


# ==============================================================================
# EXTRAÇÃO DE ESTATÍSTICAS
# ==============================================================================

def extrair_stat_sofascore(
    stats_data,
    item_name
):

    if not stats_data:
        return 0, 0, 0

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

                if item.get('name') != item_name:
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

                    val_home = float(
                        home_raw
                    )

                    val_away = float(
                        away_raw
                    )

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
        return (
            xg_total,
            xg_home,
            xg_away
        )

    return extrair_stat_sofascore(
        stats_data,
        'Expected goals (xG)'
    )


# ==============================================================================
# VALIDAÇÃO DA PARTIDA
# ==============================================================================

def eh_partida_valida(
    nome_liga,
    time_casa,
    time_fora
):

    texto_completo = (
        f" {nome_liga} "
        f"{time_casa} "
        f"{time_fora} "
    ).lower()

    for termo in TERMOS_IGNORADOS:

        if termo in texto_completo:
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

        if (
            termo in status_desc
            or termo in status_type
        ):
            return None, None

    minuto = None

    if "'" in status_desc:

        min_limpo = (
            status_desc
            .replace(
                "'",
                ""
            )
            .split('+')[0]
            .strip()
        )

        if min_limpo.isdigit():
            minuto = int(
                min_limpo
            )

    if not minuto:

        time_data = item.get(
            'time',
            {}
        )

        if (
            isinstance(
                time_data,
                dict
            )
            and time_data.get(
                'currentPeriodStartTimestamp'
            )
        ):

            now_ts = int(
                time.time()
            )

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

        if (
            eh_1h
            and minuto <= 45
        ):
            return (
                f"{minuto}' do 1º tempo",
                minuto
            )

        if (
            eh_2h
            and 45 <= minuto <= 90
        ):
            return (
                f"{minuto}' do 2º tempo",
                minuto
            )

    return None, None


# ==============================================================================
# CLASSIFICAÇÃO DE INTENSIDADE
# ==============================================================================

def classificar_intensidade(
    pressao
):

    aceleracao = pressao.get(
        'aceleracao',
        0
    )

    recente = pressao.get(
        'recente',
        0
    )

    if (
        aceleracao >= 8
        and recente >= 25
    ):
        return "CRESCENTE"

    if (
        aceleracao <= -8
        and recente < 25
    ):
        return "CAINDO"

    return "ESTÁVEL"


# ==============================================================================
# CLASSIFICAÇÃO DA PRESSÃO
# ==============================================================================

def classificar_pressao(
    pressao
):

    recente = pressao.get(
        'recente',
        0
    )

    pico = pressao.get(
        'pico',
        0
    )

    if (
        recente >= 40
        or pico >= 55
    ):
        return "ALTA"

    if (
        recente >= 25
        or pico >= 35
    ):
        return "MÉDIA"

    return "BAIXA"


# ==============================================================================
# QUALIDADE DAS CHANCES
# ==============================================================================

def classificar_qualidade_chances(
    xg_tot,
    grandes_chances,
    chutes_gol,
    finalizacoes
):

    # Alta qualidade
    if (
        grandes_chances >= 2
        or xg_tot >= 1.00
        or (
            chutes_gol >= 4
            and xg_tot >= 0.70
        )
    ):
        return "ALTA"

    # Média qualidade
    if (
        grandes_chances >= 1
        or xg_tot >= 0.55
        or chutes_gol >= 3
        or (
            finalizacoes >= 8
            and xg_tot >= 0.45
        )
    ):
        return "MÉDIA"

    return "BAIXA"


# ==============================================================================
# EQUILÍBRIO OFENSIVO
# ==============================================================================

def calcular_equilibrio(
    fin_h,
    fin_a
):

    total = (
        fin_h + fin_a
    )

    if total <= 0:
        return 0

    maior = max(
        fin_h,
        fin_a
    )

    menor = min(
        fin_h,
        fin_a
    )

    if maior <= 0:
        return 0

    proporcao = (
        menor / maior
    )

    if proporcao >= 0.50:
        return 2

    if proporcao >= 0.30:
        return 1

    return 0


# ==============================================================================
# SCORE 0-100
# ==============================================================================

def calcular_goal_score(
    mercado,
    minuto,
    xg_tot,
    finalizacoes,
    chutes_gol,
    grandes_chances,
    escanteios,
    fin_h,
    fin_a,
    pressao
):

    # --------------------------------------------------------------------------
    # PESOS
    # --------------------------------------------------------------------------

    score_xg = 0
    score_finalizacoes = 0
    score_alvo = 0
    score_chances = 0
    score_escanteios = 0
    score_pressao = 0
    score_aceleracao = 0
    score_equilibrio = 0

    motivos = []

    # --------------------------------------------------------------------------
    # 1. xG RELATIVO AO MINUTO
    # --------------------------------------------------------------------------

    if mercado == '05_HT':

        if minuto <= 18:

            if xg_tot >= 0.65:
                score_xg = 25
            elif xg_tot >= 0.50:
                score_xg = 20
            elif xg_tot >= 0.40:
                score_xg = 15
            elif xg_tot >= 0.30:
                score_xg = 8

        elif minuto <= 22:

            if xg_tot >= 0.80:
                score_xg = 25
            elif xg_tot >= 0.65:
                score_xg = 22
            elif xg_tot >= 0.50:
                score_xg = 18
            elif xg_tot >= 0.40:
                score_xg = 10

        else:

            if xg_tot >= 0.90:
                score_xg = 25
            elif xg_tot >= 0.75:
                score_xg = 22
            elif xg_tot >= 0.60:
                score_xg = 18
            elif xg_tot >= 0.45:
                score_xg = 10

    elif mercado == '15_HT':

        if xg_tot >= 1.20:
            score_xg = 25
        elif xg_tot >= 1.00:
            score_xg = 22
        elif xg_tot >= 0.85:
            score_xg = 18
        elif xg_tot >= 0.70:
            score_xg = 12
        elif xg_tot >= 0.55:
            score_xg = 6

    elif mercado == 'LIMITE_FT':

        if xg_tot >= 2.00:
            score_xg = 25
        elif xg_tot >= 1.70:
            score_xg = 22
        elif xg_tot >= 1.45:
            score_xg = 19
        elif xg_tot >= 1.20:
            score_xg = 14
        elif xg_tot >= 1.00:
            score_xg = 8

    # --------------------------------------------------------------------------
    # 2. FINALIZAÇÕES — PESO 15
    # --------------------------------------------------------------------------

    if mercado == '05_HT':

        if finalizacoes >= 12:
            score_finalizacoes = 15
        elif finalizacoes >= 10:
            score_finalizacoes = 13
        elif finalizacoes >= 8:
            score_finalizacoes = 10
        elif finalizacoes >= 6:
            score_finalizacoes = 7
        elif finalizacoes >= 4:
            score_finalizacoes = 3

    elif mercado == '15_HT':

        if finalizacoes >= 12:
            score_finalizacoes = 15
        elif finalizacoes >= 10:
            score_finalizacoes = 13
        elif finalizacoes >= 8:
            score_finalizacoes = 10
        elif finalizacoes >= 6:
            score_finalizacoes = 7

    else:

        if finalizacoes >= 20:
            score_finalizacoes = 15
        elif finalizacoes >= 17:
            score_finalizacoes = 13
        elif finalizacoes >= 14:
            score_finalizacoes = 11
        elif finalizacoes >= 11:
            score_finalizacoes = 8
        elif finalizacoes >= 9:
            score_finalizacoes = 5

    # --------------------------------------------------------------------------
    # 3. CHUTES NO ALVO — PESO 15
    # --------------------------------------------------------------------------

    if chutes_gol >= 6:
        score_alvo = 15
    elif chutes_gol >= 5:
        score_alvo = 14
    elif chutes_gol >= 4:
        score_alvo = 12
    elif chutes_gol >= 3:
        score_alvo = 9
    elif chutes_gol >= 2:
        score_alvo = 6
    elif chutes_gol >= 1:
        score_alvo = 2

    # --------------------------------------------------------------------------
    # 4. GRANDES CHANCES — PESO 15
    # --------------------------------------------------------------------------

    if grandes_chances >= 3:
        score_chances = 15
    elif grandes_chances >= 2:
        score_chances = 13
    elif grandes_chances >= 1:
        score_chances = 8

    # --------------------------------------------------------------------------
    # 5. ESCANTEIOS — PESO 5
    # --------------------------------------------------------------------------

    if escanteios >= 7:
        score_escanteios = 5
    elif escanteios >= 5:
        score_escanteios = 4
    elif escanteios >= 3:
        score_escanteios = 3
    elif escanteios >= 2:
        score_escanteios = 1

    # --------------------------------------------------------------------------
    # 6. PRESSÃO — PESO 10
    # --------------------------------------------------------------------------

    pressao_recente = pressao.get(
        'recente',
        0
    )

    pressao_pico = pressao.get(
        'pico',
        0
    )

    if (
        pressao_recente >= 50
        or pressao_pico >= 65
    ):
        score_pressao = 10

    elif (
        pressao_recente >= 40
        or pressao_pico >= 55
    ):
        score_pressao = 8

    elif (
        pressao_recente >= 30
        or pressao_pico >= 45
    ):
        score_pressao = 6

    elif (
        pressao_recente >= 20
        or pressao_pico >= 30
    ):
        score_pressao = 3

    # --------------------------------------------------------------------------
    # 7. ACELERAÇÃO — PESO 5
    # --------------------------------------------------------------------------

    aceleracao = pressao.get(
        'aceleracao',
        0
    )

    if aceleracao >= 15:
        score_aceleracao = 5

    elif aceleracao >= 10:
        score_aceleracao = 4

    elif aceleracao >= 5:
        score_aceleracao = 3

    elif aceleracao >= 2:
        score_aceleracao = 1

    # --------------------------------------------------------------------------
    # 8. EQUILÍBRIO — PESO 10
    # --------------------------------------------------------------------------

    equilibrio = calcular_equilibrio(
        fin_h,
        fin_a
    )

    if equilibrio >= 2:
        score_equilibrio = 10

    elif equilibrio == 1:
        score_equilibrio = 5

    # --------------------------------------------------------------------------
    # SCORE BRUTO
    # --------------------------------------------------------------------------

    score = (
        score_xg
        + score_finalizacoes
        + score_alvo
        + score_chances
        + score_escanteios
        + score_pressao
        + score_aceleracao
        + score_equilibrio
    )

    score = max(
        0,
        min(
            100,
            int(score)
        )
    )

    # ==========================================================================
    # MOTIVOS
    # ==========================================================================

    if score_xg >= 18:
        motivos.append(
            "xG elevado para o minuto"
        )

    elif score_xg >= 12:
        motivos.append(
            "xG consistente para o minuto"
        )

    if chutes_gol >= 5:
        motivos.append(
            "5+ chutes no alvo"
        )

    elif chutes_gol >= 4:
        motivos.append(
            "4 chutes no alvo"
        )

    elif chutes_gol >= 3:
        motivos.append(
            "3 chutes no alvo"
        )

    if grandes_chances >= 2:
        motivos.append(
            "2+ grandes chances"
        )

    elif grandes_chances == 1:
        motivos.append(
            "grande chance criada"
        )

    if aceleracao >= 10:
        motivos.append(
            "pressão crescente"
        )

    elif aceleracao >= 5:
        motivos.append(
            "pressão ganhando força"
        )

    if fin_h > 0 and fin_a > 0:

        proporcao = (
            min(fin_h, fin_a)
            / max(fin_h, fin_a)
        )

        if proporcao >= 0.50:
            motivos.append(
                "volume ofensivo dos dois lados"
            )

    if finalizacoes >= 10:
        motivos.append(
            "alto volume de finalizações"
        )

    if escanteios >= 5:
        motivos.append(
            "volume alto de escanteios"
        )

    # ==========================================================================
    # CLASSIFICAÇÕES
    # ==========================================================================

    intensidade = classificar_intensidade(
        pressao
    )

    nivel_pressao = classificar_pressao(
        pressao
    )

    qualidade = classificar_qualidade_chances(
        xg_tot,
        grandes_chances,
        chutes_gol,
        finalizacoes
    )

    # ==========================================================================
    # CONFIANÇA
    # ==========================================================================

    confianca = round(
        score / 10,
        1
    )

    return {
        'score': score,
        'confianca': confianca,
        'intensidade': intensidade,
        'pressao': nivel_pressao,
        'qualidade': qualidade,
        'motivos': motivos
    }


# ==============================================================================
# FILTROS DE ENTRADA
# ==============================================================================

def filtro_05_ht(
    minuto,
    xg,
    finalizacoes,
    chutes_gol,
    grandes_chances,
    escanteios,
    score
):

    # Faixa original do bot
    if not (
        15 <= minuto <= 25
    ):
        return False

    # Base mínima
    base = (
        xg >= 0.45
        or chutes_gol >= 2
        or finalizacoes >= 6
        or grandes_chances >= 1
    )

    if not base:
        return False

    # Score avançado
    if score < 72:
        return False

    # Confirmação adicional
    sinais = 0

    if xg >= 0.55:
        sinais += 1

    if chutes_gol >= 2:
        sinais += 1

    if finalizacoes >= 7:
        sinais += 1

    if grandes_chances >= 1:
        sinais += 1

    if escanteios >= 3:
        sinais += 1

    return sinais >= 2


def filtro_15_ht(
    minuto,
    xg,
    finalizacoes,
    chutes_gol,
    grandes_chances,
    escanteios,
    score
):

    if not (
        18 <= minuto <= 28
    ):
        return False

    base = (
        xg >= 0.70
        or chutes_gol >= 3
        or grandes_chances >= 1
        or (
            finalizacoes >= 8
            and escanteios >= 3
        )
    )

    if not base:
        return False

    if score < 75:
        return False

    sinais = 0

    if xg >= 0.80:
        sinais += 1

    if chutes_gol >= 3:
        sinais += 1

    if finalizacoes >= 8:
        sinais += 1

    if grandes_chances >= 1:
        sinais += 1

    if escanteios >= 4:
        sinais += 1

    return sinais >= 2


def filtro_limite_ft(
    minuto,
    xg,
    finalizacoes,
    chutes_gol,
    grandes_chances,
    escanteios,
    score
):

    if not (
        65 <= minuto <= 75
    ):
        return False

    base = (
        xg >= 1.20
        or chutes_gol >= 4
        or grandes_chances >= 2
        or (
            finalizacoes >= 12
            and escanteios >= 5
        )
    )

    if not base:
        return False

    if score < 75:
        return False

    sinais = 0

    if xg >= 1.20:
        sinais += 1

    if chutes_gol >= 4:
        sinais += 1

    if finalizacoes >= 12:
        sinais += 1

    if grandes_chances >= 2:
        sinais += 1

    if escanteios >= 5:
        sinais += 1

    return sinais >= 2


# ==============================================================================
# FORMATAÇÃO DOS MOTIVOS
# ==============================================================================

def formatar_motivos(motivos):

    if not motivos:
        return "• intensidade ofensiva consistente"

    # Remove duplicados preservando ordem
    unicos = []

    for motivo in motivos:

        if motivo not in unicos:
            unicos.append(
                motivo
            )

    return "\n".join(
        f"• {motivo}"
        for motivo in unicos[:5]
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

        event_id = info[
            'event_id'
        ]

        message_id = info[
            'message_id'
        ]

        gols_no_alerta = info[
            'gols_alerta'
        ]

        mercado = info[
            'mercado'
        ]

        msg_original = info[
            'mensagem_original'
        ]

        item_jogo = jogos_dict.get(
            event_id
        )

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
            gols_c + gols_f
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

        # GREEN
        if gols_atuais > gols_no_alerta:

            nova_mensagem = (
                f"{msg_original}\n\n"
                f"✅️✅️✅️"
            )

            editar_alerta(
                message_id,
                nova_mensagem
            )

            chaves_para_remover.append(
                chave_alerta
            )

        # RED
        else:

            if (
                mercado in [
                    '05_HT',
                    '15_HT'
                ]
                and (
                    eh_intervalo
                    or eh_2h
                    or eh_finalizado
                )
            ):

                nova_mensagem = (
                    f"{msg_original}\n\n"
                    f"❌️❌️❌️"
                )

                editar_alerta(
                    message_id,
                    nova_mensagem
                )

                chaves_para_remover.append(
                    chave_alerta
                )

            elif (
                mercado == 'LIMITE_FT'
                and eh_finalizado
            ):

                nova_mensagem = (
                    f"{msg_original}\n\n"
                    f"❌️❌️❌️"
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
# BUSCA DOS JOGOS
# ==============================================================================

def checar_jogos_ao_vivo():

    horario = (
        obter_horario_brasil()
        .strftime('%H:%M:%S')
    )

    print(
        f"[{horario}] "
        f"Faro de Beagle buscando "
        f"partidas no Sofascore..."
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
            str(
                item.get(
                    'id',
                    ''
                )
            ).strip(): item

            for item in jogos

            if item.get('id')
        }

        validar_alertas_enviados(
            jogos_dict
        )

        # ======================================================================
        # PROCESSAMENTO DOS JOGOS
        # ======================================================================

        for item in jogos:

            event_id = str(
                item.get(
                    'id',
                    ''
                )
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
                    f"{nome_pais} - "
                    f"{nome_liga}"
                )

            else:

                liga_formatada = nome_liga

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

            # ------------------------------------------------------------------
            # BLOQUEIO PRORROGAÇÃO/PÊNALTIS
            # ------------------------------------------------------------------

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

            # ==================================================================
            # ESTATÍSTICAS
            # ==================================================================

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

            # Grandes chances
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

            # ==================================================================
            # NORMALIZAÇÃO
            # ==================================================================

            chutes_gol = int(
                cg_tot
            )

            cg_h_int = int(
                cg_h
            )

            cg_a_int = int(
                cg_a
            )

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

            # ==================================================================
            # xG
            # ==================================================================

            xg_tot, xg_h, xg_a = (
                extrair_xg_sofascore(
                    stats
                )
            )

            # ==================================================================
            # PRESSÃO
            # ==================================================================

            pressao = (
                obter_pressao_grafico_sofascore(
                    event_id
                )
            )

            # ==================================================================
            # PRÉ-LIVE
            # ==================================================================

            prelive_dados = (
                obter_prelive_sofascore(
                    event_id
                )
            )

            # ==================================================================
            # 1. OVER 0.5 HT
            # ==================================================================

            if (
                total_gols == 0
                and eh_1h
                and event_id
                not in notificados_05_ht
                and 15 <= minuto_num <= 25
            ):

                dados_score = (
                    calcular_goal_score(
                        '05_HT',
                        minuto_num,
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        grandes_chances,
                        escanteios,
                        fin_h_int,
                        fin_a_int,
                        pressao
                    )
                )

                score = dados_score[
                    'score'
                ]

                aprovado = (
                    filtro_05_ht(
                        minuto_num,
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        grandes_chances,
                        escanteios,
                        score
                    )
                )

                if aprovado:

                    notificados_05_ht.add(
                        event_id
                    )

                    motivos_txt = (
                        formatar_motivos(
                            dados_score[
                                'motivos'
                            ]
                        )
                    )

                    intensidade = (
                        dados_score[
                            'intensidade'
                        ]
                    )

                    nivel_pressao = (
                        dados_score[
                            'pressao'
                        ]
                    )

                    qualidade = (
                        dados_score[
                            'qualidade'
                        ]
                    )

                    confianca = (
                        dados_score[
                            'confianca'
                        ]
                    )

                    mensagem = (

                        f"🐶 *FARO DE BEAGLE*\n"
                        f"🔥 *SINAL +0,5 HT*\n\n"

                        f"{time_casa} x "
                        f"{time_fora}\n"

                        f"⏱️ {minuto_num}' — "
                        f"0x0\n\n"

                        f"📊 *GOAL SCORE: "
                        f"{score}/100*\n\n"

                        f"xG: {xg_tot:.2f}\n"

                        f"Finalizações: "
                        f"{fin_tot}\n"

                        f"No alvo: "
                        f"{chutes_gol}\n"

                        f"Grandes chances: "
                        f"{grandes_chances}\n"

                        f"Escanteios: "
                        f"{escanteios}\n\n"

                        f"📈 Intensidade: "
                        f"*{intensidade}*\n"

                        f"🔥 Pressão: "
                        f"*{nivel_pressao}*\n"

                        f"🎯 Qualidade das chances: "
                        f"*{qualidade}*\n\n"

                        f"🧠 *Motivos:*\n"
                        f"{motivos_txt}\n\n"

                        f"🐶 *FARO:*\n"
                        f"*OVER 0,5 HT*\n\n"

                        f"Confiança: "
                        f"*{confianca:.1f}/10*"
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

            # ==================================================================
            # 2. OVER 1.5 HT
            # ==================================================================

            elif (
                total_gols == 1
                and eh_1h
                and event_id
                not in notificados_15_ht
                and 18 <= minuto_num <= 28
            ):

                dados_score = (
                    calcular_goal_score(
                        '15_HT',
                        minuto_num,
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        grandes_chances,
                        escanteios,
                        fin_h_int,
                        fin_a_int,
                        pressao
                    )
                )

                score = dados_score[
                    'score'
                ]

                aprovado = (
                    filtro_15_ht(
                        minuto_num,
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        grandes_chances,
                        escanteios,
                        score
                    )
                )

                if aprovado:

                    notificados_15_ht.add(
                        event_id
                    )

                    motivos_txt = (
                        formatar_motivos(
                            dados_score[
                                'motivos'
                            ]
                        )
                    )

                    intensidade = (
                        dados_score[
                            'intensidade'
                        ]
                    )

                    nivel_pressao = (
                        dados_score[
                            'pressao'
                        ]
                    )

                    qualidade = (
                        dados_score[
                            'qualidade'
                        ]
                    )

                    confianca = (
                        dados_score[
                            'confianca'
                        ]
                    )

                    mensagem = (

                        f"🐶 *FARO DE BEAGLE*\n"
                        f"🔥 *SINAL +1,5 HT*\n\n"

                        f"{time_casa} x "
                        f"{time_fora}\n"

                        f"⏱️ {minuto_num}' — "
                        f"{gols_c}x{gols_f}\n\n"

                        f"📊 *GOAL SCORE: "
                        f"{score}/100*\n\n"

                        f"xG: {xg_tot:.2f}\n"

                        f"Finalizações: "
                        f"{fin_tot}\n"

                        f"No alvo: "
                        f"{chutes_gol}\n"

                        f"Grandes chances: "
                        f"{grandes_chances}\n"

                        f"Escanteios: "
                        f"{escanteios}\n\n"

                        f"📈 Intensidade: "
                        f"*{intensidade}*\n"

                        f"🔥 Pressão: "
                        f"*{nivel_pressao}*\n"

                        f"🎯 Qualidade das chances: "
                        f"*{qualidade}*\n\n"

                        f"🧠 *Motivos:*\n"
                        f"{motivos_txt}\n\n"

                        f"🐶 *FARO:*\n"
                        f"*OVER 1,5 HT*\n\n"

                        f"Confiança: "
                        f"*{confianca:.1f}/10*"
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

            # ==================================================================
            # 3. OVER LIMITE FT
            # ==================================================================

            elif (
                eh_2h
                and abs(
                    gols_c - gols_f
                ) <= 1
                and total_gols <= 4
                and event_id
                not in notificados_limite_ft
                and 65 <= minuto_num <= 75
            ):

                dados_score = (
                    calcular_goal_score(
                        'LIMITE_FT',
                        minuto_num,
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        grandes_chances,
                        escanteios,
                        fin_h_int,
                        fin_a_int,
                        pressao
                    )
                )

                score = dados_score[
                    'score'
                ]

                aprovado = (
                    filtro_limite_ft(
                        minuto_num,
                        xg_tot,
                        fin_tot,
                        chutes_gol,
                        grandes_chances,
                        escanteios,
                        score
                    )
                )

                if aprovado:

                    notificados_limite_ft.add(
                        event_id
                    )

                    motivos_txt = (
                        formatar_motivos(
                            dados_score[
                                'motivos'
                            ]
                        )
                    )

                    intensidade = (
                        dados_score[
                            'intensidade'
                        ]
                    )

                    nivel_pressao = (
                        dados_score[
                            'pressao'
                        ]
                    )

                    qualidade = (
                        dados_score[
                            'qualidade'
                        ]
                    )

                    confianca = (
                        dados_score[
                            'confianca'
                        ]
                    )

                    proximo_gol = (
                        total_gols + 0.5
                    )

                    mensagem = (

                        f"🐶 *FARO DE BEAGLE*\n"
                        f"🔥 *SINAL LIMITE FT*\n\n"

                        f"{time_casa} x "
                        f"{time_fora}\n"

                        f"⏱️ {minuto_num}' — "
                        f"{gols_c}x{gols_f}\n\n"

                        f"📊 *GOAL SCORE: "
                        f"{score}/100*\n\n"

                        f"xG: {xg_tot:.2f}\n"

                        f"Finalizações: "
                        f"{fin_tot}\n"

                        f"No alvo: "
                        f"{chutes_gol}\n"

                        f"Grandes chances: "
                        f"{grandes_chances}\n"

                        f"Escanteios: "
                        f"{escanteios}\n\n"

                        f"📈 Intensidade: "
                        f"*{intensidade}*\n"

                        f"🔥 Pressão: "
                        f"*{nivel_pressao}*\n"

                        f"🎯 Qualidade das chances: "
                        f"*{qualidade}*\n\n"

                        f"🧠 *Motivos:*\n"
                        f"{motivos_txt}\n\n"

                        f"🐶 *FARO:*\n"
                        f"*OVER LIMITE "
                        f"(+{proximo_gol})*\n\n"

                        f"Confiança: "
                        f"*{confianca:.1f}/10*"
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
            f"Erro na consulta: {e}"
        )


# ==============================================================================
# EXECUÇÃO PRINCIPAL — MANTIDA PARA RAILWAY
# ==============================================================================

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

            hora_atual = (
                agora_br.hour
            )

            if (
                8 <= hora_atual < 24
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

        time.sleep(120)
