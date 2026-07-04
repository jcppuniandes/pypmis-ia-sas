FROM mcr.microsoft.com/playwright:v1.57.0-noble

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --fund=false

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
