import time
import cloudscraper
from datetime import datetime
import zoneinfo
import os

# ==============================================================================
# CONFIGURAÇÕES
# ==============================================================================

# IMPORTANTE:
# Gere um NOVO token no BotFather, pois o token anterior foi exposto.
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4)
CHAT_ID = os.getenv("CHAT_ID", "1865504705")

# Intervalo padrão entre consultas.
# A estrutura de utilização continua igual: basta executar este arquivo.
INTERVALO_NORMAL = 120
INTERVALO_ALERTA = 60

# Score mínimo para gerar alerta
SCORE_ALERTA_FORTE = 75

# Score mínimo para sinal premium
SCORE_PREMIUM = 85

TERMOS_IGNORADOS = [
    # Categorias de Base
    'u15', 'u16', 'u17', 'u18', 'u19', 'u20', 'u21', 'u22', 'u23',
    'sub-15', 'sub-16', 'sub-17', 'sub-18', 'sub-19', 'sub-20',
    'sub-21', 'sub-22', 'sub-23',
    'sub15', 'sub16', 'sub17', 'sub18', 'sub19', 'sub20',
    'sub21', 'sub22', 'sub23',
    ' youth', 'youth ', 'juniors', 'junior',
    'reserve', 'reserves', 'academy',
    'proliga', 'liga pro', 'cup u', 'league u',
    'trophy u', 'championship u',

    # Feminino
    'women', 'feminino', 'femeni', 'women\'s', 'female', ' w ',

    # Ligas menores
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

# Evita alertas duplicados
notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()

# Alertas aguardando validação
alertas_pendentes = {}

# Cache simples para evitar excesso de consultas
cache_dados = {}


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


# ==============================================================================
# SOFASCORE
# ==============================================================================

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
                    'casa': 0,
                    'fora': 0,
                    'tendencia': 'NEUTRA',
                    'aceleracao': 0
                }

            pontos = points[-12:]

            valores_casa = []
            valores_fora = []

            for p in pontos:

                valor = p.get('value', 0)

                try:
                    valor = float(valor)
                except Exception:
                    valor = 0

                # IMPORTANTE:
                # Não usamos abs().
                # O sinal identifica qual equipe está pressionando.
                if valor >= 0:
                    valores_casa.append(valor)
                    valores_fora.append(0)
                else:
                    valores_casa.append(0)
                    valores_fora.append(abs(valor))

            media_casa = sum(valores_casa) / len(valores_casa)
            media_fora = sum(valores_fora) / len(valores_fora)

            pico = max(
                max(valores_casa),
                max(valores_fora)
            )

            # Últimos pontos para identificar aceleração
            metade = max(1, len(pontos) // 2)

            primeira_casa = sum(valores_casa[:metade]) / max(1, len(valores_casa[:metade]))
            segunda_casa = sum(valores_casa[metade:]) / max(1, len(valores_casa[metade:]))

            primeira_fora = sum(valores_fora[:metade]) / max(1, len(valores_fora[:metade]))
            segunda_fora = sum(valores_fora[metade:]) / max(1, len(valores_fora[metade:]))

            aceleracao_casa = segunda_casa - primeira_casa
            aceleracao_fora = segunda_fora - primeira_fora

            if media_casa > media_fora * 1.25:
                tendencia = 'CASA'

            elif media_fora > media_casa * 1.25:
                tendencia = 'FORA'

            else:
                tendencia = 'EQUILIBRADA'

            aceleracao = max(
                aceleracao_casa,
                aceleracao_fora
            )

            return {
                'pico': round(pico, 1),
                'media': round(max(media_casa, media_fora), 1),
                'casa': round(media_casa, 1),
                'fora': round(media_fora, 1),
                'tendencia': tendencia,
                'aceleracao': round(aceleracao, 1)
            }

    except Exception:
        pass

    return {
        'pico': 0,
        'media': 0,
        'casa': 0,
        'fora': 0,
        'tendencia': 'NEUTRA',
        'aceleracao': 0
    }


# ==============================================================================
# EXTRAÇÃO DE ESTATÍSTICAS
# ==============================================================================

def encontrar_periodo(stats_data, periodo):

    if not stats_data:
        return None

    for bloco in stats_data:

        if bloco.get('period') == periodo:
            return bloco

    return None


def extrair_stat_periodo(stats_data, item_name, periodo='ALL'):

    bloco = encontrar_periodo(stats_data, periodo)

    if not bloco:
        return 0, 0, 0

    for group in bloco.get('groups', []):

        for item in group.get('statisticsItems', []):

            if item.get('name') == item_name:

                home_raw = str(item.get('home', '0')).replace('%', '')
                away_raw = str(item.get('away', '0')).replace('%', '')

                try:

                    home = float(home_raw)
                    away = float(away_raw)

                    return home + away, home, away

                except ValueError:
                    return 0, 0, 0

    return 0, 0, 0


def extrair_stat_sofascore(stats_data, item_name):

    return extrair_stat_periodo(
        stats_data,
        item_name,
        'ALL'
    )


def extrair_xg_sofascore(stats_data, periodo='ALL'):

    xg = extrair_stat_periodo(
        stats_data,
        'Expected goals',
        periodo
    )

    if xg[0] > 0:
        return xg

    return extrair_stat_periodo(
        stats_data,
        'Expected goals (xG)',
        periodo
    )


def extrair_grandes_chances(stats_data, periodo='ALL'):

    nomes = [
        'Big chances',
        'Big chances created'
    ]

    for nome in nomes:

        valor = extrair_stat_periodo(
            stats_data,
            nome,
            periodo
        )

        if valor[0] > 0:
            return valor

    return 0, 0, 0


# ==============================================================================
# VALIDAÇÃO DA PARTIDA
# ==============================================================================

def eh_partida_valida(nome_liga, time_casa, time_fora):

    texto = f" {nome_liga} {time_casa} {time_fora} ".lower()

    for termo in TERMOS_IGNORADOS:

        if termo in texto:
            return False

    return True


# ==============================================================================
# MINUTAGEM
# ==============================================================================

def extrair_minutagem_e_numero(item, eh_1h, eh_2h):

    status_desc = str(
        item.get('status', {}).get('description', '')
    ).lower().strip()

    status_type = str(
        item.get('status', {}).get('type', '')
    ).lower().strip()

    termos_prorrogacao = [
        'extra',
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

        if isinstance(time_data, dict):

            inicio = time_data.get(
                'currentPeriodStartTimestamp'
            )

            if inicio:

                agora = int(time.time())

                minuto_calculado = (
                    agora - int(inicio)
                ) // 60

                if eh_2h:
                    minuto_calculado += 45

                if 1 <= minuto_calculado <= 90:
                    minuto = minuto_calculado

    if minuto:

        if eh_1h and minuto <= 45:
            return f"{minuto}' do 1º tempo", minuto

        if eh_2h and 45 <= minuto <= 90:
            return f"{minuto}' do 2º tempo", minuto

    return None, None


# ==============================================================================
# NORMALIZAÇÃO
# ==============================================================================

def limitar(valor, minimo=0, maximo=100):

    return max(
        minimo,
        min(maximo, valor)
    )


def percentual(valor, referencia):

    if referencia <= 0:
        return 0

    return limitar(
        (valor / referencia) * 100
    )


# ==============================================================================
# ANÁLISE DE INTENSIDADE
# ==============================================================================

def analisar_intensidade(
    minuto,
    finalizacoes,
    chutes_alvo,
    grandes_chances,
    xg,
    escanteios
):

    score = 0

    # xG
    if minuto <= 20:

        if xg >= 0.70:
            score += 30
        elif xg >= 0.50:
            score += 24
        elif xg >= 0.35:
            score += 17

    elif minuto <= 30:

        if xg >= 0.95:
            score += 30
        elif xg >= 0.70:
            score += 24
        elif xg >= 0.50:
            score += 17

    else:

        if xg >= 1.20:
            score += 30
        elif xg >= 0.90:
            score += 24
        elif xg >= 0.65:
            score += 17

    # Chutes no alvo
    if chutes_alvo >= 5:
        score += 22
    elif chutes_alvo >= 4:
        score += 18
    elif chutes_alvo >= 3:
        score += 14
    elif chutes_alvo >= 2:
        score += 9

    # Finalizações
    if finalizacoes >= 12:
        score += 16
    elif finalizacoes >= 9:
        score += 13
    elif finalizacoes >= 7:
        score += 10
    elif finalizacoes >= 5:
        score += 6

    # Grandes chances
    if grandes_chances >= 3:
        score += 20
    elif grandes_chances >= 2:
        score += 16
    elif grandes_chances >= 1:
        score += 9

    # Escanteios
    if escanteios >= 7:
        score += 8
    elif escanteios >= 5:
        score += 6
    elif escanteios >= 3:
        score += 4

    return limitar(score)


# ==============================================================================
# SCORE DE PRESSÃO
# ==============================================================================

def calcular_score_pressao(pressao):

    score = 0

    pico = pressao.get('pico', 0)
    media = pressao.get('media', 0)
    aceleracao = pressao.get('aceleracao', 0)

    if pico >= 70:
        score += 30
    elif pico >= 55:
        score += 24
    elif pico >= 40:
        score += 17
    elif pico >= 30:
        score += 10

    if media >= 55:
        score += 25
    elif media >= 40:
        score += 19
    elif media >= 30:
        score += 12

    if aceleracao >= 20:
        score += 25
    elif aceleracao >= 10:
        score += 18
    elif aceleracao >= 5:
        score += 10

    if pressao.get('tendencia') in ['CASA', 'FORA']:
        score += 10

    return limitar(score)


# ==============================================================================
# CONTEXTO DO PLACAR
# ==============================================================================

def calcular_contexto_placar(
    gols_c,
    gols_f,
    minuto,
    mercado
):

    total = gols_c + gols_f
    diferenca = abs(gols_c - gols_f)

    score = 50

    # --------------------------------------------------------------------------
    # HT
    # --------------------------------------------------------------------------

    if mercado == '05_HT':

        if total == 0:
            score += 15

        if diferenca == 0:
            score += 10

        if minuto >= 30:
            score -= 5

    elif mercado == '15_HT':

        if total == 1:
            score += 18

        if diferenca == 1:
            score += 10

        if minuto >= 30:
            score -= 5

    # --------------------------------------------------------------------------
    # FT
    # --------------------------------------------------------------------------

    elif mercado == 'LIMITE_FT':

        if diferenca == 0:
            score += 18

        elif diferenca == 1:
            score += 10

        elif diferenca == 2:
            score += 3

        elif diferenca >= 3:
            score -= 15

        if total >= 4:
            score -= 5

        # Último terço costuma ficar mais interessante
        if minuto >= 75:
            score += 5

    return limitar(score)


# ==============================================================================
# FILTRO DE JOGO MORTO
# ==============================================================================

def jogo_morto(
    minuto,
    xg,
    finalizacoes,
    chutes_alvo,
    grandes_chances,
    pressao_score
):

    # Não considera morto se já existem grandes chances.
    if grandes_chances >= 2:
        return False

    # Pouquíssima produção ofensiva
    if minuto >= 20:

        if (
            xg < 0.30 and
            finalizacoes < 5 and
            chutes_alvo < 2 and
            pressao_score < 30
        ):
            return True

    if minuto >= 35:

        if (
            xg < 0.45 and
            finalizacoes < 7 and
            chutes_alvo < 2 and
            grandes_chances == 0 and
            pressao_score < 35
        ):
            return True

    if minuto >= 65:

        if (
            xg < 0.70 and
            finalizacoes < 8 and
            chutes_alvo < 2 and
            grandes_chances == 0 and
            pressao_score < 35
        ):
            return True

    return False


# ==============================================================================
# SCORE +0,5 HT
# ==============================================================================

def score_over_05_ht(
    minuto,
    xg,
    finalizacoes,
    chutes_alvo,
    grandes_chances,
    escanteios,
    pressao_score,
    contexto
):

    score = 0

    # xG
    if xg >= 1.00:
        score += 27
    elif xg >= 0.75:
        score += 23
    elif xg >= 0.55:
        score += 19
    elif xg >= 0.40:
        score += 14
    elif xg >= 0.30:
        score += 8

    # Chutes no alvo
    if chutes_alvo >= 5:
        score += 18
    elif chutes_alvo >= 4:
        score += 15
    elif chutes_alvo >= 3:
        score += 12
    elif chutes_alvo >= 2:
        score += 8

    # Grandes chances
    if grandes_chances >= 3:
        score += 20
    elif grandes_chances >= 2:
        score += 17
    elif grandes_chances >= 1:
        score += 9

    # Volume
    if finalizacoes >= 12:
        score += 12
    elif finalizacoes >= 9:
        score += 10
    elif finalizacoes >= 7:
        score += 8
    elif finalizacoes >= 5:
        score += 5

    # Escanteios
    if escanteios >= 6:
        score += 5
    elif escanteios >= 4:
        score += 3

    # Pressão
    score += int(pressao_score * 0.10)

    # Contexto
    score += int((contexto - 50) * 0.08)

    # Quanto mais perto do intervalo, mais exigente
    if minuto >= 35 and xg < 0.60:
        score -= 8

    return limitar(score)


# ==============================================================================
# SCORE +1,5 HT
# ==============================================================================

def score_over_15_ht(
    minuto,
    xg,
    finalizacoes,
    chutes_alvo,
    grandes_chances,
    escanteios,
    pressao_score,
    contexto
):

    score = 0

    # Para o segundo gol, exigência maior.
    if xg >= 1.40:
        score += 28
    elif xg >= 1.10:
        score += 24
    elif xg >= 0.90:
        score += 19
    elif xg >= 0.70:
        score += 13
    elif xg >= 0.55:
        score += 7

    if chutes_alvo >= 6:
        score += 18
    elif chutes_alvo >= 5:
        score += 15
    elif chutes_alvo >= 4:
        score += 12
    elif chutes_alvo >= 3:
        score += 8

    if grandes_chances >= 3:
        score += 22
    elif grandes_chances >= 2:
        score += 18
    elif grandes_chances >= 1:
        score += 10

    if finalizacoes >= 14:
        score += 12
    elif finalizacoes >= 11:
        score += 10
    elif finalizacoes >= 8:
        score += 7

    if escanteios >= 7:
        score += 5
    elif escanteios >= 5:
        score += 3

    score += int(pressao_score * 0.12)

    score += int((contexto - 50) * 0.10)

    if minuto >= 35 and xg < 0.90:
        score -= 10

    return limitar(score)


# ==============================================================================
# SCORE GOL LIMITE FT
# ==============================================================================

def score_limite_ft(
    minuto,
    xg,
    finalizacoes,
    chutes_alvo,
    grandes_chances,
    escanteios,
    pressao_score,
    contexto
):

    score = 0

    # xG acumulado
    if xg >= 2.20:
        score += 27
    elif xg >= 1.80:
        score += 24
    elif xg >= 1.40:
        score += 20
    elif xg >= 1.10:
        score += 15
    elif xg >= 0.85:
        score += 9

    # Chutes no alvo
    if chutes_alvo >= 8:
        score += 18
    elif chutes_alvo >= 6:
        score += 15
    elif chutes_alvo >= 4:
        score += 11
    elif chutes_alvo >= 3:
        score += 7

    # Grandes chances
    if grandes_chances >= 4:
        score += 20
    elif grandes_chances >= 3:
        score += 17
    elif grandes_chances >= 2:
        score += 13
    elif grandes_chances >= 1:
        score += 7

    # Volume
    if finalizacoes >= 18:
        score += 12
    elif finalizacoes >= 14:
        score += 10
    elif finalizacoes >= 10:
        score += 7
    elif finalizacoes >= 8:
        score += 4

    # Escanteios
    if escanteios >= 9:
        score += 5
    elif escanteios >= 7:
        score += 4
    elif escanteios >= 5:
        score += 2

    # Pressão tem bastante importância no FT
    score += int(pressao_score * 0.15)

    # Contexto
    score += int((contexto - 50) * 0.15)

    # Aos 80+ precisa haver produção real
    if minuto >= 80:

        if xg < 1.10 and chutes_alvo < 4 and grandes_chances < 2:
            score -= 12

    return limitar(score)


# ==============================================================================
# CLASSIFICAÇÃO
# ==============================================================================

def classificacao_score(score):

    if score >= 85:
        return "🔥 PREMIUM"

    if score >= 75:
        return "🟢 FORTE"

    if score >= 68:
        return "🟡 OBSERVAÇÃO"

    return "🔴 FRACO"


def confianca_score(score):

    return round(
        5 + (score / 20),
        1
    )


# ==============================================================================
# RESUMO DO SCORE
# ==============================================================================

def gerar_linha_score(score):

    classe = classificacao_score(score)
    confianca = confianca_score(score)

    return (
        f"🎯 *Goal Score:* `{score}/100` {classe}\n"
        f"⭐ *Confiança:* `{confianca}/10`\n"
    )


# ==============================================================================
# ALERTA — VALIDAÇÃO
# ==============================================================================

def validar_alertas_enviados(jogos_dict):

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
        ).get('current', 0)

        gols_f = item_jogo.get(
            'awayScore', {}
        ).get('current', 0)

        gols_atuais = gols_c + gols_f

        status_desc = str(
            item_jogo.get('status', {}).get('description', '')
        ).lower()

        time_status = str(
            item_jogo.get('status', {}).get('type', '')
        ).lower()

        eh_intervalo = (
            'halftime' in status_desc or
            'ht' in status_desc or
            time_status == 'halftime'
        )

        eh_2h = (
            '2nd' in status_desc or
            time_status == '2nd'
        )

        eh_finalizado = (
            time_status == 'finished' or
            'ended' in status_desc or
            'ft' in status_desc or
            'extra' in status_desc
        )

        # ----------------------------------------------------------------------
        # GREEN
        # ----------------------------------------------------------------------

        if gols_atuais > gols_no_alerta:

            nova_mensagem = (
                f"{msg_original}\n\n"
                f"✅️✅️✅️ *GREEN*"
            )

            editar_alerta(
                message_id,
                nova_mensagem
            )

            chaves_para_remover.append(chave_alerta)

        # ----------------------------------------------------------------------
        # RED HT
        # ----------------------------------------------------------------------

        else:

            if mercado in ['05_HT', '15_HT']:

                if eh_intervalo or eh_2h or eh_finalizado:

                    nova_mensagem = (
                        f"{msg_original}\n\n"
                        f"❌️❌️❌️ *RED*"
                    )

                    editar_alerta(
                        message_id,
                        nova_mensagem
                    )

                    chaves_para_remover.append(chave_alerta)

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

                    chaves_para_remover.append(chave_alerta)

    for chave in chaves_para_remover:

        alertas_pendentes.pop(
            chave,
            None
        )


# ==============================================================================
# CONSULTA PRINCIPAL
# ==============================================================================

def checar_jogos_ao_vivo():

    horario = obter_horario_brasil().strftime('%H:%M:%S')

    print(
        f"[{horario}] "
        f"Faro de Beagle analisando partidas..."
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

            return False

        dados = response.json()

        jogos = dados.get(
            'events',
            []
        )

        print(
            f"[{horario}] "
            f"Partidas ao vivo: {len(jogos)}"
        )

        jogos_dict = {
            str(item.get('id', '')).strip(): item
            for item in jogos
            if item.get('id')
        }

        validar_alertas_enviados(
            jogos_dict
        )

        houve_alerta = False

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
                nome_pais and
                nome_pais.lower()
                not in nome_liga.lower()
            ):
                liga_formatada = (
                    f"{nome_pais} - {nome_liga}"
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

            # --------------------------------------------------------------
            # Prorrogação
            # --------------------------------------------------------------

            if any(
                term in status_desc or
                term in time_status

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

            total_gols = gols_c + gols_f

            eh_1h = (
                time_status == 'inprogress' and
                '1st' in status_desc
            )

            eh_2h = (
                time_status == 'inprogress' and
                '2nd' in status_desc
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

            # ==============================================================
            # ESTATÍSTICAS
            # ==============================================================

            stats = obter_estatisticas_sofascore(
                event_id
            )

            # ALL
            cg_tot, cg_h, cg_a = extrair_stat_sofascore(
                stats,
                'Shots on target'
            )

            cf_tot, cf_h, cf_a = extrair_stat_sofascore(
                stats,
                'Shots off target'
            )

            esc_tot, esc_h, esc_a = extrair_stat_sofascore(
                stats,
                'Corner kicks'
            )

            xg_tot, xg_h, xg_a = extrair_xg_sofascore(
                stats,
                'ALL'
            )

            bc_tot, bc_h, bc_a = extrair_grandes_chances(
                stats,
                'ALL'
            )

            # --------------------------------------------------------------
            # Período relevante
            # --------------------------------------------------------------

            periodo_relevante = '1ST' if eh_1h else '2ND'

            xg_periodo, _, _ = extrair_xg_sofascore(
                stats,
                periodo_relevante
            )

            bc_periodo, _, _ = extrair_grandes_chances(
                stats,
                periodo_relevante
            )

            sot_periodo, _, _ = extrair_stat_periodo(
                stats,
                'Shots on target',
                periodo_relevante
            )

            # --------------------------------------------------------------
            # Conversões
            # --------------------------------------------------------------

            chutes_gol = int(cg_tot)

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
                bc_tot
            )

            # ==============================================================
            # PRESSÃO
            # ==============================================================

            pressao = obter_pressao_grafico_sofascore(
                event_id
            )

            pressao_score = calcular_score_pressao(
                pressao
            )

            # ==============================================================
            # CONTEXTO
            # ==============================================================

            contexto_05 = calcular_contexto_placar(
                gols_c,
                gols_f,
                minuto_num,
                '05_HT'
            )

            contexto_15 = calcular_contexto_placar(
                gols_c,
                gols_f,
                minuto_num,
                '15_HT'
            )

            contexto_ft = calcular_contexto_placar(
                gols_c,
                gols_f,
                minuto_num,
                'LIMITE_FT'
            )

            # ==============================================================
            # INTENSIDADE
            # ==============================================================

            intensidade = analisar_intensidade(
                minuto_num,
                fin_tot,
                chutes_gol,
                grandes_chances,
                xg_tot,
                escanteios
            )

            # ==============================================================
            # SCORES
            # ==============================================================

            score_05 = score_over_05_ht(
                minuto_num,
                xg_tot,
                fin_tot,
                chutes_gol,
                grandes_chances,
                escanteios,
                pressao_score,
                contexto_05
            )

            score_15 = score_over_15_ht(
                minuto_num,
                xg_tot,
                fin_tot,
                chutes_gol,
                grandes_chances,
                escanteios,
                pressao_score,
                contexto_15
            )

            score_ft = score_limite_ft(
                minuto_num,
                xg_tot,
                fin_tot,
                chutes_gol,
                grandes_chances,
                escanteios,
                pressao_score,
                contexto_ft
            )

            # ==============================================================
            # JOGO MORTO
            # ==============================================================

            jogo_sem_intensidade = jogo_morto(
                minuto_num,
                xg_tot,
                fin_tot,
                chutes_gol,
                grandes_chances,
                pressao_score
            )

            if jogo_sem_intensidade:

                print(
                    f"[{horario}] "
                    f"{time_casa} x {time_fora} "
                    f"→ jogo morto"
                )

                continue

            # ==============================================================
            # TEXTO ESTATÍSTICO
            # ==============================================================

            linha_xg = ""

            if xg_tot > 0:

                linha_xg = (
                    f"📈 *xG:* `{xg_tot:.2f}` "
                    f"_({time_casa} "
                    f"{xg_h:.2f} | "
                    f"{xg_a:.2f} "
                    f"{time_fora})_\n"
                )

            linha_xg_periodo = ""

            if xg_periodo > 0:

                nome_periodo = (
                    "1º tempo"
                    if eh_1h
                    else
                    "2º tempo"
                )

                linha_xg_periodo = (
                    f"📊 *xG {nome_periodo}:* "
                    f"`{xg_periodo:.2f}`\n"
                )

            linha_pressao = (
                f"🔥 *Pressão:* "
                f"`{pressao_score}/100` "
                f"({pressao['tendencia']})\n"
            )

            if pressao['aceleracao'] > 0:

                linha_pressao += (
                    f"📈 *Aceleração:* "
                    f"`+{pressao['aceleracao']:.1f}`\n"
                )

            bloco_estatisticas = (

                f"{linha_xg}"

                f"{linha_xg_periodo}"

                f"🎯 *Finalizações:* "
                f"`{fin_tot}` "
                f"_({fin_h_int}x{fin_a_int})_\n"

                f"🥅 *No alvo:* "
                f"`{chutes_gol}` "
                f"_({cg_h_int}x{cg_a_int})_\n"

                f"💥 *Grandes chances:* "
                f"`{grandes_chances}`\n"

                f"🚩 *Escanteios:* "
                f"`{escanteios}` "
                f"_({esc_h_int}x{esc_a_int})_\n"

                f"{linha_pressao}"

                f"⚡ *Intensidade:* "
                f"`{intensidade}/100`\n"
            )

            # ==============================================================
            # 1 — OVER 0.5 HT
            # ==============================================================

            if (
                total_gols == 0 and
                eh_1h and
                15 <= minuto_num <= 35
            ):

                score_final = (
                    int(score_05 * 0.70) +
                    int(intensidade * 0.15) +
                    int(pressao_score * 0.15)
                )

                score_final = limitar(
                    score_final
                )

                if (
                    score_final >= SCORE_ALERTA_FORTE and
                    event_id not in notificados_05_ht
                ):

                    notificados_05_ht.add(
                        event_id
                    )

                    houve_alerta = True

                    classe = classificacao_score(
                        score_final
                    )

                    mensagem = (

                        f"🚨 *FARO DE BEAGLE — "
                        f"OVER 0.5 HT* 🚨\n\n"

                        f"🏆 *Liga:* "
                        f"{liga_formatada}\n"

                        f"⚽ *{time_casa} "
                        f"{gols_c} x "
                        f"{gols_f} "
                        f"{time_fora}*\n"

                        f"⏱️ *{minutagem}*\n\n"

                        f"📊 *ANÁLISE AO VIVO*\n"

                        f"{bloco_estatisticas}\n"

                        f"🎯 *GOAL SCORE:* "
                        f"`{score_final}/100` "
                        f"{classe}\n"

                        f"⭐ *Confiança:* "
                        f"`{confianca_score(score_final)}/10`\n\n"

                        f"🐶 *FARO:* "
                        f"OVER 0.5 HT"
                    )

                    msg_id = enviar_alerta(
                        mensagem
                    )

                    if msg_id:

                        alertas_pendentes[
                            f"{event_id}_05_HT"
                        ] = {

                            'event_id': event_id,

                            'message_id': msg_id,

                            'gols_alerta': total_gols,

                            'mercado': '05_HT',

                            'mensagem_original': mensagem
                        }

            # ==============================================================
            # 2 — OVER 1.5 HT
            # ==============================================================

            elif (
                total_gols == 1 and
                eh_1h and
                18 <= minuto_num <= 32
            ):

                # Aumenta importância do xG do período.
                score_ajustado = score_15

                if xg_periodo >= 0.80:
                    score_ajustado += 6

                if bc_periodo >= 2:
                    score_ajustado += 5

                if sot_periodo >= 4:
                    score_ajustado += 4

                score_final = (
                    int(score_ajustado * 0.70) +
                    int(intensidade * 0.12) +
                    int(pressao_score * 0.18)
                )

                score_final = limitar(
                    score_final
                )

                if (
                    score_final >= SCORE_ALERTA_FORTE and
                    event_id not in notificados_15_ht
                ):

                    notificados_15_ht.add(
                        event_id
                    )

                    houve_alerta = True

                    classe = classificacao_score(
                        score_final
                    )

                    mensagem = (

                        f"⚡ *FARO DE BEAGLE — "
                        f"OVER 1.5 HT* ⚡\n\n"

                        f"🏆 *Liga:* "
                        f"{liga_formatada}\n"

                        f"⚽ *{time_casa} "
                        f"{gols_c} x "
                        f"{gols_f} "
                        f"{time_fora}*\n"

                        f"⏱️ *{minutagem}*\n\n"

                        f"📊 *ANÁLISE AO VIVO*\n"

                        f"{bloco_estatisticas}\n"

                        f"🎯 *GOAL SCORE:* "
                        f"`{score_final}/100` "
                        f"{classe}\n"

                        f"⭐ *Confiança:* "
                        f"`{confianca_score(score_final)}/10`\n\n"

                        f"🐶 *FARO:* "
                        f"OVER 1.5 HT — 2º GOL"
                    )

                    msg_id = enviar_alerta(
                        mensagem
                    )

                    if msg_id:

                        alertas_pendentes[
                            f"{event_id}_15_HT"
                        ] = {

                            'event_id': event_id,

                            'message_id': msg_id,

                            'gols_alerta': total_gols,

                            'mercado': '15_HT',

                            'mensagem_original': mensagem
                        }

            # ==============================================================
            # 3 — GOL LIMITE FT
            # ==============================================================

            elif (
                eh_2h and
                65 <= minuto_num <= 82 and
                total_gols <= 5
            ):

                score_final = score_ft

                # Jogo empatado recebe pequeno bônus.
                if gols_c == gols_f:
                    score_final += 5

                # Diferença de apenas um gol:
                elif abs(gols_c - gols_f) == 1:
                    score_final += 3

                # Reação ofensiva muito forte.
                if (
                    pressao['aceleracao'] >= 15 and
                    grandes_chances >= 2
                ):
                    score_final += 5

                score_final = limitar(
                    score_final
                )

                if (
                    score_final >= SCORE_ALERTA_FORTE and
                    event_id not in notificados_limite_ft
                ):

                    notificados_limite_ft.add(
                        event_id
                    )

                    houve_alerta = True

                    classe = classificacao_score(
                        score_final
                    )

                    proximo_gol = (
                        total_gols + 0.5
                    )

                    mensagem = (

                        f"🎯 *FARO DE BEAGLE — "
                        f"GOL LIMITE FT* 🎯\n\n"

                        f"🏆 *Liga:* "
                        f"{liga_formatada}\n"

                        f"⚽ *{time_casa} "
                        f"{gols_c} x "
                        f"{gols_f} "
                        f"{time_fora}*\n"

                        f"⏱️ *{minutagem}*\n\n"

                        f"📊 *ANÁLISE AO VIVO*\n"

                        f"{bloco_estatisticas}\n"

                        f"🎯 *GOAL SCORE:* "
                        f"`{score_final}/100` "
                        f"{classe}\n"

                        f"⭐ *Confiança:* "
                        f"`{confianca_score(score_final)}/10`\n\n"

                        f"🐶 *FARO:* "
                        f"OVER LIMITE "
                        f"+{proximo_gol} FT"
                    )

                    msg_id = enviar_alerta(
                        mensagem
                    )

                    if msg_id:

                        alertas_pendentes[
                            f"{event_id}_LIMITE_FT"
                        ] = {

                            'event_id': event_id,

                            'message_id': msg_id,

                            'gols_alerta': total_gols,

                            'mercado': 'LIMITE_FT',

                            'mensagem_original': mensagem
                        }

        return houve_alerta

    except Exception as e:

        print(
            f"Erro na consulta: {e}"
        )

        return False


# ==============================================================================
# EXECUÇÃO
# ==============================================================================

if __name__ == '__main__':

    horario_inicio = (
        obter_horario_brasil()
        .strftime('%H:%M:%S')
    )

    print(
        f"[{horario_inicio}] "
        f"Faro de Beagle V2 iniciado."
    )

    print(
        "🐶 Motor: Goal Score + "
        "Pressão + Contexto + Intensidade"
    )

    while True:

        try:

            agora_br = (
                obter_horario_brasil()
            )

            hora_atual = agora_br.hour

            if 8 <= hora_atual < 24:

                houve_alerta = (
                    checar_jogos_ao_vivo()
                )

                if houve_alerta:

                    time.sleep(
                        INTERVALO_ALERTA
                    )

                else:

                    time.sleep(
                        INTERVALO_NORMAL
                    )

            else:

                horario_formatado = (
                    agora_br
                    .strftime('%H:%M:%S')
                )

                print(
                    f"[{horario_formatado}] "
                    f"Bot em repouso "
                    f"fora do horário "
                    f"(08h às 00h)."
                )

                time.sleep(240)

        except Exception as e:

            print(
                f"Aviso no ciclo principal: {e}"
            )

            time.sleep(60)


