import time
import cloudscraper
from datetime import datetime
import zoneinfo

# ==============================================================================
# CONFIGURAÇÕES E CREDENCIAIS
# ==============================================================================
TELEGRAM_TOKEN = '8826311067:AAE5i3mc3Rt7IibVr2Lai2b63vHKCADONX4'
CHAT_ID = '1865504705'

# Filtros contra jogos de base, amadores e femininos
TERMOS_IGNORADOS = [
    # Categorias de Base
    'u15', 'u16', 'u17', 'u18', 'u19', 'u20', 'u21', 'u22', 'u23', 
    'sub-15', 'sub-16', 'sub-17', 'sub-18', 'sub-19', 'sub-20', 'sub-21', 'sub-22', 'sub-23', 
    'sub15', 'sub16', 'sub17', 'sub18', 'sub19', 'sub20', 'sub21', 'sub22', 'sub23',
    ' youth', 'youth ', 'juniors', 'junior', 'reserve', 'reserves', 'academy',
    'proliga', 'liga pro', 'cup u', 'league u', 'trophy u', 'championship u',
    # Feminino
    'women', 'feminino', 'femeni', 'women\'s', 'female', ' w ',
    # Campeonatos Amadores
    'amateur', 'amador', 'regionaliga', 'oberliga', 
    'landesliga', 'district', 'county', 'regional league', 'non-league'
]
# ==============================================================================

scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

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
        scraper.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")

def obter_estatisticas_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    try:
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            return res.json().get('statistics', [])
    except Exception:
        pass
    return []

def extrair_stat_sofascore(stats_data, item_name):
    if not stats_data:
        return 0

    for period in stats_data:
        if period.get('period') == 'ALL':
            for group in period.get('groups', []):
                for item in group.get('statisticsItems', []):
                    if item.get('name') == item_name:
                        home_val = str(item.get('home', '0')).replace('%', '')
                        away_val = str(item.get('away', '0')).replace('%', '')
                        
                        val_home = int(home_val) if home_val.isdigit() else 0
                        val_away = int(away_val) if away_val.isdigit() else 0
                        return val_home + val_away
    return 0

def eh_partida_valida(nome_liga, time_casa, time_fora):
    """Filtra se o nome da liga OU de qualquer time contiver termos de base/feminino/amador."""
    texto_completo = f" {nome_liga} {time_casa} {time_fora} ".lower()
    
    for termo in TERMOS_IGNORADOS:
        if termo in texto_completo:
            return False
    return True

def extrair_minutagem_e_numero(item, eh_1h, eh_2h):
    """Extrai e formata o minuto exato no momento do disparo (ex: 20' do 1º tempo)."""
    status_desc = str(item.get('status', {}).get('description', '')).strip()
    
    minuto = None
    time_data = item.get('time', {})
    
    # Tentativa 1: Leitura direta do relógio da partida em segundos
    if isinstance(time_data, dict) and time_data.get('currentPeriodStartTimestamp'):
        now_ts = int(time.time())
        start_ts = time_data.get('currentPeriodStartTimestamp')
        m_calc = (now_ts - start_ts) // 60
        if eh_2h:
            m_calc += 45
        if 1 <= m_calc <= 120:
            minuto = m_calc

    # Tentativa 2: Extração via descrição do status (Ex: "20'", "45+2'")
    if not minuto and "'" in status_desc:
        min_limpo = status_desc.replace("'", "").split('+')[0]
        if min_limpo.isdigit():
            minuto = int(min_limpo)

    tempo_rotulo = "1º tempo" if eh_1h else "2º tempo" if eh_2h else "tempo"
    texto_formatado = f"{minuto}' do {tempo_rotulo}" if minuto else f"Em andamento ({tempo_rotulo})"

    return texto_formatado, minuto

