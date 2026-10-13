# ═══════════════════════════════════════════════════════════════════════════════
# Build stage
# ═══════════════════════════════════════════════════════════════════════════════
FROM node:20-alpine AS build

WORKDIR /app

# Instala dependências a partir do lockfile (build reprodutível).
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Código-fonte do frontend
COPY frontend/ ./

# Pasta centralizada de ícones (ClipBuilder/Icons/) → public/, para que o Vite
# os inclua no dist/ como assets estáticos normais.
COPY Icons/ /Icons/
RUN find /Icons -maxdepth 1 -type f \( -name "*.png" -o -name "*.ico" -o -name "*.svg" -o -name "*.webp" \) \
      -exec cp {} ./public/ \; || true

# ── Variáveis de build do Vite ────────────────────────────────────────────────
# Precisam existir em build-time: o Vite as inlineia no bundle.
# Chave publicável do Clerk (opcional — sem ela o app usa o JWT local).
ARG VITE_CLERK_PUBLISHABLE_KEY=""
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY

# Public key do Mercado Pago (tokenização de cartão).
ARG VITE_MP_PUBLIC_KEY=""
ENV VITE_MP_PUBLIC_KEY=$VITE_MP_PUBLIC_KEY

# Site key do Cloudflare Turnstile (proteção do login).
ARG VITE_TURNSTILE_SITE_KEY=""
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY

RUN npm run build

# ═══════════════════════════════════════════════════════════════════════════════
# Serve stage
# ═══════════════════════════════════════════════════════════════════════════════
FROM nginx:1.27-alpine

RUN apk add --no-cache curl

COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf            /etc/nginx/conf.d/default.conf
COPY frontend/security-headers.conf /etc/nginx/security-headers.conf

EXPOSE 80
EXPOSE 443

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS -o /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
