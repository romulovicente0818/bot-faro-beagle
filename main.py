import time
import requests

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4'
CHAT_ID = '1865504705'
API_SPORTS_KEY = '27c8ac6d4f3de1f3938be3ffcfa100be'
# ==============================================================================

headers_api = {
    'x-apisports-key': API_SPORTS_KEY
}

jogos_notificados = set()

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

def extrair_valor_stat(lista_stats, nome_stat):
    for stat in lista_stats:
        if stat['type'] == nome_stat:
            val = stat['value']
            if val is None:
                return 0
            if isinstance(val, str) and '%' in val:
                return int(val.replace('%', ''))
            return val
    return 0

def checar_jogos_ao_vivo():
    horario = time.strftime('%H:%M:%S')
    print(f"[{horario}] Checando jogos ao vivo na API...")
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    
    try:
        response = requests.get(url, headers=headers_api, timeout=15)
        data = response.json()
    except Exception as e:
        print(f"Erro ao conectar na API: {e}")
        return

    jogos = data.get('response', [])
    print(f"[{horario}] Total de jogos ao vivo na API: {len(jogos)}")
    
    if not jogos:
        return

    for item in jogos:
        fixture_id = item['fixture']['id']
        tempo_minuto = item['fixture']['status']['elapsed']
        status = item['fixture']['status']['short']

        time_casa = item['teams']['home']['name']
        time_fora = item['teams']['away']['name']
        gols_casa = item['goals']['home']
        gols_fora = item['goals']['away']

        nome_liga = item['league']['name']
        pais_liga = item['league']['country']

        if tempo_minuto is None:
            continue

        if fixture_id in jogos_notificados:
            continue

        gols_c = gols_casa if gols_casa is not None else 0
        gols_f = gols_fora if gols_fora is not None else 0
        total_gols = gols_c + gols_f

        # ======================================================================
        # REGRAS DE 1º TEMPO (1H)
        # ======================================================================
        if status == '1H':
            # ESTRATÉGIA 1: JOGO 0 x 0 (Over 0.5 HT) -> 12' a 32'
            if total_gols == 0 and 12 <= tempo_minuto <= 32:
                url_stats = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
                try:
                    resp_stats = requests.get(url_stats, headers=headers_api, timeout=15).json()
                except Exception:
                    continue

                if resp_stats.get('response') and len(resp_stats['response']) == 2:
                    stats_casa = resp_stats['response'][0]['statistics']
                    stats_fora = resp_stats['response'][1]['statistics']

                    posse_casa = extrair_valor_stat(stats_casa, 'Ball Possession')
                    posse_fora = extrair_valor_stat(stats_fora, 'Ball Possession')

                    atq_perigosos = extrair_valor_stat(stats_casa, 'Dangerous Attacks') + extrair_valor_stat(stats_fora, 'Dangerous Attacks')
                    appm = round(atq_perigosos / tempo_minuto, 2)

                    chutes_gol = extrair_valor_stat(stats_casa, 'Shots on Goal') + extrair_valor_stat(stats_fora, 'Shots on Goal')
                    chutes_fora = extrair_valor_stat(stats_casa, 'Shots off Goal') + extrair_valor_stat(stats_fora, 'Shots off Goal')
                    chutes_bloq = extrair_valor_stat(stats_casa, 'Blocked Shots') + extrair_valor_stat(stats_fora, 'Blocked Shots')
                    finalizacoes = chutes_gol + chutes_fora + chutes_bloq
                    escanteios = extrair_valor_stat(stats_casa, 'Corner Kicks') + extrair_valor_stat(stats_fora, 'Corner Kicks')

                    if appm >= 1.0 and finalizacoes >= 3 and chutes_gol >= 1 and (posse_casa >= 55 or posse_fora >= 55):
                        mensagem = (
                            f"⚡ *ALERTA DE PRESSAO (GOL HT)* ⚡\n\n"
                            f"🏆 *Liga:* {pais_liga} - {nome_liga}\n"
                            f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                            f"⏱️ Tempo: *{tempo_minuto}' min*\n\n"
                            f"📊 *Estatísticas Ao Vivo:*\n"
                            f"• APPM (Ataques/min): *{appm}*\n"
                            f"• Finalizações Totais: *{finalizacoes}*\n"
                            f"• Chutes no Gol: *{chutes_gol}*\n"
                            f"• Escanteios: *{escanteios}*\n\n"
                            f"🔥 *Forte tendência de gol no 1º tempo!*"
                        )
                        enviar_alerta(mensagem)
                        jogos_notificados.add(fixture_id)

            # ESTRATÉGIA 2: JOGO 1 x 0 ou 0 x 1 (Over 1.5 HT) -> 15' a 35'
            elif total_gols == 1 and 15 <= tempo_minuto <= 35:
                url_stats = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
                try:
                    resp_stats = requests.get(url_stats, headers=headers_api, timeout=15).json()
                except Exception:
                    continue

                if resp_stats.get('response') and len(resp_stats['response']) == 2:
                    stats_casa = resp_stats['response'][0]['statistics']
                    stats_fora = resp_stats['response'][1]['statistics']

                    posse_casa = extrair_valor_stat(stats_casa, 'Ball Possession')
                    posse_fora = extrair_valor_stat(stats_fora, 'Ball Possession')

                    atq_perigosos = extrair_valor_stat(stats_casa, 'Dangerous Attacks') + extrair_valor_stat(stats_fora, 'Dangerous Attacks')
                    appm = round(atq_perigosos / tempo_minuto, 2)

                    chutes_gol = extrair_valor_stat(stats_casa, 'Shots on Goal') + extrair_valor_stat(stats_fora, 'Shots on Goal')
                    chutes_fora = extrair_valor_stat(stats_casa, 'Shots off Goal') + extrair_valor_stat(stats_fora, 'Shots off Goal')
                    chutes_bloq = extrair_valor_stat(stats_casa, 'Blocked Shots') + extrair_valor_stat(stats_fora, 'Blocked Shots')
                    finalizacoes = chutes_gol + chutes_fora + chutes_bloq
                    escanteios = extrair_valor_stat(stats_casa, 'Corner Kicks') + extrair_valor_stat(stats_fora, 'Corner Kicks')

                    if appm >= 1.1 and finalizacoes >= 4 and chutes_gol >= 2 and (posse_casa >= 55 or posse_fora >= 55):
                        mensagem = (
                            f"⚡ *ALERTA DE REAÇÃO (OVER 1.5 HT)* ⚡\n\n"
                            f"🏆 *Liga:* {pais_liga} - {nome_liga}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo: *{tempo_minuto}' min*\n\n"
                            f"📊 *Estatísticas Ao Vivo:*\n"
                            f"• APPM (Ataques/min): *{appm}*\n"
                            f"• Finalizações Totais: *{finalizacoes}*\n"
                            f"• Chutes no Gol: *{chutes_gol}*\n"
                            f"• Escanteios: *{escanteios}*\n\n"
                            f"🔥 *Jogo movimentado com alta pressão por mais um gol!*"
                        )
                        enviar_alerta(mensagem)
                        jogos_notificados.add(fixture_id)

        # ======================================================================
        # REGRAS DE 2º TEMPO (2H) -> ESTRATÉGIA OVER LIMITE FT
        # ======================================================================
        elif status == '2H':
            # Janela de 65' a 78' minutos | Placar parelho (diferença <= 1 gol)
            if 65 <= tempo_minuto <= 78 and abs(gols_c - gols_f) <= 1:
                url_stats = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
                try:
                    resp_stats = requests.get(url_stats, headers=headers_api, timeout=15).json()
                except Exception:
                    continue

                if resp_stats.get('response') and len(resp_stats['response']) == 2:
                    stats_casa = resp_stats['response'][0]['statistics']
                    stats_fora = resp_stats['response'][1]['statistics']

                    posse_casa = extrair_valor_stat(stats_casa, 'Ball Possession')
                    posse_fora = extrair_valor_stat(stats_fora, 'Ball Possession')

                    atq_perigosos = extrair_valor_stat(stats_casa, 'Dangerous Attacks') + extrair_valor_stat(stats_fora, 'Dangerous Attacks')
                    appm = round(atq_perigosos / tempo_minuto, 2)

                    chutes_gol = extrair_valor_stat(stats_casa, 'Shots on Goal') + extrair_valor_stat(stats_fora, 'Shots on Goal')
                    chutes_fora = extrair_valor_stat(stats_casa, 'Shots off Goal') + extrair_valor_stat(stats_fora, 'Shots off Goal')
                    chutes_bloq = extrair_valor_stat(stats_casa, 'Blocked Shots') + extrair_valor_stat(stats_fora, 'Blocked Shots')
                    finalizacoes = chutes_gol + chutes_fora + chutes_bloq
                    escanteios = extrair_valor_stat(stats_casa, 'Corner Kicks') + extrair_valor_stat(stats_fora, 'Corner Kicks')

                    # Filtro para 2º tempo: Pressão alta acumulada
                    if appm >= 1.0 and finalizacoes >= 8 and chutes_gol >= 3 and (posse_casa >= 55 or posse_fora >= 55):
                        proximo_gol = total_gols + 0.5
                        mensagem = (
                            f"🎯 *ALERTA OVER LIMITE FT (+{proximo_gol} GOLS)* 🎯\n\n"
                            f"🏆 *Liga:* {pais_liga} - {nome_liga}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo: *{tempo_minuto}' min*\n\n"
                            f"📊 *Estatísticas do Jogo:*\n"
                            f"• APPM (Ataques/min): *{appm}*\n"
                            f"• Finalizações Totais: *{finalizacoes}*\n"
                            f"• Chutes no Gol: *{chutes_gol}*\n"
                            f"• Escanteios: *{escanteios}*\n\n"
                            f"🔥 *Alta pressão no 2º tempo! Excelente janela para Over Limite.*"
                        )
                        enviar_alerta(mensagem)
                        jogos_notificados.add(fixture_id)

if __name__ == '__main__':
    while True:
        try:
            checar_jogos_ao_vivo()
        except Exception as e:
            print(f"Aviso no ciclo principal: {e}")
        time.sleep(480)
