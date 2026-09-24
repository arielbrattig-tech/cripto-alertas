"""Monitor de oscilação de criptomoedas na última hora (Binance Futures) com alerta no WhatsApp via CallMeBot.

Regras de alerta (por moeda):
- Olha os candles de 1 minuto dos últimos 60 minutos e compara o preço atual com a mínima
  (alta) e a máxima (queda) desse período — pega qualquer movimento de 5% em menos de 1 hora.
- Alerta quando o movimento chega a +5% ou -5%.
- Na mesma direção, só alerta de novo depois de COOLDOWN_MIN minutos ou se o movimento
  chegar a um novo degrau de 5% (10%, 15%...). Direção oposta alerta na hora.
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ===== Configuração =====
SYMBOLS = ["DOTUSDT", "NEARUSDT", "ATOMUSDT", "SUIUSDT", "ONDOUSDT"]  # adicione/remova moedas aqui
THRESHOLD_PCT = 5.0     # tamanho de cada degrau de alerta
WINDOW_MIN = 60         # janela de observação (minutos)
COOLDOWN_MIN = 60       # tempo mínimo entre alertas na mesma direção (salvo novo degrau)
STATE_FILE = Path(__file__).parent / "state.json"
BRT = timezone(timedelta(hours=-3))  # horário de Brasília

KLINE_SOURCES = [
    # Binance Futures (perpétuo). Bloqueia IPs dos EUA (servidores do GitHub), por isso há fallback.
    ("Binance Futures", "https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit={limit}"),
    # Mirror público de dados da Binance (spot) — funciona de qualquer lugar.
    ("Binance Spot", "https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}"),
]


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cripto-alertas/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def fetch_candles(symbol):
    """Candles de 1 min da última hora: [abertura, open, high, low, close, ...]."""
    errors = []
    for name, url in KLINE_SOURCES:
        try:
            candles = http_get_json(url.format(symbol=symbol, limit=WINDOW_MIN))
            if not candles:
                raise ValueError("resposta vazia")
            return name, candles
        except Exception as e:  # tenta a próxima fonte
            errors.append(f"{name}: {e}")
    raise RuntimeError(f"Falha ao buscar {symbol}: " + " | ".join(errors))


def fetch_move(symbol):
    """Maior movimento da última hora até o preço atual: alta desde a mínima ou queda desde a máxima."""
    source, candles = fetch_candles(symbol)
    price = float(candles[-1][4])
    low = min(float(c[3]) for c in candles)
    high = max(float(c[2]) for c in candles)
    rise = (price - low) / low * 100
    fall = (price - high) / high * 100
    return source, price, (rise if rise >= -fall else fall)


def fetch_btc():
    """Preço do BTC e variação no mesmo período (agora vs. 1 hora atrás)."""
    try:
        _, candles = fetch_candles("BTCUSDT")
        price = float(candles[-1][4])
        start = float(candles[0][1])
        return price, (price - start) / start * 100
    except Exception as e:  # alerta sai mesmo sem o BTC
        print(e, file=sys.stderr)
        return None


def send_whatsapp(text):
    phone = os.environ.get("CALLMEBOT_PHONE")
    apikey = os.environ.get("CALLMEBOT_APIKEY")
    if not phone or not apikey:
        print("[dry-run] CALLMEBOT_PHONE/CALLMEBOT_APIKEY não definidos. Mensagem:\n" + text)
        return
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": phone, "text": text, "apikey": apikey}
    )
    req = urllib.request.Request(url, headers={"User-Agent": "cripto-alertas/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", "replace")
    if "error" in body.lower() and "queued" not in body.lower():
        raise RuntimeError(f"CallMeBot retornou erro: {body[:300]}")
    print("WhatsApp enviado.")
    time.sleep(5)  # CallMeBot limita envios seguidos


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def level_for(pct):
    """Com degrau de 5%: +6% -> 1, -11% -> -2, +3% -> 0."""
    steps = int(abs(pct) // THRESHOLD_PCT)
    return steps if pct >= 0 else -steps


def fmt_num(value, decimals):
    """Formato brasileiro: 112345.6 -> '112.345,60'."""
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_price(price):
    if price >= 1000:
        return fmt_num(price, 0)
    if price >= 10:
        return fmt_num(price, 2)
    return fmt_num(price, 4)


def fmt_pct(pct):
    return ("+" if pct >= 0 else "") + fmt_num(pct, 2) + "%"


def build_message(symbol, price, pct, btc):
    coin = symbol.replace("USDT", "")
    head, word = ("🚀🟢", "SUBIU") if pct >= 0 else ("🔻🔴", "CAIU")
    lines = [
        f"{head} *{coin}/USDT {word} {fmt_pct(pct)}*",
        "Variação na última hora",
        f"💵 Preço: *US$ {fmt_price(price)}*",
    ]
    if btc:
        btc_price, btc_pct = btc
        btc_dot = "🟢" if btc_pct >= 0 else "🔴"
        lines += [
            "",
            "━━━━━━━━━━━━━━",
            "₿ *BTC/USD*",
            f"💵 US$ {fmt_price(btc_price)}  {btc_dot} {fmt_pct(btc_pct)}",
        ]
    now = datetime.now(BRT).strftime("%d/%m %H:%M")
    lines += ["", f"🕒 {now} (Brasília)"]
    return "\n".join(lines)


def main():
    if os.environ.get("TESTE") == "true":  # dispara a mensagem de todas as moedas com dados reais
        btc = fetch_btc()
        for symbol in SYMBOLS:
            _, price, pct = fetch_move(symbol)
            send_whatsapp(build_message(symbol, price, pct, btc))
        return

    state = load_state()
    state.pop("levels", None)  # formato antigo (variação 24h)
    alerts = state.setdefault("alerts", {})
    now = int(time.time())
    failures = 0
    btc = None

    for symbol in SYMBOLS:
        try:
            source, price, pct = fetch_move(symbol)
        except Exception as e:
            print(e, file=sys.stderr)
            failures += 1
            continue

        last = alerts.get(symbol)
        expired = last is None or now - last["at"] >= COOLDOWN_MIN * 60
        level = level_for(pct)
        print(f"{symbol}: {price} ({pct:+.2f}% em {WINDOW_MIN} min) via {source} | nível {level}, último alerta {last}")

        if level != 0 and (
            expired
            or (level > 0) != (last["level"] > 0)  # direção oposta
            or abs(level) > abs(last["level"])     # novo degrau
        ):
            if btc is None:
                btc = fetch_btc()
            try:
                send_whatsapp(build_message(symbol, price, pct, btc))
            except Exception as e:  # não marca como alertado -> tenta de novo na próxima execução
                print(f"{symbol}: falha ao enviar WhatsApp: {e}", file=sys.stderr)
                failures += 1
                continue
            alerts[symbol] = {"level": level, "at": now}
        elif expired and last is not None:
            del alerts[symbol]  # passou o cooldown sem novo movimento

    # Muda uma vez por mês -> gera um commit e impede o GitHub de desativar o agendamento por inatividade.
    state["keepalive"] = datetime.now(timezone.utc).strftime("%Y-%m")
    save_state(state)

    if failures == len(SYMBOLS):
        sys.exit(1)


if __name__ == "__main__":
    main()
