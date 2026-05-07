# ─────────────────────────────────────────────
# Stage 1 — node builder
# Build the React static assets
# ─────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests first (layer cache optimisation)
COPY package.json package-lock.json* ./

RUN npm ci --silent

# Copy source and build
# REACT_APP_API_URL can be overridden at build time:
#   docker build --build-arg REACT_APP_API_URL=https://api.example.com .
ARG REACT_APP_API_URL=""
ENV REACT_APP_API_URL=$REACT_APP_API_URL

COPY . .
RUN npm run build


# ─────────────────────────────────────────────
# Stage 2 — nginx runtime
# Serve static files; ~20 MB final image
# ─────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Remove default config
RUN rm /etc/nginx/conf.d/default.conf

# Custom nginx config (SPA-friendly, security headers)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Run as non-root
RUN addgroup -S appgroup && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /usr/share/nginx/html \
                                  /var/cache/nginx \
                                  /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown -R appuser:appgroup /var/run/nginx.pid \
    && sed -i 's|pid.*nginx.pid|pid /tmp/nginx.pid|' /etc/nginx/nginx.conf

USER appuser

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://localhost:80 || exit 1

CMD ["nginx", "-g", "daemon off;"]