import time
import requests
from datetime import datetime
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4'
CHAT_ID = '1865504705'

# Chave gerada via RapidAPI
RAPIDAPI_KEY = '9b7d7f5f312027c13998f1bf28aa506f'
# ==============================================================================

headers_api = {
    'x-rapidapi-key': RAPIDAPI_KEY,
    'x-rapidapi-host': 'api-football-v1.p.rapidapi.com'
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

def obter_estatisticas_fixture(fixture_id):
    """Consulta os dados estatísticos da partida na RapidAPI."""
    url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures/statistics?fixture={fixture_id}"
    try:
        response = requests.get(url, headers=headers_api, timeout=10)
        data = response.json()
        return data.get('response', [])
    except Exception as e:
        print(f"Erro ao buscar estatísticas do jogo {fixture_id}: {e}")
        return []

def extrair_stat(stats_list, stat_name):
    """Soma as estatísticas de ambos os times (Casa + Fora)."""
    total = 0
    for team_stats in stats_list:
        for item in team_stats.get('statistics', []):
            if item.get('type') == stat_name and item.get('value') is not None:
                val = item.get('value')
                if isinstance(val, int):
                    total += val
                elif isinstance(val, str) and val.replace('%', '').isdigit():
                    total += int(val.replace('%', ''))
    return total

def checar_jogos_ao_vivo():
    horario = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario}] Checando partidas ao vivo via RapidAPI (Métrica APM)...")

    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures?live=all"

    try:
        response = requests.get(url, headers=headers_api, timeout=15)
        data = response.json()
        
        if data.get('errors'):
            print(f"[{horario}] Resposta da RapidAPI: {data.get('errors')}")
    except Exception as e:
        print(f"Erro na requisição da RapidAPI: {e}")
        return

    jogos = data.get('response', [])
    print(f"[{horario}] Total de jogos ao vivo localizados: {len(jogos)}")

    if not jogos:
        return

    for item in jogos:
        fixture = item.get('fixture', {})
        fixture_id = fixture.get('id')
        status_short = fixture.get('status', {}).get('short')
        elapsed = fixture.get('status', {}).get('elapsed') or 0

        goals = item.get('goals', {})
        gols_c = goals.get('home') if goals.get('home') is not None else 0
        gols_f = goals.get('away') if goals.get('away') is not None else 0
        total_gols = gols_c + gols_f

        teams = item.get('teams', {})
        time_casa = teams.get('home', {}).get('name', 'Casa')
        time_fora = teams.get('away', {}).get('name', 'Fora')

        league = item.get('league', {})
        nome_liga = league.get('name', '')
        pais_liga = league.get('country', '')

        if fixture_id in jogos_notificados or elapsed == 0:
            continue

        if status_short not in ['1H', '2H']:
            continue

        # ======================================================================
        # CÁLCULO DE PRESSÃO E ATAQUES POR MINUTO (APM)
        # ======================================================================
        if total_gols <= 3:
            stats = obter_estatisticas_fixture(fixture_id)
            if not stats:
                continue

            atq_perigosos = extrair_stat(stats, "Dangerous Attacks")
            chutes_gol = extrair_stat(stats, "Shots on Goal")
            chutes_fora = extrair_stat(stats, "Shots off Goal")
            finalizacoes_totais = chutes_gol + chutes_fora
            escanteios = extrair_stat(stats, "Corner Kicks")

            # Métrica de Pressão: Ataques Perigosos por Minuto (APM)
            apm = round(atq_perigosos / elapsed, 2)

            # --- ESTRATÉGIA 1: OVER 0.5 HT (0x0 + APM >= 1.0) ---
            if total_gols == 0 and status_short == '1H' and elapsed >= 15:
                if apm >= 1.0 and finalizacoes_totais >= 3:
                    mensagem = (
                        f"🚨 *FARO DE BEAGLE: ALTA PRESSÃO HT (OVER 0.5)* 🚨\n\n"
                        f"🏆 *Liga:* {pais_liga} - {nome_liga}\n"
                        f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                        f"⏱️ Tempo: *{elapsed}' min (1º Tempo)*\n\n"
                        f"🔥 *Índice de Pressão (APM):* `{apm}` atq/min\n"
                        f"📊 *Estatísticas da Partida:*\n"
                        f"⚡ *Ataques Perigosos:* `{atq_perigosos}`\n"
                        f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                        f"👞 *Finalizações Totais:* `{finalizacoes_totais}`\n"
                        f"🚩 *Escanteios:* `{escanteios}`\n\n"
                        f"💡 *Ação:* Jogo com alta intensidade. Confira o **Over 0.5 HT**!"
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(fixture_id)

            # --- ESTRATÉGIA 2: OVER 1.5 HT (1x0 ou 0x1 + APM >= 0.9) ---
            elif total_gols == 1 and status_short == '1H' and elapsed >= 20:
                if apm >= 0.9 and finalizacoes_totais >= 4:
                    mensagem = (
                        f"⚡ *FARO DE BEAGLE: PRESSÃO PARA 2º GOL (OVER 1.5 HT)* ⚡\n\n"
                        f"🏆 *Liga:* {pais_liga} - {nome_liga}\n"
                        f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                        f"⏱️ Tempo: *{elapsed}' min (1º Tempo)*\n\n"
                        f"🔥 *Índice de Pressão (APM):* `{apm}` atq/min\n"
                        f"📊 *Estatísticas da Partida:*\n"
                        f"⚡ *Ataques Perigosos:* `{atq_perigosos}`\n"
                        f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                        f"👞 *Finalizações Totais:* `{finalizacoes_totais}`\n\n"
                        f"💡 *Ação:* Ritmo acelerado. Confira a linha de **Over 1.5 HT**!"
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(fixture_id)

            # --- ESTRATÉGIA 3: OVER LIMITE FT (2º Tempo | Diferença <= 1 gol + APM >= 1.1) ---
            elif status_short == '2H' and elapsed >= 65 and abs(gols_c - gols_f) <= 1:
                if apm >= 1.1 and finalizacoes_totais >= 7:
                    proximo_gol = total_gols + 0.5
                    mensagem = (
                        f"🎯 *FARO DE BEAGLE: PRESSÃO RETA FINAL (OVER +{proximo_gol})* 🎯\n\n"
                        f"🏆 *Liga:* {pais_liga} - {nome_liga}\n"
                        f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                        f"⏱️ Tempo: *{elapsed}' min (2º Tempo)*\n\n"
                        f"🔥 *Índice de Pressão (APM):* `{apm}` atq/min\n"
                        f"📊 *Estatísticas da Partida:*\n"
                        f"⚡ *Ataques Perigosos:* `{atq_perigosos}`\n"
                        f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                        f"👞 *Finalizações Totais:* `{finalizacoes_totais}`\n"
                        f"🚩 *Escanteios:* `{escanteios}`\n\n"
                        f"💡 *Ação:* Sufoco na reta final! Confira o **Over Limite (+{proximo_gol})**!"
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(fixture_id)

if __name__ == '__main__':
    horario_inicio = obter_horario_brasil().strftime('%H:%M:%S')
    msg_inicio = (
        f"🐶⚽ *FARO DE BEAGLE (MODO RAPIDAPI)*\n\n"
        f"📡 Conectado via RapidAPI com monitoramento de ataques por minuto (APM).\n"
        f"⏰ [{horario_inicio}]"
    )
    enviar_alerta(msg_inicio)

    while True:
        try:
            agora_br = obter_horario_brasil()
            hora_atual = agora_br.hour

            if 8 <= hora_atual < 20:
                checar_jogos_ao_vivo()
            else:
                horario_formatado = agora_br.strftime('%H:%M:%S')
                print(f"[{horario_formatado}] Bot em repouso fora do horário estipulado (08h às 20h).")

        except Exception as e:
            print(f"Aviso no ciclo principal: {e}")

        # Intervalo: 450 segundos = 7,5 minutos
        time.sleep(450)
