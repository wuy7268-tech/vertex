FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
ENV API_URL=http://api:8000
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
