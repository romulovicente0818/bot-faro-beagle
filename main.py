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

notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()

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
        scraper.post(url, json=payload, timeout=10)
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

def obter_pressao_grafico_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/graph"
    try:
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            points = res.json().get('graphPoints', [])
            if not points:
                return {'pico': 0, 'media': 0, 'recente': 0, 'aceleracao': 0}

            ultimos_pontos = points[-10:] if len(points) >= 10 else points
            valores = [float(p.get('value', 0)) for p in ultimos_pontos if 'value' in p]

            if not valores:
                return {'pico': 0, 'media': 0, 'recente': 0, 'aceleracao': 0}

            metade = max(1, len(valores) // 2)
            primeira_metade = valores[:metade]
            segunda_metade = valores[metade:]

            media_abs = sum(abs(x) for x in valores) / len(valores)
            recente_abs = sum(abs(x) for x in segunda_metade) / len(segunda_metade) if segunda_metade else media_abs
            media_anterior = sum(abs(x) for x in primeira_metade) / len(primeira_metade) if primeira_metade else 0
            pico_pressao = max(abs(x) for x in valores)
            aceleracao = recente_abs - media_anterior

            return {
                'pico': pico_pressao,
                'media': media_abs,
                'recente': recente_abs,
                'aceleracao': aceleracao
            }
    except Exception:
        pass
    return {'pico': 0, 'media': 0, 'recente': 0, 'aceleracao': 0}

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
    status_desc = str(item.get('status', {}).get('description', '')).lower().strip()
    status_type = str(item.get('status', {}).get('type', '')).lower().strip()

    termos_prorrogacao = ['extra', 'et', 'extratime', 'overtime', 'penalties', 'pen', 'prorrogação']
    for termo in termos_prorrogacao:
        if termo in status_desc or termo in status_type:
            return None, None

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
            if 1 <= m_calc <= 90:
                minuto = m_calc

    if minuto:
        if eh_1h and minuto <= 45:
            return f"{minuto}'", minuto
        elif eh_2h and 45 <= minuto <= 90:
            return f"{minuto}'", minuto

    return None, None

# ==============================================================================
# SISTEMA GOAL SCORE DE 0 A 100 PONTOS E LEITURA DINÂMICA
# ==============================================================================

def calcular_score_0_100(xg_tot, fin_tot, chutes_gol, escanteios, grandes_chances, fin_h, fin_a, pressao, minuto, mercado):
    score = 0
    motivos = []

    # 1. xG Relativo ao Minuto (Peso: 25)
    xg_esperado = (minuto / 90.0) * (0.8 if 'HT' in mercado else 1.4)
    if xg_tot >= xg_esperado * 1.5 and xg_tot > 0.3:
        pts_xg = 25
        motivos.append("xG elevado para o minuto")
    elif xg_tot >= xg_esperado and xg_tot > 0.2:
        pts_xg = 18
        motivos.append("xG dentro da média ideal")
    elif xg_tot >= 0.3:
        pts_xg = 12
    else:
        pts_xg = 5
    score += pts_xg

    # 2. Chutes no Alvo (Peso: 20)
    if chutes_gol >= 5:
        pts_ch = 20
        motivos.append(f"{chutes_gol} chutes no alvo")
    elif chutes_gol >= 3:
        pts_ch = 15
        motivos.append(f"{chutes_gol} chutes no alvo")
    elif chutes_gol >= 2:
        pts_ch = 10
    else:
        pts_ch = 4
    score += pts_ch

    # 3. Grandes Chances (Peso: 20)
    if grandes_chances >= 3:
        pts_gc = 20
        motivos.append(f"{grandes_chances} grandes chances")
    elif grandes_chances == 2:
        pts_gc = 16
        motivos.append("2 grandes chances")
    elif grandes_chances == 1:
        pts_gc = 10
        motivos.append("1 grande chance criada")
    else:
        pts_gc = 0
    score += pts_gc

    # 4. Volume de Finalizações (Peso: 15)
    fin_alvo = 8 if 'HT' in mercado else 14
    if fin_tot >= fin_alvo:
        pts_fin = 15
        motivos.append("alto volume de finalizações")
    elif fin_tot >= fin_alvo * 0.7:
        pts_fin = 10
    else:
        pts_fin = 5
    score += pts_fin

    # 5. Escanteios (Peso: 5)
    if escanteios >= 5:
        pts_esc = 5
        motivos.append("bom número de escanteios")
    elif escanteios >= 3:
        pts_esc = 3
    else:
        pts_esc = 1
    score += pts_esc

    # 6. Pressão Atual (Peso: 10)
    if pressao['recente'] >= 45:
        pts_pr = 10
        motivos.append("pressão forte")
    elif pressao['recente'] >= 25:
        pts_pr = 7
    else:
        pts_pr = 3
    score += pts_pr

    # 7. Aceleração da Pressão (Peso: 5)
    if pressao['aceleracao'] >= 8:
        pts_ac = 5
        motivos.append("pressão crescente")
    elif pressao['aceleracao'] >= 3:
        pts_ac = 3
    else:
        pts_ac = 1
    score += pts_ac

    # Identificadores Visuais
    # Intensidade
    if pressao['aceleracao'] >= 5:
        intensidade = "CRESCENTE"
    elif pressao['aceleracao'] <= -5:
        intensidade = "CAINDO"
    else:
        intensidade = "ESTÁVEL"

    # Pressão
    if pressao['recente'] >= 40:
        pressao_rotulo = "ALTA"
    elif pressao['recente'] >= 20:
        pressao_rotulo = "MÉDIA"
    else:
        pressao_rotulo = "BAIXA"

    # Qualidade das Chances
    if xg_tot >= 0.7 or grandes_chances >= 2 or (chutes_gol >= 4 and xg_tot >= 0.5):
        qualidade = "ALTA"
    elif xg_tot >= 0.4 or grandes_chances == 1:
        qualidade = "MÉDIA"
    else:
        qualidade = "BAIXA"

    # Equilíbrio de Volume
    if fin_h > 0 and fin_a > 0:
        prop = min(fin_h, fin_a) / max(fin_h, fin_a)
        if prop >= 0.4:
            motivos.append("volume ofensivo dos dois lados")

    score_final = min(100, score)
    confianca_val = round(score_final / 10.0, 1)

    return score_final, confianca_val, intensidade, pressao_rotulo, qualidade, motivos

def validar_alertas_enviados(jogos_dict):
    chaves_para_remover = []

    for chave_alerta, info in list(alertas_pendentes.items()):
        event_id = info['event_id']
        message_id = info['message_id']
        gols_no_alerta = info['gols_alerta']
        mercado = info['mercado']
        msg_original = info['mensagem_original']

        item_jogo = jogos_dict.get(event_id)
        if not item_jogo:
            continue

        gols_c = item_jogo.get('homeScore', {}).get('current', 0)
        gols_f = item_jogo.get('awayScore', {}).get('current', 0)
        gols_atuais = gols_c + gols_f

        status_desc = str(item_jogo.get('status', {}).get('description', '')).lower()
        time_status = str(item_jogo.get('status', {}).get('type', '')).lower()

        eh_intervalo = 'halftime' in status_desc or 'ht' in status_desc or time_status == 'halftime'
        eh_2h = '2nd' in status_desc or time_status == '2nd'
        eh_finalizado = time_status == 'finished' or 'ended' in status_desc or 'ft' in status_desc or 'extra' in status_desc

        if gols_atuais > gols_no_alerta:
            nova_mensagem = f"{msg_original}\n\n✅️✅️✅️"
            editar_alerta(message_id, nova_mensagem)
            chaves_para_remover.append(chave_alerta)
        else:
            if mercado in ['05_HT', '15_HT'] and (eh_intervalo or eh_2h or eh_finalizado):
                nova_mensagem = f"{msg_original}\n\n❌️❌️❌️"
                editar_alerta(message_id, nova_mensagem)
                chaves_para_remover.append(chave_alerta)
            elif mercado == 'LIMITE_FT' and eh_finalizado:
                nova_mensagem = f"{msg_original}\n\n❌️❌️❌️"
                editar_alerta(message_id, nova_mensagem)
                chaves_para_remover.append(chave_alerta)

    for ch in chaves_para_remover:
        alertas_pendentes.pop(ch, None)

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

        jogos_dict = {str(item.get('id', '')).strip(): item for item in jogos if item.get('id')}
        validar_alertas_enviados(jogos_dict)

        for item in jogos:
            event_id = str(item.get('id', '')).strip()
            if not event_id:
                continue

            nome_liga = item.get('tournament', {}).get('name', 'Liga')
            time_casa = item.get('homeTeam', {}).get('name', 'Casa')
            time_fora = item.get('awayTeam', {}).get('name', 'Fora')

            if not eh_partida_valida(nome_liga, time_casa, time_fora):
                continue

            status_desc = str(item.get('status', {}).get('description', '')).lower()
            time_status = str(item.get('status', {}).get('type', '')).lower()

            if any(term in status_desc or term in time_status for term in ['extra', 'et', 'extratime', 'overtime', 'penalties']):
                continue

            gols_c = item.get('homeScore', {}).get('current', 0)
            gols_f = item.get('awayScore', {}).get('current', 0)
            total_gols = gols_c + gols_f

            eh_1h = time_status == 'inprogress' and '1st' in status_desc
            eh_2h = time_status == 'inprogress' and '2nd' in status_desc

            if not (eh_1h or eh_2h):
                continue

            minutagem_str, minuto_num = extrair_minutagem_e_numero(item, eh_1h, eh_2h)
            if not minuto_num:
                continue

            stats = obter_estatisticas_sofascore(event_id)

            cg_tot, cg_h, cg_a = extrair_stat_sofascore(stats, 'Shots on target')
            cf_tot, cf_h, cf_a = extrair_stat_sofascore(stats, 'Shots off target')
            esc_tot, _, _ = extrair_stat_sofascore(stats, 'Corner kicks')
            gc_tot, _, _ = extrair_stat_sofascore(stats, 'Big chances')
            if gc_tot == 0:
                gc_tot, _, _ = extrair_stat_sofascore(stats, 'Big chances created')

            chutes_gol = int(cg_tot)
            fin_tot = int(cg_tot + cf_tot)
            escanteios = int(esc_tot)
            grandes_chances = int(gc_tot)

            xg_tot, xg_h, xg_a = extrair_xg_sofascore(stats)
            pressao = obter_pressao_grafico_sofascore(event_id)

            # ==================================================================
            # 1. OVER 0.5 HT (0x0) -> 15' a 25'
            # ==================================================================
            if total_gols == 0 and eh_1h and 15 <= minuto_num <= 25:
                if event_id not in notificados_05_ht:
                    score, confianca, int_rotulo, pres_rotulo, qual_rotulo, motivos = calcular_score_0_100(
                        xg_tot, fin_tot, chutes_gol, escanteios, grandes_chances,
                        int(cg_h + cf_h), int(cg_a + cf_a), pressao, minuto_num, '05_HT'
                    )

                    # Filtro Rígido + Score Mínimo (75 pts)
                    if score >= 75 and (xg_tot >= 0.40 or chutes_gol >= 2 or fin_tot >= 6):
                        notificados_05_ht.add(event_id)
                        motivos_str = "\n".join([f"• {m}" for m in motivos]) if motivos else "• Volume ofensivo constante"

                        mensagem = (
                            f"🐶 *FARO DE BEAGLE*\n"
                            f"🔥 *SINAL +0,5 HT*\n\n"
                            f"*{time_casa} x {time_fora}*\n"
                            f"⏱️ {minutagem_str} — {gols_c}x{gols_f}\n\n"
                            f"📊 *GOAL SCORE:* `{score}/100`\n\n"
                            f"xG: {xg_tot:.2f}\n"
                            f"Finalizações: {fin_tot}\n"
                            f"No alvo: {chutes_gol}\n"
                            f"Grandes chances: {grandes_chances}\n"
                            f"Escanteios: {escanteios}\n\n"
                            f"📈 Intensidade: *{int_rotulo}*\n"
                            f"🔥 Pressão: *{pres_rotulo}*\n"
                            f"🎯 Qualidade das chances: *{qual_rotulo}*\n\n"
                            f"🧠 *Motivos:*\n"
                            f"{motivos_str}\n\n"
                            f"🐶 *FARO:*\n"
                            f"OVER 0,5 HT\n\n"
                            f"Confiança: *{confianca:.1f}/10*\n"
                            f"------------"
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
            elif total_gols == 1 and eh_1h and 18 <= minuto_num <= 28:
                if event_id not in notificados_15_ht:
                    score, confianca, int_rotulo, pres_rotulo, qual_rotulo, motivos = calcular_score_0_100(
                        xg_tot, fin_tot, chutes_gol, escanteios, grandes_chances,
                        int(cg_h + cf_h), int(cg_a + cf_a), pressao, minuto_num, '15_HT'
                    )

                    if score >= 75 and (xg_tot >= 0.70 or chutes_gol >= 3 or fin_tot >= 7):
                        notificados_15_ht.add(event_id)
                        motivos_str = "\n".join([f"• {m}" for m in motivos]) if motivos else "• Pressão constante após o primeiro gol"

                        mensagem = (
                            f"🐶 *FARO DE BEAGLE*\n"
                            f"⚡ *SINAL +1,5 HT*\n\n"
                            f"*{time_casa} x {time_fora}*\n"
                            f"⏱️ {minutagem_str} — {gols_c}x{gols_f}\n\n"
                            f"📊 *GOAL SCORE:* `{score}/100`\n\n"
                            f"xG: {xg_tot:.2f}\n"
                            f"Finalizações: {fin_tot}\n"
                            f"No alvo: {chutes_gol}\n"
                            f"Grandes chances: {grandes_chances}\n"
                            f"Escanteios: {escanteios}\n\n"
                            f"📈 Intensidade: *{int_rotulo}*\n"
                            f"🔥 Pressão: *{pres_rotulo}*\n"
                            f"🎯 Qualidade das chances: *{qual_rotulo}*\n\n"
                            f"🧠 *Motivos:*\n"
                            f"{motivos_str}\n\n"
                            f"🐶 *FARO:*\n"
                            f"OVER 1,5 HT\n\n"
                            f"Confiança: *{confianca:.1f}/10*\n"
                            f"------------"
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
            elif eh_2h and abs(gols_c - gols_f) <= 1 and total_gols <= 4 and 65 <= minuto_num <= 75:
                if event_id not in notificados_limite_ft:
                    score, confianca, int_rotulo, pres_rotulo, qual_rotulo, motivos = calcular_score_0_100(
                        xg_tot, fin_tot, chutes_gol, escanteios, grandes_chances,
                        int(cg_h + cf_h), int(cg_a + cf_a), pressao, minuto_num, 'LIMITE_FT'
                    )

                    proximo_gol = total_gols + 0.5
                    if score >= 75 and (xg_tot >= 1.10 or chutes_gol >= 4 or fin_tot >= 11):
                        notificados_limite_ft.add(event_id)
                        motivos_str = "\n".join([f"• {m}" for m in motivos]) if motivos else "• Sufoco do segundo tempo em busca do gol"

                        mensagem = (
                            f"🐶 *FARO DE BEAGLE*\n"
                            f"🎯 *SINAL OVER LIMITE FT (+{proximo_gol})*\n\n"
                            f"*{time_casa} x {time_fora}*\n"
                            f"⏱️ {minutagem_str} — {gols_c}x{gols_f}\n\n"
                            f"📊 *GOAL SCORE:* `{score}/100`\n\n"
                            f"xG: {xg_tot:.2f}\n"
                            f"Finalizações: {fin_tot}\n"
                            f"No alvo: {chutes_gol}\n"
                            f"Grandes chances: {grandes_chances}\n"
                            f"Escanteios: {escanteios}\n\n"
                            f"📈 Intensidade: *{int_rotulo}*\n"
                            f"🔥 Pressão: *{pres_rotulo}*\n"
                            f"🎯 Qualidade das chances: *{qual_rotulo}*\n\n"
                            f"🧠 *Motivos:*\n"
                            f"{motivos_str}\n\n"
                            f"🐶 *FARO:*\n"
                            f"OVER LIMITE FT (+{proximo_gol})\n\n"
                            f"Confiança: *{confianca:.1f}/10*\n"
                            f"------------"
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
        print(f"Erro na consulta: {e}")

if __name__ == '__main__':
    horario_inicio = obter_horario_brasil().strftime('%H:%M:%S')
    print(f"[{horario_inicio}] Faro de Beagle rodando com Goal Score 0-100 e novo layout...")

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

        time.sleep(120)
