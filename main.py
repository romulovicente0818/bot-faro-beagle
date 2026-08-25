import time
import cloudscraper
from datetime import datetime
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

# Registros para evitar repetição do mesmo alerta
notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()

# Dicionário de acompanhamento dos alertas enviados para validação do resultado
alertas_pendentes = {}


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
        res = scraper.post(url, json=payload, timeout=10)

        if res.status_code != 200:
            print(f"Erro ao editar mensagem Telegram: {res.status_code} - {res.text[:500]}")
        else:
            dados = res.json()
            if not dados.get('ok', False):
                print(f"Telegram recusou edição da mensagem: {dados}")

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



def obter_incidentes_sofascore(event_id):
    """Busca incidentes do jogo para detectar cartões vermelhos e outros eventos contextuais."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/incidents"
    try:
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            return res.json().get('incidents', [])
    except Exception:
        pass
    return []


def extrair_cartoes_vermelhos(incidentes):
    """Retorna vermelhos diretos/segundos amarelos por lado."""
    vermelhos_casa = 0
    vermelhos_fora = 0

    for inc in incidentes or []:
        tipo = str(inc.get('incidentType', '')).lower()
        classe = str(inc.get('incidentClass', '')).lower()
        is_red = (
            'red' in tipo or 'red' in classe or
            'secondyellow' in classe or 'second yellow' in classe or
            'secondyellow' in tipo or 'second yellow' in tipo
        )
        if not is_red:
            continue

        is_home = inc.get('isHome')
        if is_home is True:
            vermelhos_casa += 1
        elif is_home is False:
            vermelhos_fora += 1

    return vermelhos_casa, vermelhos_fora


def calcular_contexto_proximo_gol(
    mercado,
    gols_c,
    gols_f,
    minuto,
    fin_h,
    fin_a,
    chutes_h,
    chutes_a,
    grandes_h,
    grandes_a,
    pressao,
    vermelhos_casa=0,
    vermelhos_fora=0,
):
    """
    Camada contextual do FARO.

    Não substitui os filtros estatísticos existentes. Ajusta a decisão para
    responder à pergunta: "o contexto atual favorece a busca pelo próximo gol?"

    Importante: no início de temporada NÃO penaliza 0x0 por suposta falta de
    necessidade de resultado. Sem informação confiável de favorito/odds, o
    parâmetro favorito permanece neutro.
    """
    pontos = 0
    motivos = []

    total_gols = gols_c + gols_f
    intensidade = pressao.get('aceleracao', 0)

    # ------------------------------------------------------------------
    # 1) Equipe atrás do placar e produzindo.
    # ------------------------------------------------------------------
    if gols_c > gols_f:
        perdendo_fin = fin_a
        perdendo_alvo = chutes_a
        perdendo_gc = grandes_a
        lado_perdendo = 'fora'
    elif gols_f > gols_c:
        perdendo_fin = fin_h
        perdendo_alvo = chutes_h
        perdendo_gc = grandes_h
        lado_perdendo = 'casa'
    else:
        perdendo_fin = 0
        perdendo_alvo = 0
        perdendo_gc = 0
        lado_perdendo = None

    if lado_perdendo:
        sinais_perdendo = 0
        if perdendo_fin >= 6:
            sinais_perdendo += 1
        if perdendo_alvo >= 2:
            sinais_perdendo += 1
        if perdendo_gc >= 1:
            sinais_perdendo += 1

        if sinais_perdendo >= 2:
            pontos += 2
            motivos.append('equipe atrás do placar produzindo')
        elif sinais_perdendo == 1:
            pontos += 1

    # ------------------------------------------------------------------
    # 2) Jogo empatado com produção dos dois lados.
    # Não presume necessidade extra em 0x0; apenas recompensa jogo aberto.
    # ------------------------------------------------------------------
    if gols_c == gols_f:
        maior_fin = max(fin_h, fin_a)
        menor_fin = min(fin_h, fin_a)
        equilibrio = (menor_fin / maior_fin) if maior_fin > 0 else 0

        if equilibrio >= 0.50 and (chutes_h + chutes_a) >= 4:
            pontos += 1
            motivos.append('empate com produção dos dois lados')

        if (grandes_h + grandes_a) >= 2 and equilibrio >= 0.40:
            pontos += 1

    # ------------------------------------------------------------------
    # 3) Expulsão: superioridade numérica aumenta a relevância do contexto.
    # ------------------------------------------------------------------
    if vermelhos_casa or vermelhos_fora:
        if gols_c == gols_f:
            pontos += 2
            motivos.append('superioridade numérica após expulsão')
        elif gols_c > gols_f and vermelhos_fora:
            pontos += 2
            motivos.append('equipe vencendo em superioridade numérica')
        elif gols_f > gols_c and vermelhos_casa:
            pontos += 2
            motivos.append('equipe vencendo em superioridade numérica')
        else:
            # Mesmo com a equipe atrás tendo um expulso, não damos bônus.
            # Isso evita tratar qualquer cartão vermelho como automaticamente bom.
            pontos -= 1

    # ------------------------------------------------------------------
    # 4) Pressão recente acelerando: confirma que o contexto não está apenas
    # acumulando estatísticas antigas.
    # ------------------------------------------------------------------
    if intensidade >= 8:
        pontos += 2
        motivos.append('pressão recente acelerando')
    elif intensidade >= 4:
        pontos += 1

    # ------------------------------------------------------------------
    # 5) Jogo muito desequilibrado em produção: não é automaticamente ruim,
    # mas exige mais qualidade para evitar que volume de um lado seja confundido
    # com probabilidade de próximo gol.
    # ------------------------------------------------------------------
    maior = max(fin_h, fin_a)
    menor = min(fin_h, fin_a)
    if maior >= 10 and menor / maior < 0.25:
        if (chutes_h + chutes_a) < 4 or (grandes_h + grandes_a) == 0:
            pontos -= 1
            motivos.append('produção muito concentrada em um lado')

    # Limites conservadores: contexto é ajuste, não substituto do filtro.
    if mercado == '05_HT':
        minimo = 0
    elif mercado == '15_HT':
        minimo = 0
    else:
        minimo = 0

    return max(-2, min(4, pontos)), motivos[:3]


def aplicar_contexto_ao_score(
    score,
    mercado,
    gols_c,
    gols_f,
    minuto,
    fin_h,
    fin_a,
    chutes_h,
    chutes_a,
    grandes_h,
    grandes_a,
    pressao,
    vermelhos_casa=0,
    vermelhos_fora=0,
):
    """Aplica o ajuste contextual ao score interno sem alterar a escala exibida."""
    ajuste, motivos_contexto = calcular_contexto_proximo_gol(
        mercado,
        gols_c,
        gols_f,
        minuto,
        fin_h,
        fin_a,
        chutes_h,
        chutes_a,
        grandes_h,
        grandes_a,
        pressao,
        vermelhos_casa,
        vermelhos_fora,
    )
    return score + ajuste, ajuste, motivos_contexto


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


def calcular_confianca_independente(
    mercado,
    minutagem,
    xg_tot,
    fin_tot,
    chutes_gol,
    escanteios,
    grandes_chances,
    fin_h,
    fin_a,
    pressao,
):
    """
    Calcula a CONFIANÇA do alerta de forma independente do GOAL SCORE.

    O Goal Score mede força/volume ofensivo acumulado.
    A Confiança mede a convergência dos sinais para o mercado específico.
    Não utiliza o score interno nem o GOAL SCORE como entrada.
    """

    try:
        minuto = int(str(minutagem).split("'")[0])
    except (ValueError, IndexError):
        minuto = 45

    recente = max(0.0, float(pressao.get('recente', 0)))
    pico = max(0.0, float(pressao.get('pico', 0)))
    aceleracao = float(pressao.get('aceleracao', 0))

    # Limita cada componente entre 0 e 1.
    def saturar(valor, alvo):
        if alvo <= 0:
            return 0.0
        return max(0.0, min(1.0, float(valor) / float(alvo)))

    # Produção dos dois lados: útil como confirmação, mas não obrigatória.
    maior = max(fin_h, fin_a)
    menor = min(fin_h, fin_a)
    equilibrio = (menor / maior) if maior > 0 else 0.0

    if mercado == '05_HT':
        # +0,5 HT: prioridade para qualidade imediata e pressão.
        componentes = [
            (saturar(xg_tot, 0.70), 30),
            (saturar(chutes_gol, 4), 25),
            (saturar(grandes_chances, 2), 20),
            (saturar(recente, 40), 15),
            (saturar(fin_tot, 10), 5),
            (saturar(escanteios, 5), 5),
        ]
        alvos = (xg_tot >= 0.55, chutes_gol >= 3, grandes_chances >= 1,
                 recente >= 30 or pico >= 40)
        minimo_convergencia = 3

    elif mercado == '15_HT':
        # +1,5 HT: exige maior convergência porque ainda falta outro gol.
        componentes = [
            (saturar(xg_tot, 1.00), 30),
            (saturar(chutes_gol, 4), 22),
            (saturar(grandes_chances, 2), 18),
            (saturar(recente, 45), 15),
            (saturar(fin_tot, 11), 5),
            (saturar(escanteios, 5), 5),
            (equilibrio, 5),
        ]
        alvos = (xg_tot >= 0.80, chutes_gol >= 3, grandes_chances >= 1,
                 recente >= 30 or pico >= 40, fin_tot >= 8)
        minimo_convergencia = 3

    else:
        # Limite FT: peso maior para produção acumulada e pressão do 2º tempo.
        componentes = [
            (saturar(xg_tot, 1.70), 28),
            (saturar(chutes_gol, 7), 22),
            (saturar(grandes_chances, 3), 18),
            (saturar(recente, 50), 17),
            (saturar(fin_tot, 18), 8),
            (saturar(escanteios, 8), 4),
            (saturar(max(aceleracao, 0), 12), 3),
        ]
        alvos = (xg_tot >= 1.30, chutes_gol >= 5, grandes_chances >= 2,
                 recente >= 35 or pico >= 50, fin_tot >= 14)
        minimo_convergencia = 3

    base = sum(valor * peso for valor, peso in componentes)

    # Bônus por convergência de sinais. Isso diferencia confiança de volume puro.
    sinais_fortes = sum(1 for sinal in alvos if sinal)
    if sinais_fortes >= 4:
        base += 7
    elif sinais_fortes >= minimo_convergencia:
        base += 4

    # Pressão em aceleração aumenta a confiabilidade; queda forte reduz.
    if aceleracao >= 8:
        base += 4
    elif aceleracao >= 4:
        base += 2
    elif aceleracao <= -8:
        base -= 5
    elif aceleracao <= -4:
        base -= 2

    # Para HT, equilíbrio é uma confirmação extra, não um requisito.
    if mercado in ('05_HT', '15_HT') and equilibrio >= 0.50:
        base += 3

    # Evita confiança artificialmente alta quando os principais sinais estão fracos.
    principais_fracos = (
        xg_tot < (0.35 if mercado == '05_HT' else 0.55 if mercado == '15_HT' else 0.90)
        and chutes_gol < (2 if mercado != 'LIMITE_FT' else 3)
        and grandes_chances == 0
    )
    if principais_fracos:
        base -= 8

    # Pequeno ajuste temporal: dentro da janela do filtro, o ponto mais tardio
    # é ligeiramente mais informativo, sem transformar minuto em score.
    if mercado == '05_HT' and minuto >= 22:
        base += 2
    elif mercado == '15_HT' and minuto >= 25:
        base += 2
    elif mercado == 'LIMITE_FT' and minuto >= 72:
        base += 2

    confianca = max(0.0, min(10.0, base / 10.0))
    return round(confianca, 1)


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
    confianca = calcular_confianca_independente(
        mercado,
        minutagem,
        xg_tot,
        fin_tot,
        chutes_gol,
        escanteios,
        grandes_chances,
        fin_h,
        fin_a,
        pressao,
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
        f'🏆 *Liga:* {liga}\n\n'
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

        # Se o jogo saiu do endpoint /events/live, ele pode ter terminado.
        # Busca o evento individual para validar RED/GREEN no FT.
        if not item_jogo:
            try:
                url_evento = f"https://api.sofascore.com/api/v1/event/{event_id}"
                res_evento = scraper.get(url_evento, timeout=10)
                if res_evento.status_code == 200:
                    item_jogo = res_evento.json().get('event')
            except Exception as e:
                print(f"Erro ao consultar evento {event_id} para validar alerta: {e}")

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

            # CONFIRMAÇÃO DO GOL:
            # Alguns gols aparecem no placar e são anulados logo depois
            # (VAR/falta/impedimento). Antes de marcar GREEN, aguarda
            # alguns segundos e consulta novamente o evento.
            gol_confirmado = True

            try:
                time.sleep(15)
                url_confirmacao = f"https://api.sofascore.com/api/v1/event/{event_id}"
                res_confirmacao = scraper.get(
                    url_confirmacao,
                    timeout=10
                )

                if res_confirmacao.status_code == 200:
                    evento_confirmado = res_confirmacao.json().get('event', {})
                    gols_c_confirmados = evento_confirmado.get(
                        'homeScore', {}
                    ).get(
                        'current',
                        0
                    )
                    gols_f_confirmados = evento_confirmado.get(
                        'awayScore', {}
                    ).get(
                        'current',
                        0
                    )
                    gols_confirmados = gols_c_confirmados + gols_f_confirmados

                    if gols_confirmados <= gols_no_alerta:
                        gol_confirmado = False
                        print(
                            f"Gol possivelmente anulado no evento {event_id}. "
                            f"Placar voltou para {gols_confirmados}. GREEN cancelado."
                        )

            except Exception as e:
                print(
                    f"Aviso ao confirmar gol do evento {event_id}: {e}"
                )

            if gol_confirmado:
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

            # Os incidentes serão consultados somente quando o jogo estiver
            # perto de atingir o filtro de algum mercado. Isso evita uma chamada
            # extra desnecessária para todas as partidas ao vivo.
            vermelhos_casa, vermelhos_fora = 0, 0

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

                    if score >= 8:
                        incidentes = obter_incidentes_sofascore(event_id)
                        vermelhos_casa, vermelhos_fora = extrair_cartoes_vermelhos(incidentes)
                    score, ajuste_contexto, motivos_contexto = aplicar_contexto_ao_score(
                        score, '05_HT', gols_c, gols_f, minuto_num,
                        fin_h_int, fin_a_int, cg_h_int, cg_a_int,
                        int(gc_h), int(gc_a), pressao,
                        vermelhos_casa, vermelhos_fora
                    )
                    motivos.extend(motivos_contexto)
                    aprovado = score >= 10

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

                    if score >= 10:
                        incidentes = obter_incidentes_sofascore(event_id)
                        vermelhos_casa, vermelhos_fora = extrair_cartoes_vermelhos(incidentes)
                    score, ajuste_contexto, motivos_contexto = aplicar_contexto_ao_score(
                        score, '15_HT', gols_c, gols_f, minuto_num,
                        fin_h_int, fin_a_int, cg_h_int, cg_a_int,
                        int(gc_h), int(gc_a), pressao,
                        vermelhos_casa, vermelhos_fora
                    )
                    motivos.extend(motivos_contexto)
                    aprovado = score >= 12

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

                    if score >= 10:
                        incidentes = obter_incidentes_sofascore(event_id)
                        vermelhos_casa, vermelhos_fora = extrair_cartoes_vermelhos(incidentes)
                    score, ajuste_contexto, motivos_contexto = aplicar_contexto_ao_score(
                        score, 'LIMITE_FT', gols_c, gols_f, minuto_num,
                        fin_h_int, fin_a_int, cg_h_int, cg_a_int,
                        int(gc_h), int(gc_a), pressao,
                        vermelhos_casa, vermelhos_fora
                    )
                    motivos.extend(motivos_contexto)
                    aprovado = score >= 12

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

            if 8 <= hora_atual < 24:

                checar_jogos_ao_vivo()

            else:

                horario_formatado = (
                    agora_br.strftime('%H:%M:%S')
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

        time.sleep(240)