def checar_jogos_ao_vivo():
    horario = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario}] Faro de Beagle buscando partidas no Sofascore...")

    url = "https://api.sofascore.com/api/v1/sport/football/events/live"

    try:
        response = scraper.get(url, timeout=15)
        if response.status_code != 200:
            print(f"[{horario}] Status retornado: {response.status_code}")
            return

        dados = response.json()
        jogos = dados.get('events', [])
        print(f"[{horario}] Total de partidas ao vivo localizadas: {len(jogos)}")

        for item in jogos:
            event_id = item.get('id')
            if event_id in jogos_notificados:
                continue

            nome_liga = item.get('tournament', {}).get('name', 'Liga')
            time_casa = item.get('homeTeam', {}).get('name', 'Casa')
            time_fora = item.get('awayTeam', {}).get('name', 'Fora')
            
            # FILTRO COMPLETO: Analisa Liga, Time da Casa e Time Visitante
            if not eh_partida_valida(nome_liga, time_casa, time_fora):
                continue

            category = item.get('tournament', {}).get('category', {})
            nome_pais = category.get('name', '')

            if nome_pais and nome_pais.lower() not in nome_liga.lower():
                liga_formatada = f"{nome_pais} - {nome_liga}"
            else:
                liga_formatada = nome_liga

            status_desc = item.get('status', {}).get('description', '')
            time_status = item.get('status', {}).get('type', '')

            gols_c = item.get('homeScore', {}).get('current', 0)
            gols_f = item.get('awayScore', {}).get('current', 0)
            total_gols = gols_c + gols_f

            eh_1h = time_status == 'inprogress' and '1st' in status_desc.lower()
            eh_2h = time_status == 'inprogress' and '2nd' in status_desc.lower()

            if not (eh_1h or eh_2h):
                continue

            # Obtenção do tempo formatado e do número do minuto
            minutagem, minuto_num = extrair_minutagem_e_numero(item, eh_1h, eh_2h)

            if not minuto_num:
                continue

            stats = obter_estatisticas_sofascore(event_id)
            
            chutes_gol = extrair_stat_sofascore(stats, 'Shots on target')
            chutes_fora = extrair_stat_sofascore(stats, 'Shots off target')
            finalizacoes = chutes_gol + chutes_fora
            escanteios = extrair_stat_sofascore(stats, 'Corner kicks')

            if finalizacoes == 0 and escanteios == 0:
                continue

            # ==================================================================
            # 1. OVER 0.5 HT (0x0) -> 15' a 25' do 1º Tempo
            # ==================================================================
            if total_gols == 0 and eh_1h:
                if 15 <= minuto_num <= 25:
                    if finalizacoes >= 3 or escanteios >= 2:
                        mensagem = (
                            f"🚨 *FARO DE BEAGLE: OVER 0.5 HT (0x0)* 🚨\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                            f"👞 *Finalizações Totais:* `{finalizacoes}`\n"
                            f"🚩 *Escanteios:* `{escanteios}`\n\n"
                            f"💡 Confira a linha de **Over 0.5 HT**!"
                        )
                        enviar_alerta(mensagem)
                        jogos_notificados.add(event_id)

            # ==================================================================
            # 2. OVER 1.5 HT (1x0 / 0x1) -> 18' a 28' do 1º Tempo
            # ==================================================================
            elif total_gols == 1 and eh_1h:
                if 18 <= minuto_num <= 28:
                    if finalizacoes >= 4:
                        mensagem = (
                            f"⚡ *FARO DE BEAGLE: OVER 1.5 HT (2º GOL)* ⚡\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                            f"👞 *Finalizações Totais:* `{finalizacoes}`\n\n"
                            f"💡 Confira a linha de **Over 1.5 HT**!"
                        )
                        enviar_alerta(mensagem)
                        jogos_notificados.add(event_id)

            # ==================================================================
            # 3. OVER LIMITE FT -> 65' a 75' do 2º Tempo
            # ==================================================================
            elif eh_2h and abs(gols_c - gols_f) <= 1 and total_gols <= 4:
                if 65 <= minuto_num <= 75:
                    if finalizacoes >= 7:
                        proximo_gol = total_gols + 0.5
                        mensagem = (
                            f"🎯 *FARO DE BEAGLE: OVER LIMITE FT (+{proximo_gol})* 🎯\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
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
    print(f"[{horario_inicio}] Faro de Beagle rodando...")

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

        time.sleep(240)
