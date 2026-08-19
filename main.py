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

# Registros para evitar repetição do mesmo alerta
notificados_05_ht = set()
notificados_15_ht = set()
notificados_limite_ft = set()

# Dicionário de acompanhamento dos alertas enviados para validação do resultado
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

def obter_prelive_sofascore(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/prematch-form"
    try:
        res = scraper.get(url, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

def obter_pressao_grafico_sofascore(event_id):
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
            
            texto_fluxo = f"🔥 *Pressão no Grafico:* Pico `{pico_pressao}` | Média `{media_pressao}`\n"
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
    status_desc = str(item.get('status', {}).get('description', '')).lower().strip()
    status_type = str(item.get('status', {}).get('type', '')).lower().strip()

    # BLOQUEIO RIGIDO DE PRORROGAÇÃO E PÊNALTIS
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

    # Valida apenas minutos dentro do tempo regulamentar HT (1-45) e FT (45-90)
    if minuto:
        if eh_1h and minuto <= 45:
            return f"{minuto}' do 1º tempo", minuto
        elif eh_2h and 45 <= minuto <= 90:
            return f"{minuto}' do 2º tempo", minuto

    return None, None

def validar_alertas_enviados(jogos_dict):
    """Verifica o placar e edita o alerta apenas anexando os emojis de GREEN ou RED ao final."""
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

            category = item.get('tournament', {}).get('category', {})
            nome_pais = category.get('name', '')

            if nome_pais and nome_pais.lower() not in nome_liga.lower():
                liga_formatada = f"{nome_pais} - {nome_liga}"
            else:
                liga_formatada = nome_liga

            status_desc = str(item.get('status', {}).get('description', '')).lower()
            time_status = str(item.get('status', {}).get('type', '')).lower()

            # Descarta se estiver em prorrogação ou disputa de pênaltis
            if any(term in status_desc or term in time_status for term in ['extra', 'et', 'extratime', 'overtime', 'penalties']):
                continue

            gols_c = item.get('homeScore', {}).get('current', 0)
            gols_f = item.get('awayScore', {}).get('current', 0)
            total_gols = gols_c + gols_f

            eh_1h = time_status == 'inprogress' and '1st' in status_desc
            eh_2h = time_status == 'inprogress' and '2nd' in status_desc

            if not (eh_1h or eh_2h):
                continue

            minutagem, minuto_num = extrair_minutagem_e_numero(item, eh_1h, eh_2h)
            if not minuto_num:
                continue

            stats = obter_estatisticas_sofascore(event_id)
            
            cg_tot, cg_h, cg_a = extrair_stat_sofascore(stats, 'Shots on target')
            cf_tot, cf_h, cf_a = extrair_stat_sofascore(stats, 'Shots off target')
            esc_tot, esc_h, esc_a = extrair_stat_sofascore(stats, 'Corner kicks')

            chutes_gol = int(cg_tot)
            cg_h_int, cg_a_int = int(cg_h), int(cg_a)

            fin_tot = int(cg_tot + cf_tot)
            fin_h_int, fin_a_int = int(cg_h + cf_h), int(cg_a + cf_a)

            escanteios = int(esc_tot)
            esc_h_int, esc_a_int = int(esc_h), int(esc_a)

            xg_tot, xg_h, xg_a = extrair_xg_sofascore(stats)
            linha_xg = f"📈 *xG Acumulado:* `{xg_tot:.2f}` _({time_casa} {xg_h:.2f} | {xg_a:.2f} {time_fora})_\n" if xg_tot > 0 else ""

            pico_pressao, linha_fluxo = obter_pressao_grafico_sofascore(event_id)
            fluxo_confirmado = (pico_pressao >= 30) if pico_pressao > 0 else True

            prelive_dados = obter_prelive_sofascore(event_id)
            linha_prelive = "📋 *Tendência Pré-Live:* Propenso a Gols ✅\n" if prelive_dados else ""

            bloco_estatisticas = (
                f"{linha_xg}"
                f"{linha_fluxo}"
                f"shirt *Finalizações Totais:* `{fin_tot}` _({fin_h_int}x{fin_a_int})_\n"
                f"🎯 *Chutes no Gol:* `{chutes_gol}` _({cg_h_int}x{cg_a_int})_\n"
                f"🚩 *Escanteios:* `{escanteios}` _({esc_h_int}x{esc_a_int})_\n"
                f"{linha_prelive}"
            )

            # ==================================================================
            # 1. OVER 0.5 HT (0x0) -> 15' a 25' do 1º TEMPO
            # FILTRO SUBSTITUÍDO
            # ==================================================================
            if total_gols == 0 and eh_1h:
                if event_id not in notificados_05_ht and 15 <= minuto_num <= 25:

                    # ----------------------------------------------------------
                    # FILTRO +0,5 HT
                    #
                    # Prioridade:
                    # 1) xG
                    # 2) Chutes no alvo
                    # 3) Finalizações
                    # 4) Escanteios
                    # 5) Pressão
                    #
                    # Não basta apenas uma estatística isolada.
                    # ----------------------------------------------------------

                    if xg_tot > 0:

                        # Cenário com xG disponível
                        filtro_05_ht = (
                            xg_tot >= 0.45
                            and (
                                chutes_gol >= 2
                                or fin_tot >= 7
                            )
                            and (
                                pico_pressao >= 30
                                or chutes_gol >= 3
                                or fin_tot >= 9
                                or escanteios >= 4
                            )
                        )

                        # Reforço para xG muito alto
                        if xg_tot >= 0.65:
                            filtro_05_ht = (
                                (
                                    chutes_gol >= 2
                                    and fin_tot >= 6
                                )
                                or (
                                    chutes_gol >= 3
                                )
                                or (
                                    fin_tot >= 9
                                    and escanteios >= 3
                                )
                            )

                    else:

                        # Cenário sem xG disponível
                        filtro_05_ht = (
                            (
                                chutes_gol >= 3
                                and fin_tot >= 7
                            )
                            or (
                                chutes_gol >= 2
                                and fin_tot >= 9
                                and escanteios >= 3
                            )
                        )

                        if pico_pressao >= 35:
                            filtro_05_ht = (
                                filtro_05_ht
                                and (
                                    chutes_gol >= 2
                                    or fin_tot >= 8
                                )
                            )

                    if filtro_05_ht:
                        notificados_05_ht.add(event_id)

                        mensagem = (
                            f"🚨 *FARO DE BEAGLE: OVER 0.5 HT (0x0)* 🚨\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} 0 x 0 {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"{bloco_estatisticas}\n"
                            f"💡 Confira a linha de **Over 0.5 HT**!"
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
            # 2. OVER 1.5 HT (1x0 / 0x1) -> 18' a 28' DO 1º TEMPO
            # FILTRO SUBSTITUÍDO
            # ==================================================================
            elif total_gols == 1 and eh_1h:
                if event_id not in notificados_15_ht and 18 <= minuto_num <= 28:

                    # ----------------------------------------------------------
                    # FILTRO +1,5 HT
                    #
                    # Como já existe um gol, exigimos uma produção ofensiva
                    # superior à necessária para o +0,5 HT.
                    # ----------------------------------------------------------

                    if xg_tot > 0:

                        filtro_15_ht = (
                            xg_tot >= 0.80
                            and (
                                chutes_gol >= 2
                                or fin_tot >= 7
                            )
                            and (
                                pico_pressao >= 30
                                or chutes_gol >= 3
                                or fin_tot >= 9
                                or escanteios >= 4
                            )
                        )

                        # Quando o xG está realmente forte,
                        # permite combinação alternativa.
                        if xg_tot >= 1.05:
                            filtro_15_ht = (
                                (
                                    chutes_gol >= 2
                                    and fin_tot >= 6
                                )
                                or (
                                    chutes_gol >= 3
                                )
                                or (
                                    fin_tot >= 9
                                    and escanteios >= 3
                                )
                            )

                    else:

                        filtro_15_ht = (
                            (
                                chutes_gol >= 3
                                and fin_tot >= 7
                            )
                            or (
                                chutes_gol >= 2
                                and fin_tot >= 9
                                and escanteios >= 3
                            )
                        )

                        if pico_pressao >= 35:
                            filtro_15_ht = (
                                filtro_15_ht
                                and (
                                    chutes_gol >= 2
                                    or fin_tot >= 8
                                )
                            )

                    if filtro_15_ht:
                        notificados_15_ht.add(event_id)

                        mensagem = (
                            f"⚡ *FARO DE BEAGLE: OVER 1.5 HT (2º GOL)* ⚡\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"{bloco_estatisticas}\n"
                            f"💡 Confira a linha de **Over 1.5 HT**!"
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
            # 3. OVER LIMITE FT -> 65' a 75' DO 2º TEMPO
            # FILTRO SUBSTITUÍDO
            # ==================================================================
            elif eh_2h and abs(gols_c - gols_f) <= 1 and total_gols <= 4:
                if event_id not in notificados_limite_ft and 65 <= minuto_num <= 75:

                    # ----------------------------------------------------------
                    # FILTRO LIMITE FT
                    #
                    # O objetivo é encontrar partidas em que ainda existe
                    # intensidade suficiente para um gol, sem depender somente
                    # do xG.
                    # ----------------------------------------------------------

                    if xg_tot > 0:

                        filtro_limite_ft = (
                            xg_tot >= 1.20
                            and (
                                chutes_gol >= 3
                                or fin_tot >= 10
                            )
                            and (
                                pico_pressao >= 30
                                or chutes_gol >= 4
                                or fin_tot >= 13
                                or escanteios >= 6
                            )
                        )

                        # xG muito forte permite uma combinação mais agressiva.
                        if xg_tot >= 1.70:
                            filtro_limite_ft = (
                                (
                                    chutes_gol >= 3
                                    and fin_tot >= 9
                                )
                                or (
                                    chutes_gol >= 4
                                )
                                or (
                                    fin_tot >= 12
                                    and escanteios >= 5
                                )
                            )

                    else:

                        filtro_limite_ft = (
                            (
                                chutes_gol >= 4
                                and fin_tot >= 10
                            )
                            or (
                                chutes_gol >= 3
                                and fin_tot >= 13
                                and escanteios >= 5
                            )
                        )

                        if pico_pressao >= 40:
                            filtro_limite_ft = (
                                filtro_limite_ft
                                and (
                                    chutes_gol >= 3
                                    or fin_tot >= 11
                                )
                            )

                    if filtro_limite_ft:
                        notificados_limite_ft.add(event_id)

                        proximo_gol = total_gols + 0.5

                        mensagem = (
                            f"🎯 *FARO DE BEAGLE: OVER LIMITE FT (+{proximo_gol})* 🎯\n\n"
                            f"🏆 *Liga:* {liga_formatada}\n"
                            f"⚽ *{time_casa} {gols_c} x {gols_f} {time_fora}*\n"
                            f"⏱️ Tempo de Jogo: *{minutagem}*\n\n"
                            f"📊 *Estatísticas em Tempo Real:*\n"
                            f"{bloco_estatisticas}\n"
                            f"💡 Confira a linha de **Over Limite (+{proximo_gol})**!"
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
    print(f"[{horario_inicio}] Faro de Beagle rodando restrito a HT/FT (sem prorrogação)...")

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
