import time
import requests
from datetime import datetime
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4'
CHAT_ID = '1865504705'
# ==============================================================================

headers_sofascore = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Cache-Control': 'no-cache'
}

jogos_notificados = set()

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
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")

def obter_estatisticas_sofascore(event_id):
    """Obtém os dados detalhados da partida no Sofascore."""
    url = f"https://api.sofascore.com/api/v3/event/{event_id}/statistics"
    try:
        res = requests.get(url, headers=headers_sofascore, timeout=10)
        if res.status_code == 200:
            return res.json().get('statistics', [])
    except Exception:
        pass
    return []

def extrair_stat_sofascore(stats_data, group_name, item_name):
    """Extrai estatísticas como Chutes, Ataques e Escanteios."""
    total = 0
    for period in stats_data:
        if period.get('period') == 'ALL':
            for group in period.get('groups', []):
                for item in group.get('items', []):
                    if item.get('name') == item_name:
                        val_home = int(item.get('home', '0').replace('%', '')) if str(item.get('home')).isdigit() else 0
                        val_away = int(item.get('away', '0').replace('%', '')) if str(item.get('away')).isdigit() else 0
                        return val_home + val_away
    return total

def checar_jogos_ao_vivo():
    horario = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario}] Faro de Beagle buscando partidas no Sofascore...")

    url = "https://api.sofascore.com/api/v3/events/live"

    try:
        response = requests.get(url, headers=headers_sofascore, timeout=15)
        if response.status_code != 200:
            print(f"[{horario}] Status retornado: {response.status_code}")
            return

        dados = response.json()
        jogos = dados.get('events', [])
        print(f"[{horario}] Total de partidas ao vivo: {len(jogos)}")

        for item in jogos:
            event_id = item.get('id')
            if event_id in jogos_notificados:
                continue

            # Valida se é futebol
            if item.get('sport', {}).get('name') != 'Football':
                continue

            status_desc = item.get('status', {}).get('description', '')
            time_status = item.get('status', {}).get('type', '')

            time_casa = item.get('homeTeam', {}).get('name', 'Casa')
            time_fora = item.get('awayTeam', {}).get('name', 'Fora')
            nome_liga = item.get('tournament', {}).get('name', 'Liga')

            gols_c = item.get('homeScore', {}).get('current', 0)
            gols_f = item.get('awayScore', {}).get('current', 0)
            total_gols = gols_c + gols_f

            # Identificação de tempo de jogo
            eh_1h = time_status == 'inprogress' and '1st' in status_desc.lower()
            eh_2h = time_status == 'inprogress' and '2nd' in status_desc.lower()

            if not (eh_1h or eh_2h):
                continue

            # Busca estatísticas
            stats = obter_estatisticas_sofascore(event_id)
            if not stats:
                continue

            chutes_gol = extrair_stat_sofascore(stats, 'Shots', 'Shots on target')
            chutes_fora = extrair_stat_sofascore(stats, 'Shots', 'Shots off target')
            finalizacoes = chutes_gol + chutes_fora
            escanteios = extrair_stat_sofascore(stats, 'TVData', 'Corner kicks')

            # Estratégia 1: Over 0.5 HT (0x0)
            if total_gols == 0 and eh_1h:
                if finalizacoes >= 3 or escanteios >= 2:
                    mensagem = (
                        f"🚨 *FARO DE BEAGLE: OVER 0.5 HT (0x0)* 🚨\n\n"
                        f"🏆 *Liga:* {nome_liga}\n"
                        f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                        f"⏱️ Status: *1º Tempo em andamento*\n\n"
                        f"📊 *Estatísticas:*\n"
                        f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                        f"👞 *Finalizações Totais:* `{finalizacoes}`\n"
                        f"🚩 *Escanteios:* `{escanteios}`\n\n"
                        f"💡 Confira a linha de **Over 0.5 HT**!"
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(event_id)

            # Estratégia 2: Over 1.5 HT (1x0 / 0x1)
            elif total_gols == 1 and eh_1h:
                if finalizacoes >= 4:
                    mensagem = (
                        f"⚡ *FARO DE BEAGLE: OVER 1.5 HT (2º GOL)* ⚡\n\n"
                        f"🏆 *Liga:* {nome_liga}\n"
                        f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                        f"⏱️ Status: *1º Tempo em andamento*\n\n"
                        f"📊 *Estatísticas:*\n"
                        f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                        f"👞 *Finalizações Totais:* `{finalizacoes}`\n\n"
                        f"💡 Confira a linha de **Over 1.5 HT**!"
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(event_id)

            # Estratégia 3: Over Limite FT (2º Tempo | Diferença <= 1 gol)
            elif eh_2h and abs(gols_c - gols_f) <= 1 and total_gols <= 4:
                if finalizacoes >= 7:
                    proximo_gol = total_gols + 0.5
                    mensagem = (
                        f"🎯 *FARO DE BEAGLE: OVER LIMITE FT (+{proximo_gol})* 🎯\n\n"
                        f"🏆 *Liga:* {nome_liga}\n"
                        f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                        f"⏱️ Status: *2º Tempo em andamento*\n\n"
                        f"📊 *Estatísticas:*\n"
                        f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                        f"👞 *Finalizações Totais:* `{finalizacoes}`\n"
                        f"🚩 *Escanteios:* `{escanteios}`\n\n"
                        f"💡 Confira a linha de **Over Limite (+{proximo_gol})**!"
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(event_id)

    except Exception as e:
        print(f"Erro na consulta: {e}")

if __name__ == '__main__':
    horario_inicio = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario_inicio}] Faro de Beagle rodando em segundo plano...")

    while True:
        try:
            agora_br = obter_horario_brasil()
            hora_atual = agora_br.hour

            if 8 <= hora_atual < 20:
                checar_jogos_ao_vivo()
            else:
                horario_formatado = agora_br.strftime('%H:%M:%S')
                print(f"[{horario_formatado}] Bot em repouso fora do horário (08h às 20h).")

        except Exception as e:
            print(f"Aviso no ciclo principal: {e}")

        # Consulta a cada 4 minutos
        time.sleep(240)
