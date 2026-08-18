import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4'
CHAT_ID = '1865504705'
# ==============================================================================

jogos_notificados = set()

# Cabeçalhos completos para evitar o erro 406 (Simula navegador real)
headers_scraping = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

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

def raspar_jogos_ao_vivo():
    horario = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario}] Farejando partidas ao vivo via Web Scraping...")

    url_live = "https://www.besoccer.com/livescore"
    
    try:
        response = requests.get(url_live, headers=headers_scraping, timeout=15)
        if response.status_code != 200:
            print(f"[{horario}] Aviso ao acessar o site: Status {response.status_code}")
            return
        
        soup = BeautifulSoup(response.content, 'html.parser')
        partidas = soup.find_all('div', class_='match-link')
        
        print(f"[{horario}] Total de partidas encontradas em campo: {len(partidas)}")

        for match in partidas:
            try:
                match_id = match.get('id', '')
                if not match_id or match_id in jogos_notificados:
                    continue

                status_elem = match.find('span', class_='status')
                status_texto = status_elem.text.strip() if status_elem else ''

                if "'" not in status_texto and '1H' not in status_texto and '2H' not in status_texto:
                    continue

                time_casa = match.find('div', class_='team-name-home').text.strip() if match.find('div', class_='team-name-home') else 'Casa'
                time_fora = match.find('div', class_='team-name-away').text.strip() if match.find('div', class_='team-name-away') else 'Fora'

                placar_casa = match.find('span', class_='r1').text.strip() if match.find('span', class_='r1') else '0'
                placar_fora = match.find('span', class_='r2').text.strip() if match.find('span', class_='r2') else '0'

                gols_c = int(placar_casa) if placar_casa.isdigit() else 0
                gols_f = int(placar_fora) if placar_fora.isdigit() else 0
                total_gols = gols_c + gols_f

                eh_primeiro_tempo = '1H' in status_texto or ("'" in status_texto and int(status_texto.replace("'", "")) <= 45 if status_texto.replace("'", "").isdigit() else True)
                eh_segundo_tempo = '2H' in status_texto or ("'" in status_texto and int(status_texto.replace("'", "")) > 45 if status_texto.replace("'", "").isdigit() else False)

                # ==============================================================
                # 1. OVER 0.5 HT (0x0)
                # ==============================================================
                if total_gols == 0 and eh_primeiro_tempo:
                    mensagem = (
                        f"🚨 *RADAR WEB: OVER 0.5 HT (0x0)* 🚨\n\n"
                        f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                        f"⏱️ Tempo: *{status_texto}*\n\n"
                        f"🔥 *Jogo em andamento no 1º Tempo!*\n"
                        f"💡 Confira a Odd do **Over 0.5 HT** na sua casa de apostas."
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(match_id)

                # ==============================================================
                # 2. OVER 1.5 HT (1x0 ou 0x1)
                # ==============================================================
                elif total_gols == 1 and eh_primeiro_tempo:
                    mensagem = (
                        f"⚡ *RADAR WEB: OVER 1.5 HT (BUSCA PELO 2º GOL)* ⚡\n\n"
                        f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                        f"⏱️ Tempo: *{status_texto}*\n\n"
                        f"🔥 *Jogo aberto com 1 gol no 1º Tempo!*\n"
                        f"💡 Confira a linha de **Over 1.5 HT** para buscar o próximo gol."
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(match_id)

                # ==============================================================
                # 3. OVER LIMITE FT (2º Tempo | Diferença <= 1 gol)
                # ==============================================================
                elif eh_segundo_tempo and abs(gols_c - gols_f) <= 1 and total_gols <= 4:
                    proximo_gol = total_gols + 0.5
                    mensagem = (
                        f"🎯 *RADAR WEB: OVER LIMITE FT (+{proximo_gol} GOLS)* 🎯\n\n"
                        f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                        f"⏱️ Tempo: *{status_texto}*\n\n"
                        f"🔥 *Reta final disputada e placar parelho!*\n"
                        f"💡 Confira a linha de **Over Limite (+{proximo_gol})**."
                    )
                    enviar_alerta(mensagem)
                    jogos_notificados.add(match_id)

            except Exception:
                continue

    except Exception as e:
        print(f"Erro na raspagem de dados: {e}")

if __name__ == '__main__':
    horario_inicio = obter_horario_brasil().strftime('%H:%M:%S')
    msg_inicio = (
        f"🐶⚽ *FARO DE BEAGLE ATIVO (MODO WEB SCRAPING)*\n\n"
        f"🌐 Bot operando sem APIs pagas e sem limites de requisição!\n"
        f"📋 *Estratégias ativas:* Over 0.5 HT, Over 1.5 HT e Over Limite FT.\n"
        f"⏰ [{horario_inicio}]"
    )
    enviar_alerta(msg_inicio)

    while True:
        try:
            agora_br = obter_horario_brasil()
            hora_atual = agora_br.hour

            if 8 <= hora_atual < 20:
                raspar_jogos_ao_vivo()
            else:
                horario_formatado = agora_br.strftime('%H:%M:%S')
                print(f"[{horario_formatado}] Bot em repouso fora do horário estipulado (08h às 20h).")

        except Exception as e:
            print(f"Aviso no ciclo principal: {e}")

        time.sleep(120)
