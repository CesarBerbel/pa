FROM node:20-alpine

ENV NODE_ENV=production

WORKDIR /app

# As dependências mudam muito menos do que o server.js; copiar os manifestos
# primeiro faz a instalação ficar em cache entre rebuilds.
#
# `npm ci` e não `npm install`: instala exatamente as versões do lock file. Sem
# isso, dois deploys da mesma revisão podiam trazer bibliotecas diferentes, e a
# ligação ao WhatsApp é sensível a versões do Baileys.
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund

COPY server.js ./

# Ponto de montagem do volume com as credenciais da sessão. Se ficasse dentro
# da imagem, cada rebuild obrigaria a ler o QR code outra vez.
RUN mkdir -p /data/auth

EXPOSE 3000

CMD ["node", "server.js"]
