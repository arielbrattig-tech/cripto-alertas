# Cripto Alertas

Monitora a variação de 24h de moedas na Binance Futures e envia alerta no WhatsApp (CallMeBot)
quando passa de ±5% — e de novo a cada degrau de 5% (10%, 15%...). Roda no GitHub Actions a cada 5 min.

## Configurar o WhatsApp (CallMeBot)
1. Pegue o número atual do bot em https://www.callmebot.com/blog/free-api-whatsapp-messages/ e adicione aos contatos.
2. Envie para ele por WhatsApp: `I allow callmebot to send me messages`
3. Você receberá sua **API key**.
4. No GitHub: *Settings → Secrets and variables → Actions → New repository secret*:
   - `CALLMEBOT_PHONE` = seu número com DDI, ex.: `+5511999999999`
   - `CALLMEBOT_APIKEY` = a key recebida

## Adicionar moedas
Edite `SYMBOLS` em `monitor.py`. Atuais: DOT, NEAR, ATOM, SUI, ONDO (pares USDT).

## Testar
Aba **Actions → Monitor cripto → Run workflow**.
