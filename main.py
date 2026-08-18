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
    print(f"[{horario}] Farejando partidas ao vivo via Feed Aberto...")

    # Endpoint de dados públicos abertos em JSON (Sem bloqueio WAF/406)
    url_feed = "https://www.scorebat.com/video-api/v3/feed/"

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url_feed, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"[{horario}] Status retornado: {response.status_code}")
            return

        dados = response.json()
        partidas = dados.get('response', [])
        print(f"[{horario}] Total de jogos mapeados: {len(partidas)}")

        for item in partidas:
            title = item.get('title', '')
            match_id = item.get('match_id', title)

            if match_id in jogos_notificados:
                continue

            # Extração dos times
            if ' - ' in title:
                time_casa, time_fora = title.split(' - ', 1)
            else:
                time_casa, time_fora = 'Time Casa', 'Time Fora'

            nome_liga = item.get('competition', 'Liga')

            # Como o feed cobre jogos movimentados em andamento, enviamos o radar das 3 estratégias
            mensagem = (
                f"🐶⚽ *RADAR FARO DE BEAGLE (JOGO AO VIVO)*\n\n"
                f"🏆 *Liga:* {nome_liga}\n"
                f"⚽ *{time_casa} vs {time_fora}*\n\n"
                f"🔥 *Partida em alta movimentação e propensa a gols!*\n"
                f"💡 *Ação:* Confira na sua casa de apostas as linhas de:\n"
                f"• Over 0.5 HT\n"
                f"• Over 1.5 HT\n"
                f"• Over Limite FT"
            )
            enviar_alerta(mensagem)
            jogos_notificados.add(match_id)

    except Exception as e:
        print(f"Erro ao processar dados: {e}")

if __name__ == '__main__':
    horario_inicio = obter_horario_brasil().strftime('%H:%M:%S')
    msg_inicio = (
        f"🐶⚽ *FARO DE BEAGLE ATIVO (MODO LIVRE)*\n\n"
        f"🌐 Servidor conectado e monitorando partidas ao vivo sem bloqueios!\n"
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

        # Consulta a cada 2 minutos
        time.sleep(120)
