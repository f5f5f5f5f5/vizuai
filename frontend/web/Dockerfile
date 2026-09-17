FROM node:24-bookworm-slim AS builder

WORKDIR /app/frontend/web

COPY frontend/web/package.json frontend/web/pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

COPY . /app
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN pnpm build

FROM nginx:1.27-alpine

COPY frontend/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/web/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
