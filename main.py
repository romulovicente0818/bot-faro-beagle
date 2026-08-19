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
    ' youth', 'youth ', 'juniors', 'junior', 'reserve', 'reserves',
    'academy', 'proliga', 'liga pro', 'cup u', 'league u',
    'trophy u', 'championship u',

    # Feminino
    'women', 'feminino', 'femeni', "women's", 'female', ' w ',

    # Ligas menores / amadoras
    'amateur', 'amador', 'regionaliga', 'oberliga', 'landesliga',
    'district', 'county', 'regional league', 'non-league',
    'primera c', 'primera d', 'tercera'
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


# ==============================================================================
# PRESSÃO DO GRÁFICO
# ==============================================================================

def obter_pressao_grafico_sofascore(event_id):

    url = f"https://api.sofascore.com/api/v1/event/{event_id}/graph"

    try:
        res = scraper.get(url, timeout=10)

        if res.status_code != 200:
            return {
                'pico': 0,
                'media': 0,
                'recente': 0,
                'aceleracao': 0,
                'direcao': 0,
                'texto': ''
            }

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

        valores = []

        for p in points:
            try:
                valores.append(float(p.get('value', 0)))
            except Exception:
                valores.append(0)

        ultimos = valores[-10:] if len(valores) >= 10 else valores
        metade = max(1, len(ultimos) // 2)

        primeira = ultimos[:metade]
        segunda = ultimos[metade:]

        media_abs = sum(abs(x) for x in ultimos) / len(ultimos)
        recente_abs = sum(abs(x) for x in segunda) / len(segunda)

        pico = max(abs(x) for x in ultimos)

        media_primeira = (
            sum(abs(x) for x in primeira) / len(primeira)
            if primeira else 0
        )

        aceleracao = recente_abs - media_primeira

        # Direção:
        # positivo = pressão Casa
        # negativo = pressão Fora
        direcao = sum(segunda) / len(segunda) if segunda else 0

        texto = (
            f"🔥 *Pressão:* Pico `{pico:.0f}` | "
            f"Média `{media_abs:.1f}` | "
            f"Recente `{recente_abs:.1f}`"
        )

        return {
            'pico': pico,
            'media': media_abs,
            'recente': recente_abs,
            'aceleracao': aceleracao,
            'direcao': direcao,
            'texto': texto + "\n"
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


# ==============================================================================
# EXTRAÇÃO DE ESTATÍSTICAS
# ==============================================================================

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

    xg_total, xg_home, xg_away = extrair_stat_sofascore(
        stats_data,
        'Expected goals'
    )

    if xg_total > 0:
        return xg_total, xg_home, xg_away

    return extrair_stat_sofascore(
        stats_data,
        'Expected goals (xG)'
    )


# ==============================================================================
# VALIDAÇÃO DE PARTIDA
# ==============================================================================

def eh_partida_valida(nome_liga, time_casa, time_fora):

    texto_completo = (
        f" {nome_liga} {time_casa} {time_fora} "
    ).lower()

    for termo in TERMOS_IGNORADOS:

        if termo in texto_completo:
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
            and time_data.get('currentPeriodStartTimestamp')
        ):

            now_ts = int(time.time())
            start_ts = time_data.get(
                'currentPeriodStartTimestamp'
            )

            m_calc = (now_ts - start_ts) // 60

            if eh_2h:
                m_calc += 45

            if 1 <= m_calc <= 90:
                minuto = m_calc

    if minuto:

        if eh_1h and minuto <= 45:
            return f"{minuto}' do 1º tempo", minuto

        elif eh_2h and 45 <= minuto <= 90:
            return f"{minuto}' do 2º tempo", minuto

    return None, None


# ==============================================================================
# FUNÇÕES AUXILIARES DOS FILTROS
# ==============================================================================

def limitar(valor, minimo=0, maximo=1):

    return max(minimo, min(maximo, valor))


def calcular_intensidade(
    xg,
    finalizacoes,
    chutes_gol,
    escanteios,
    grandes_chances
):

    pontos = 0

    if xg >= 0.90:
        pontos += 3
    elif xg >= 0.70:
        pontos += 2
    elif xg >=
