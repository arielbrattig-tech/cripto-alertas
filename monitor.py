"""Monitor de variação 24h de criptomoedas (Binance Futures) com alerta no WhatsApp via CallMeBot.

Regras de alerta (por moeda):
- Alerta quando a variação 24h cruza +10% ou -10%.
- Alerta de novo a cada novo degrau de 10% (20%, 30%...) na mesma direção.
- Rearma quando a variação volta para dentro de ±REARM_PCT (evita alertas repetidos
  quando o preço fica oscilando em torno de 10%).
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
THRESHOLD_PCT = 10.0    # tamanho de cada degrau de alerta
REARM_PCT = 8.0         # volta abaixo disso (em módulo) = rearma
STATE_FILE = Path(__file__).parent / "state.json"
BRT = timezone(timedelta(hours=-3))  # horário de Brasília

PRICE_SOURCES = [
    # Binance Futures (perpétuo). Bloqueia IPs dos EUA (servidores do GitHub), por isso há fallback.
    ("Binance Futures", "https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={symbol}"),
    # Mirror público de dados da Binance (spot) — funciona de qualquer lugar.
    ("Binance Spot", "https://data-api.binance.vision/api/v3/ticker/24hr?symbol={symbol}"),
]


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "cripto-alertas/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def fetch_ticker(symbol):
    errors = []
    for name, url in PRICE_SOURCES:
        try:
            data = http_get_json(url.format(symbol=symbol))
            return name, float(data["lastPrice"]), float(data["priceChangePercent"])
        except Exception as e:  # tenta a próxima fonte
            errors.append(f"{name}: {e}")
    raise RuntimeError(f"Falha ao buscar {symbol}: " + " | ".join(errors))


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
    """Com degrau de 10%: +13% -> 1, -21% -> -2, +7% -> 0."""
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
        "Variação nas últimas 24h",
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


def fetch_btc():
    try:
        _, price, pct = fetch_ticker("BTCUSDT")
        return price, pct
    except Exception as e:  # alerta sai mesmo sem o BTC
        print(e, file=sys.stderr)
        return None


def main():
    if os.environ.get("TESTE") == "true":  # dispara a mensagem de todas as moedas com dados reais
        btc = fetch_btc()
        for symbol in SYMBOLS:
            _, price, pct = fetch_ticker(symbol)
            send_whatsapp(build_message(symbol, price, pct, btc))
        return

    state = load_state()
    levels = state.setdefault("levels", {})
    failures = 0
    btc = None

    for symbol in SYMBOLS:
        try:
            source, price, pct = fetch_ticker(symbol)
        except Exception as e:
            print(e, file=sys.stderr)
            failures += 1
            continue

        current = levels.get(symbol, 0)
        level = level_for(pct)
        print(f"{symbol}: {price} ({pct:+.2f}% 24h) via {source} | nível {level}, último alerta {current}")

        new_direction = level != 0 and (current == 0 or (level > 0) != (current > 0))
        deeper = level != 0 and (level > 0) == (current > 0) and abs(level) > abs(current)

        if new_direction or deeper:
            if btc is None:
                btc = fetch_btc()
            try:
                send_whatsapp(build_message(symbol, price, pct, btc))
            except Exception as e:  # não marca como alertado -> tenta de novo na próxima execução
                print(f"{symbol}: falha ao enviar WhatsApp: {e}", file=sys.stderr)
                failures += 1
                continue
            levels[symbol] = level
        elif abs(pct) < REARM_PCT and current != 0:
            print(f"{symbol}: voltou para dentro de ±{REARM_PCT}%, alerta rearmado.")
            levels[symbol] = 0

    # Muda uma vez por mês -> gera um commit e impede o GitHub de desativar o agendamento por inatividade.
    state["keepalive"] = datetime.now(timezone.utc).strftime("%Y-%m")
    save_state(state)

    if failures == len(SYMBOLS):
        sys.exit(1)


if __name__ == "__main__":
    main()
