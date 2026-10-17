FROM node:24.11.1-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
FROM node:24.11.1-alpine AS build
WORKDIR /app
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=${API_INTERNAL_URL}
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
FROM node:24.11.1-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
RUN addgroup -S appgroup && adduser -S appuser -G appgroup && chown -R appuser:appgroup /app
USER appuser
EXPOSE 3000
CMD ["npm", "start"]
