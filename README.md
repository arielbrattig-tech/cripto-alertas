# Cripto Alertas

Monitora moedas na Binance Futures e envia alerta no WhatsApp (CallMeBot) quando alguma sobe ou cai
5% ou mais em menos de 1 hora (preço atual vs. mínima/máxima dos últimos 60 min). Na mesma direção,
só alerta de novo após 1 hora ou se o movimento chegar a um novo degrau (10%, 15%...).
Roda no GitHub Actions a cada 5 min.

## Configurar o WhatsApp (CallMeBot)
1. Abra https://wa.me/34623801190?text=I%20allow%20callmebot%20to%20send%20me%20messages (número atual do bot; confira em callmebot.com se mudar).
2. Envie para ele por WhatsApp: `I allow callmebot to send me messages`
3. Você receberá sua **API key**.
4. No GitHub: *Settings → Secrets and variables → Actions → New repository secret*:
   - `CALLMEBOT_PHONE` = seu número com DDI, ex.: `+5511999999999`
   - `CALLMEBOT_APIKEY` = a key recebida

## Adicionar moedas
Edite `SYMBOLS` em `monitor.py`. Atuais: DOT, NEAR, ATOM, SUI, ONDO (pares USDT).

## Testar
Aba **Actions → Monitor cripto → Run workflow**, marcando "Enviar mensagem de teste"
(envia a mensagem de todas as moedas com os dados da última hora).
