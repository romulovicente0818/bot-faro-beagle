import time
import requests
from datetime import datetime
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4'
CHAT_ID = '1865504705'

# Sua chave gratuita da Football-Data.org inserida abaixo
FOOTBALL_DATA_KEY = '4c9ad930407d4b95b283becaea48fa25'
# ==============================================================================

headers_api = {
    'X-Auth-Token': FOOTBALL_DATA_KEY
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

def checar_jogos_ao_vivo():
    horario = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario}] Checando partidas ao vivo via Football-Data.org...")

    url = "https://api.football-data.org/v4/matches?status=IN_PLAY"

    try:
        response = requests.get(url, headers=headers_api, timeout=15)
        
        if response.status_code != 200:
            print(f"[{horario}] Status HTTP retornado: {response.status_code}")
            return

        dados = response.json()
        jogos = dados.get('matches', [])
        print(f"[{horario}] Total de jogos ao vivo localizados: {len(jogos)}")

        for item in jogos:
            match_id = item.get('id')
            if match_id in jogos_notificados:
                continue

            time_casa = item.get('homeTeam', {}).get('name', 'Casa')
            time_fora = item.get('awayTeam', {}).get('name', 'Fora')
            nome_liga = item.get('competition', {}).get('name', 'Liga')

            full_time = item.get('score', {}).get('fullTime', {})
            gols_c = full_time.get('home', 0) if full_time.get('home') is not None else 0
            gols_f = full_time.get('away', 0) if full_time.get('away') is not None else 0
            total_gols = gols_c + gols_f

            half_time = item.get('score', {}).get('halfTime', {})
            tem_placar_ht = half_time.get('home') is not None
            
            eh_primeiro_tempo = not tem_placar_ht
            eh_segundo_tempo = tem_placar_ht

            # 1. ESTRATÉGIA: OVER 0.5 HT (Placar 0x0 no 1º Tempo)
            if total_gols == 0 and eh_primeiro_tempo:
                mensagem = (
                    f"🚨 *RADAR FOOTBALL-DATA: OVER 0.5 HT (0x0)* 🚨\n\n"
                    f"🏆 *Liga:* {nome_liga}\n"
                    f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                    f"⏱️ Status: *1º Tempo em andamento*\n\n"
                    f"🔥 *Jogo em andamento no 1º Tempo!*\n"
                    f"💡 Confira a cotação do **Over 0.5 HT** na sua casa de apostas."
                )
                enviar_alerta(mensagem)
                jogos_notificados.add(match_id)

            # 2. ESTRATÉGIA: OVER 1.5 HT (1x0 ou 0x1 no 1º Tempo)
            elif total_gols == 1 and eh_primeiro_tempo:
                mensagem = (
                    f"⚡ *RADAR FOOTBALL-DATA: OVER 1.5 HT (2º GOL)* ⚡\n\n"
                    f"🏆 *Liga:* {nome_liga}\n"
                    f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                    f"⏱️ Status: *1º Tempo em andamento*\n\n"
                    f"🔥 *Primeiro gol marcado cedo!*\n"
                    f"💡 Confira a linha de **Over 1.5 HT** para buscar o próximo gol."
                )
                enviar_alerta(mensagem)
                jogos_notificados.add(match_id)

            # 3. ESTRATÉGIA: OVER LIMITE FT (2º Tempo | Diferença <= 1 gol)
            elif eh_segundo_tempo and abs(gols_c - gols_f) <= 1 and total_gols <= 4:
                proximo_gol = total_gols + 0.5
                mensagem = (
                    f"🎯 *RADAR FOOTBALL-DATA: OVER LIMITE FT (+{proximo_gol})* 🎯\n\n"
                    f"🏆 *Liga:* {nome_liga}\n"
                    f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                    f"⏱️ Status: *2º Tempo em andamento*\n\n"
                    f"🔥 *Placar parelho na reta final!*\n"
                    f"💡 Confira a linha de **Over Limite (+{proximo_gol} Gols)**."
                )
                enviar_alerta(mensagem)
                jogos_notificados.add(match_id)

    except Exception as e:
        print(f"Erro ao consultar Football-Data.org: {e}")

if __name__ == '__main__':
    horario_inicio = obter_horario_brasil().strftime('%H:%M:%S')
    msg_inicio = (
        f"🐶⚽ *FARO DE BEAGLE ATIVO (FOOTBALL-DATA)*\n\n"
        f"🌐 Conectado à API da Football-Data.org sem bloqueios de IP!\n"
        f"📋 *Estratégias:* Over 0.5 HT, Over 1.5 HT e Over Limite FT.\n"
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
                print(f"[{horario_formatado}] Bot em repouso fora do horário (08h às 20h).")

        except Exception as e:
            print(f"Aviso no ciclo principal: {e}")

        # Consulta a cada 3 minutos
        time.sleep(180)
