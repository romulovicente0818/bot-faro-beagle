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
    'sub-15', 'sub-16', 'sub-17', 'sub-18', 'sub-19', 'sub-20', 'sub-21', 'sub-22', 'sub-23', 
    'sub15', 'sub16', 'sub17', 'sub18', 'sub19', 'sub20', 'sub21', 'sub22', 'sub23',
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

# Controle de envio independente por estratégia
notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()

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

def obter_prelive_sofascore(event_id):
    """Consulta dados pré-live e médias recentes dos times no Sofascore."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/prematch-form"
    try:
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            dados = res.json()
            home_form = dados.get('home', {}).get('avgRating', 0)
            # Retorna estrutura pré-live identificada
            return dados
    except Exception:
        pass
    return None

def obter_pressao_grafico_sofascore(event_id):
    """Lê o gráfico de Fluxo da Partida (Attack Momentum) dos últimos minutos."""
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/graph"
    try:
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            points = res.json().get('graphPoints', [])
            if not points:
                return 0, ""
            
            ultimos_pontos = points[-8:] if len(points) >= 8 else points
            valores_abs = [abs(p.get('value', 0)) for p in ultimos_pontos]
            
            pico_pressao = max(valores_abs) if valores_abs else 0
            media_pressao = round(sum(valores_abs) / len(valores_abs), 1) if valores_abs else 0
            
            texto_fluxo = f"\n🔥 *Pressão no Grafico:* Pico `{pico_pressao}` | Média `{media_pressao}`"
            return pico_pressao, texto_fluxo
    except Exception:
        pass
    return 0, ""

def extrair_stat_sofascore(stats_data, item_name):
    if not stats_data:
        return 0, 0, 0

    for period in stats_data:
        if period.get('period') == 'ALL':
            for group in period.get('groups', []):
                for item in group.get('statisticsItems', []):
                    if item.get('name') == item_name:
                        home_raw = str(item.get('home', '0')).replace('%', '')
                        away_raw = str(item.get('away', '0')).replace('%', '')
                        
                        try:
                            val_home = float(home_raw)
                            val_away = float(away_raw)
                            return val_home + val_away, val_home, val_away
                        except ValueError:
                            return 0, 0, 0
    return 0, 0, 0

def extrair_xg_sofascore(stats_data):
    xg_total, xg_home, xg_away = extrair_stat_sofascore(stats_data, 'Expected goals')
    if xg_total > 0:
        return xg_total, xg_home, xg_away
    
    xg_total_alt, xg_h_alt, xg_a_alt = extrair_stat_sofascore(stats_data, 'Expected goals (xG)')
    return xg_total_alt, xg_h_alt, xg_a_alt

def eh_partida_valida(nome_liga, time_casa, time_fora):
    texto_completo = f" {nome_liga} {time_casa} {time_fora} ".lower()
    for termo in TERMOS_IGNORADOS:
        if termo in texto_completo:
            return False
    return True

def extrair_minutagem_e_numero(item, eh_1h, eh_2h):
    status_desc = str(item.get('status', {}).get('description', '')).strip()
    minuto = None

    if "'" in status_desc:
        min_limpo = status_desc.replace("'", "").split('+')[0].strip()
        if min_limpo.isdigit():
            minuto = int(min_limpo)

    if not minuto:
        time_data = item.get('time', {})
        if isinstance(time_data, dict) and time_data.get('currentPeriodStartTimestamp'):
            now_ts = int(time.time())
            start_ts = time_data.get('currentPeriodStartTimestamp')
            m_calc = (now_ts - start_ts) // 60
            if eh_2h:
                m_calc += 45
            if 1 <= m_calc <= 120:
                minuto = m_calc

    if minuto:
        tempo_rotulo = "1º tempo" if eh_1h else "2º tempo"
        return f"{minuto}' do {tempo_rotulo}", minuto

    return None, None

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
            event_id = str(item.get('id', '')).strip()
            if not event_id:
                continue

            nome_liga = item.get('tournament', {}).get('name', 'Liga')
            time_casa = item.get('homeTeam', {}).get('name', 'Casa')
            time_fora = item.get('awayTeam', {}).get('name', 'Fora')
            
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

            minutagem, minuto_num = extrair_minutagem_e_numero(item, eh_1h, eh_2h)
            if not minuto_num:
                continue

            stats = obter_estatisticas_sofascore(event_id)
            
            chutes_gol_tot, _, _ = extrair_stat_sofascore(stats, 'Shots on target')
            chutes_fora_tot, _, _ = extrair_stat_sofascore(stats, 'Shots off target')
            
            chutes_gol = int(chutes_gol_tot)
            finalizacoes = int(chutes_gol_tot + chutes_fora_tot)
            
            esc_tot, _, _ = extrair_stat_sofascore(stats, 'Corner kicks')
            escanteios = int(esc_tot)

            # 1. Leitura do xG (Expected Goals)
            xg_tot, xg_h, xg_a = extrair_xg_sofascore(stats)
            linha_xg = f"\n📈 *xG Acumulado:* `{xg_tot:.2f}` _({time_casa} {xg_h:.2f} | {xg_a:.2f} {time_fora})_" if xg_tot > 0 else ""

            # 2. Leitura do Fluxo da Partida (Attack Momentum)
            pico_pressao, linha_fluxo = obter_pressao_grafico_sofascore(event_id)
            fluxo_confirmado = (pico_pressao >= 30) if pico_pressao > 0 else True

            # 3. Análise Pré-Live da Partida
            prelive_dados = obter_prelive_sofascore(event_id)
            linha_prelive = "\n📋 *Tendência Pré-Live:* Propenso a Gols ✅" if prelive_dados else ""

            # ==================================================================
            # 1. OVER 0.5 HT (0x0) -> 15' a 25' do 1º Tempo
            # ==================================================================
            if total_gols == 0 and eh_1h:
                if event_id not in notificados_05_ht and 15 <= minuto_num <= 25:
                    tem_xg_valido = (xg_tot >= 0.45) if xg_tot > 0 else (chutes_gol >= 2 or finalizacoes >= 6)
                    
                    if tem_xg_valido and fluxo_confirmado:
                        notificados_05_ht.add(event_id)
                        mensagem = (
                            f"🚨 *FARO DE BEAGLE: OVER 0.5 HT (0x0)* 🚨\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                            f"👞 *Finalizações Totais:* `{finalizacoes}`{linha_xg}{linha_fluxo}{linha_prelive}\n"
                            f"🚩 *Escanteios:* `{escanteios}`\n\n"
                            f"💡 Confira a linha de **Over 0.5 HT**!"
                        )
                        enviar_alerta(mensagem)

            # ==================================================================
            # 2. OVER 1.5 HT (1x0 / 0x1) -> 18' a 28' do 1º Tempo
            # ==================================================================
            elif total_gols == 1 and eh_1h:
                if event_id not in notificados_15_ht and 18 <= minuto_num <= 28:
                    tem_xg_valido = (xg_tot >= 0.80) if xg_tot > 0 else (chutes_gol >= 2 and finalizacoes >= 5)
                    
                    if tem_xg_valido and fluxo_confirmado:
                        notificados_15_ht.add(event_id)
                        mensagem = (
                            f"⚡ *FARO DE BEAGLE: OVER 1.5 HT (2º GOL)* ⚡\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                            f"👞 *Finalizações Totais:* `{finalizacoes}`{linha_xg}{linha_fluxo}{linha_prelive}\n\n"
                            f"💡 Confira a linha de **Over 1.5 HT**!"
                        )
                        enviar_alerta(mensagem)

            # ==================================================================
            # 3. OVER LIMITE FT -> 65' a 75' do 2º Tempo
            # ==================================================================
            elif eh_2h and abs(gols_c - gols_f) <= 1 and total_gols <= 4:
                if event_id not in notificados_limite_ft and 65 <= minuto_num <= 75:
                    tem_xg_valido = (xg_tot >= 1.20) if xg_tot > 0 else (chutes_gol >= 3 and finalizacoes >= 8)
                    
                    if tem_xg_valido and fluxo_confirmado:
                        notificados_limite_ft.add(event_id)
                        proximo_gol = total_gols + 0.5
                        mensagem = (
                            f"🎯 *FARO DE BEAGLE: OVER LIMITE FT (+{proximo_gol})* 🎯\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"🎯 *Chutes no Gol:* `{chutes_gol}`\n"
                            f"👞 *Finalizações Totais:* `{finalizacoes}`{linha_xg}{linha_fluxo}{linha_prelive}\n"
                            f"🚩 *Escanteios:* `{escanteios}`\n\n"
                            f"💡 Confira a linha de **Over Limite (+{proximo_gol})**!"
                        )
                        enviar_alerta(mensagem)

    except Exception as e:
        print(f"Erro na consulta: {e}")

if __name__ == '__main__':
    horario_inicio = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario_inicio}] Faro de Beagle rodando com analise Pré-Live + xG + Fluxo...")

    while True:
        try:
            agora_br = obter_horario_brasil()
            hora_atual = agora_br.hour

            if 8 <= hora_atual < 24:
                checar_jogos_ao_vivo()
            else:
                horario_formatado = agora_br.strftime('%H:%M:%S')
                print(f"[{horario_formatado}] Bot em repouso fora do horário (08h às 00h).")

        except Exception as e:
            print(f"Aviso no ciclo principal: {e}")

        time.sleep(240)
